"""Better Capabilities backend — mounted at /api/plugins/better-capabilities/.

Skill file work only: resolve a skill folder, list its markdown, read one, zip it,
delete it. Presets are served from here too so chat and the Desktop page read one
store (``presets.py``).

Every path is resolved per REQUEST, not at import: one backend process serves
secondary profiles, and ``get_hermes_home()`` honors the context-local home
override each request sets.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._@-]{0,80}$")
SKIP_DIR_NAMES = {".git", "__pycache__", "node_modules", ".venv", "venv"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".so", ".dylib", ".pyd"}
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_TEXT_BYTES = 1024 * 1024
MAX_LISTED_FILES = 400
MAX_DEPTH = 6


def hermes_home() -> Path:
    """The active profile's Hermes home, resolved per call."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        env = os.environ.get("HERMES_HOME")
        if env:
            return Path(env)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            win = Path(local) / "hermes"
            if win.exists():
                return win
        return Path.home() / ".hermes"


def _presets():
    """The shared preset module, loaded on demand from the plugin root."""
    path = Path(__file__).resolve().parents[1] / "presets.py"
    spec = importlib.util.spec_from_file_location("better_capabilities_presets", path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail="Could not load the preset module.")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class SkillBody(BaseModel):
    name: str = Field(min_length=1, max_length=81)


class FileBody(BaseModel):
    name: str = Field(min_length=1, max_length=81)
    rel: str = Field(min_length=1, max_length=400)


class PresetBody(BaseModel):
    kind: str
    name: str = Field(min_length=1, max_length=60)


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _user_skill_roots(home: Path) -> list[tuple[int, Path]]:
    """Search roots inside the user skills tree, in the host's own precedence order."""
    from tools.skills_tool import skill_search_dirs

    roots, active_dir = skill_search_dirs()
    user_root = home / "skills"
    picked = [(tier, Path(where)) for tier, where in roots if _is_under(Path(where), user_root)]
    known = {where for _tier, where in picked}
    if active_dir and _is_under(Path(active_dir), user_root) and Path(active_dir) not in known:
        picked.append((99, Path(active_dir)))
    return picked


def _find_skill_dir(home: Path, name: str) -> Path | None:
    """Resolve one skill the way skill_view does, inside the user skills tree.

    The public helpers give tier precedence and refuse an ambiguous name instead
    of guessing, and the roots are filtered to the only tree this panel may zip,
    read or delete. A quarantined project skill never resolves here because the
    project tier is not in the root list.
    """
    try:
        from tools.skills_tool import locate_skill, skill_lookup_path_error

        if skill_lookup_path_error(name):
            return None
        roots = _user_skill_roots(home)
        if not roots:
            return None
        error_json, skill_dir, _skill_md = locate_skill(name, None, roots)
        if error_json or skill_dir is None:
            return None
    except Exception:
        return None
    path = Path(skill_dir)
    if not path.is_dir() or not (path / "SKILL.md").is_file():
        return None
    return path


def _skill_dir(name: str) -> tuple[Path, Path]:
    if not SAFE_NAME.match(name or ""):
        raise HTTPException(status_code=400, detail="Name is not a safe skill id.")
    home = hermes_home()
    path = _find_skill_dir(home, name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' was not found on disk.")
    root = home / "skills"
    if not _is_under(path, root):
        raise HTTPException(status_code=403, detail="That skill is not in the user skills folder.")
    return path, root


def _moved_target(home: Path, path: Path) -> Path:
    """A free ``<home>/better-capabilities-trash/<name>[-n]`` target."""
    grave_root = home / "better-capabilities-trash"
    grave = grave_root / path.name
    suffix = 1
    while grave.exists():
        grave = grave_root / f"{path.name}-{suffix}"
        suffix += 1
    return grave


def _delete_dir(path: Path) -> str:
    """Send a directory to the Recycle Bin when the OS can, else move it aside.

    A non-Windows host, or one whose recycle helper is unavailable, gets the
    moved-aside result instead of a 500 before its fallback runs.
    """
    home = hermes_home()
    if os.name == "nt":
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

    grave = _moved_target(home, path)
    try:
        grave.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(grave))
        return "moved"
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not recycle or move '{path.name}': {exc}",
        ) from exc


def _zip_dir(path: Path) -> tuple[str, str]:
    """Zip one skill folder.

    Symlinks and non-regular files are skipped: a link inside a skill can point at
    anything the user can read (``~/.ssh``), and an export must never carry it.
    """
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(path.rglob("*")):
            if file_path.is_symlink() or not file_path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in file_path.relative_to(path).parts):
                continue
            if file_path.suffix in SKIP_SUFFIXES:
                continue
            try:
                size = file_path.stat().st_size
            except OSError:
                continue
            total += size
            if total > MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="Skill folder is too large to zip.")
            arc = Path(path.name) / file_path.relative_to(path)
            zf.write(file_path, arc.as_posix())
    raw = buf.getvalue()
    return f"{path.name}.zip", base64.b64encode(raw).decode("ascii")


def _markdown_files(path: Path) -> list[dict[str, str]]:
    """SKILL.md first, then every other markdown file, depth-first by folder."""
    files: list[dict[str, str]] = [{"rel": "SKILL.md", "folder": "", "label": "SKILL.md"}]

    def walk(directory: Path, prefix: str, depth: int) -> None:
        if depth > MAX_DEPTH or len(files) >= MAX_LISTED_FILES:
            return
        try:
            entries = sorted(
                directory.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())
            )
        except OSError:
            return
        for entry in entries:
            if len(files) >= MAX_LISTED_FILES:
                return
            if entry.name in SKIP_DIR_NAMES or entry.is_symlink():
                continue
            if entry.is_dir():
                walk(entry, f"{prefix}/{entry.name}" if prefix else entry.name, depth + 1)
            elif entry.is_file() and entry.suffix.lower() == ".md":
                if not prefix and entry.name == "SKILL.md":
                    continue
                rel = f"{prefix}/{entry.name}" if prefix else entry.name
                files.append(
                    {
                        "rel": rel,
                        "folder": prefix or "/",
                        "label": f"{prefix}/{entry.name}" if prefix else entry.name,
                    }
                )

    walk(path, "", 1)
    return files


def _read_markdown(path: Path, rel: str) -> str:
    candidate = Path(rel)
    if candidate.is_absolute() or any(part in {"..", ""} for part in candidate.parts):
        raise HTTPException(status_code=400, detail="Relative path must stay inside the skill.")
    if candidate.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown files can be previewed.")
    target = path / candidate
    if target.is_symlink() or not target.is_file() or not _is_under(target, path):
        raise HTTPException(status_code=404, detail="That file is not in this skill.")
    try:
        if target.stat().st_size > MAX_TEXT_BYTES:
            raise HTTPException(status_code=413, detail="That file is too large to preview.")
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/health")
def health():
    return {"ok": True, "plugin": "better-capabilities"}


@router.post("/resolve")
def resolve(body: SkillBody):
    path, _root = _skill_dir(body.name)
    return {"ok": True, "kind": "skill", "name": body.name, "path": str(path)}


@router.post("/files")
def list_files(body: SkillBody):
    path, _root = _skill_dir(body.name)
    return {"ok": True, "name": body.name, "path": str(path), "files": _markdown_files(path)}


@router.post("/file")
def read_file(body: FileBody):
    path, _root = _skill_dir(body.name)
    return {"ok": True, "name": body.name, "rel": body.rel, "text": _read_markdown(path, body.rel)}


@router.post("/zip")
def zip_skill(body: SkillBody):
    path, _root = _skill_dir(body.name)
    filename, b64 = _zip_dir(path)
    return {"ok": True, "filename": filename, "b64": b64}


@router.post("/delete")
def delete_skill(body: SkillBody):
    path, _root = _skill_dir(body.name)
    result = _delete_dir(path)
    return {"ok": True, "name": body.name, "result": result}


@router.post("/nav-probe")
def nav_probe(body: dict):
    """TEMP PROBE (1.1.0): the Desktop half reports what the nav row looks like.

    Appends one JSON line to ``better-capabilities-nav-probe.jsonl`` in this
    Hermes home. Read it to tell a stale renderer module apart from a broken
    selector. Remove with the matching block in desktop/plugin.js.
    """
    path = hermes_home() / "better-capabilities-nav-probe.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"received": time.time(), "body": body}, ensure_ascii=False) + "\n")
        if path.stat().st_size > 256_000:
            lines = path.read_text(encoding="utf-8").splitlines()[-50:]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Probe write failed: {exc}") from exc
    return {"ok": True}


@router.get("/presets")
def get_presets():
    return {"ok": True, "store": _presets().load_store()}


@router.put("/presets")
def put_presets(body: dict):
    mod = _presets()
    store = mod.empty_store()
    source = body.get("store") if isinstance(body.get("store"), dict) else body
    if not isinstance(source, dict):
        raise HTTPException(status_code=400, detail="Preset store must be an object.")
    for kind in ("skills", "tools", "plugins"):
        value = source.get(kind)
        if not isinstance(value, dict):
            continue
        bucket = {name: row for name, row in value.items() if name != "_order"}
        bucket["_order"] = [name for name in value.get("_order", []) if name in bucket]
        store[kind] = bucket
    mod.save_store(store)
    return {"ok": True}


@router.post("/presets/save")
def save_named_preset(body: PresetBody):
    message = _presets().handle_preset_command(f"save {body.kind} {body.name}")
    return {"ok": True, "message": message}


@router.post("/presets/apply")
def apply_named_preset(body: PresetBody):
    message = _presets().handle_preset_command(f"{body.kind} {body.name}")
    return {"ok": True, "message": message}


@router.get("/presets/pending")
def get_pending():
    return {"ok": True, "pending": _presets().read_pending()}


@router.delete("/presets/pending")
def delete_pending():
    _presets().clear_pending()
    return {"ok": True}
