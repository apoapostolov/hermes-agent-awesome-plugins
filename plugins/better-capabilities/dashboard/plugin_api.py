"""Better Capabilities backend — mounted at /api/plugins/better-capabilities/."""

from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
MAX_ZIP_BYTES = 80 * 1024 * 1024


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        win = Path(local) / "hermes"
        if win.exists():
            return win
    return Path.home() / ".hermes"


HOME = hermes_home()


class TargetBody(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=81)


def _check_name(name: str) -> str:
    if not SAFE_NAME.match(name):
        raise HTTPException(status_code=400, detail="Name is not a safe folder id.")
    return name


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _find_skill_dir(name: str) -> Path | None:
    try:
        from tools.skill_manager_tool import _find_skill

        found = _find_skill(name)
        if found and found.get("path"):
            path = Path(found["path"])
            if path.is_dir() and (path / "SKILL.md").is_file():
                return path
    except Exception:
        pass
    root = HOME / "skills"
    if not root.is_dir():
        return None
    for md in root.rglob("SKILL.md"):
        if md.parent.name == name:
            return md.parent
    return None


def _find_plugin_dir(name: str) -> Path | None:
    for root in (HOME / "plugins", HOME / "desktop-plugins"):
        path = root / name
        if path.is_dir():
            return path
    return None


def _resolve(kind: str, name: str) -> Path:
    name = _check_name(name)
    kind = (kind or "").strip().lower()
    if kind == "skill":
        path = _find_skill_dir(name)
        root = HOME / "skills"
        if path is None:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' was not found on disk.")
        if not _is_under(path, root):
            raise HTTPException(status_code=403, detail="That skill is not in the user skills folder.")
        return path
    if kind == "plugin":
        path = _find_plugin_dir(name)
        if path is None:
            raise HTTPException(status_code=404, detail=f"Plugin '{name}' was not found on disk.")
        if not (
            _is_under(path, HOME / "plugins") or _is_under(path, HOME / "desktop-plugins")
        ):
            raise HTTPException(status_code=403, detail="That plugin is outside the Hermes plugin folders.")
        return path
    raise HTTPException(status_code=400, detail="kind must be plugin or skill.")


def _recycle_dir(path: Path) -> str:
    """Send a directory to the Recycle Bin. Fall back to a disabled-graveyard move."""
    if os.name != "nt":
        raise HTTPException(status_code=500, detail="Recycle Bin delete is only wired on Windows.")
    script = Path(tempfile.gettempdir()) / "better-capabilities-recycle.ps1"
    target = str(path.resolve())
    script.write_text(
        "Add-Type -AssemblyName Microsoft.VisualBasic\n"
        "$target = $env:BC_RECYCLE_TARGET\n"
        "[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory(\n"
        "  $target,\n"
        "  [Microsoft.VisualBasic.FileIO.UIOption]::OnlyErrorDialogs,\n"
        "  [Microsoft.VisualBasic.FileIO.RecycleOption]::SendToRecycleBin\n"
        ")\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["BC_RECYCLE_TARGET"] = target
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=45,
            env=env,
        )
        if completed.returncode == 0 and not path.exists():
            return "recycled"
    except (subprocess.TimeoutExpired, OSError):
        pass
    grave = HOME / "plugins-disabled" / f"{path.name}-removed"
    grave.parent.mkdir(parents=True, exist_ok=True)
    if grave.exists():
        suffix = 1
        while True:
            candidate = grave.parent / f"{path.name}-removed-{suffix}"
            if not candidate.exists():
                grave = candidate
                break
            suffix += 1
    try:
        path.rename(grave)
        return "moved"
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not recycle or move '{path.name}': {exc}",
        ) from exc


def _zip_dir(path: Path, folder_name: str) -> tuple[str, str]:
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in path.rglob("*"):
            if not file_path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in file_path.parts):
                continue
            if file_path.suffix in SKIP_SUFFIXES:
                continue
            total += file_path.stat().st_size
            if total > MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="Skill folder is too large to zip.")
            arc = Path(folder_name) / file_path.relative_to(path)
            zf.write(file_path, arc.as_posix())
    raw = buf.getvalue()
    filename = f"{folder_name}.zip"
    return filename, base64.b64encode(raw).decode("ascii")


@router.get("/health")
def health():
    return {"ok": True, "plugin": "better-capabilities"}


@router.post("/resolve")
def resolve(body: TargetBody):
    path = _resolve(body.kind, body.name)
    return {"ok": True, "kind": body.kind, "name": body.name, "path": str(path)}


@router.post("/zip")
def zip_target(body: TargetBody):
    if body.kind.strip().lower() != "skill":
        raise HTTPException(status_code=400, detail="Only skills can be packaged as a zip.")
    path = _resolve("skill", body.name)
    filename, b64 = _zip_dir(path, path.name)
    return {"ok": True, "filename": filename, "b64": b64}


@router.post("/delete")
def delete_target(body: TargetBody):
    path = _resolve(body.kind, body.name)
    result = _recycle_dir(path)
    return {"ok": True, "name": body.name, "kind": body.kind, "result": result}
