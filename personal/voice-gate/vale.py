"""Install and run Vale, the prose linter, on request.

Same contract the agent-desktop plugin uses for its own binary: one pinned
release, a digest checked before anything is unpacked, the copy kept under the
plugin's data directory instead of the system, and every download routed
through the ``pre_tool_call`` approval prompt so nothing arrives silently.

Nothing here runs on its own. A turn only reaches this module through the
``voice_gate_vale`` tool.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.request import Request, urlopen

VERSION = "3.26.0"
BASE_URL = f"https://github.com/errata-ai/vale/releases/download/v{VERSION}"

# Digests copied from the release's own checksums file and re-checked against a
# downloaded copy. A mismatch aborts the install before extraction.
ASSETS: Dict[Tuple[str, str], Tuple[str, str, str]] = {
    ("windows", "x86_64"): ("vale_3.26.0_Windows_64-bit.zip",
                            "c42f4b413aa29b6b36fa4e3ac0c18322588a54ac860db4c84b8255997f7d1ec2", "zip"),
    ("linux", "x86_64"): ("vale_3.26.0_Linux_64-bit.tar.gz",
                          "22aa69a556558e4a9dfc63c17030777383d8d3c48dcdfad655fa98e839d666ed", "tar.gz"),
    ("darwin", "x86_64"): ("vale_3.26.0_macOS_64-bit.tar.gz",
                           "df42b317be6ece6a6a70d06b952deec581d047046eb93ea4632f58da56a86ff9", "tar.gz"),
    ("darwin", "arm64"): ("vale_3.26.0_macOS_arm64.tar.gz",
                          "a6c3370f53bad93086c6b85f3163676e44e08049d69743afdcc13f3aab5b7482", "tar.gz"),
}

VALE_INI = """StylesPath = styles
MinAlertLevel = suggestion

[*.md]
BasedOnStyles = Vale
[*.markdown]
BasedOnStyles = Vale
"""


def _platform() -> Tuple[str, str]:
    system = {"win32": "windows", "cygwin": "windows"}.get(sys.platform, sys.platform)
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "x86_64"
    return system, arch


def asset() -> Tuple[str, str, str]:
    key = _platform()
    if key not in ASSETS:
        raise RuntimeError(f"no pinned Vale build for {key[0]}/{key[1]}")
    return ASSETS[key]


def data_dir() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
    return home / "plugin-data" / "voice-gate" / "vale" / VERSION


def binary_name() -> str:
    return "vale.exe" if _platform()[0] == "windows" else "vale"


def installed_binary() -> Optional[Path]:
    candidate = data_dir() / binary_name()
    return candidate if candidate.is_file() else None


def resolve_binary(override: str = "") -> Optional[str]:
    """The binary the tool would run: an explicit path, the plugin's copy, then PATH."""
    if override:
        path = Path(os.path.expandvars(os.path.expanduser(override)))
        if path.is_file():
            return str(path)
    local = installed_binary()
    if local is not None:
        return str(local)
    return shutil.which("vale")


def status(override: str = "") -> Dict[str, Any]:
    resolved = resolve_binary(override)
    name, digest, _kind = asset()
    return {
        "ok": True,
        "pinned_version": VERSION,
        "asset": name,
        "pinned_sha256": digest,
        "installed": str(installed_binary()) if installed_binary() else None,
        "resolved_binary": resolved,
        "resolved_version": _version_of(resolved) if resolved else None,
        "data_dir": str(data_dir()),
        "platform": list(_platform()),
    }


def _version_of(binary: str) -> Optional[str]:
    try:
        out = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).strip().splitlines()[0] if out.returncode == 0 else None
    except Exception:
        return None


def _download(url: str, timeout: float = 180.0) -> bytes:
    request = Request(url, headers={"User-Agent": "voice-gate-hermes-plugin"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed release URL
        return response.read()


def _safe_extract(archive: Path, destination: Path, kind: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if kind == "zip":
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (destination / member.filename).resolve()
                if not str(target).startswith(str(destination.resolve())):
                    raise RuntimeError(f"refusing to extract outside {destination}: {member.filename}")
            bundle.extractall(destination)
        return
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if not str(target).startswith(str(destination.resolve())):
                raise RuntimeError(f"refusing to extract outside {destination}: {member.name}")
        bundle.extractall(destination)


def install(override: str = "") -> Dict[str, Any]:
    """Download the pinned Vale, verify its digest, unpack it, and prove it runs."""
    name, digest, kind = asset()
    steps: List[Dict[str, Any]] = []
    destination = data_dir()

    if installed_binary() is not None and _version_of(str(installed_binary())):
        return {"ok": True, "already": True, "binary": str(installed_binary()),
                "version": _version_of(str(installed_binary())), "steps": steps}

    url = f"{BASE_URL}/{name}"
    steps.append({"step": "download", "url": url})
    archive_bytes = _download(url)
    actual = hashlib.sha256(archive_bytes).hexdigest()
    steps.append({"step": "checksum", "sha256": actual, "pinned": digest, "match": actual == digest})
    if actual != digest:
        return {"ok": False, "error": "checksum mismatch: refused to unpack", "url": url,
                "expected": digest, "actual": actual, "steps": steps}

    with tempfile.TemporaryDirectory(prefix="voice-gate-vale-") as tmp:
        archive = Path(tmp) / name
        archive.write_bytes(archive_bytes)
        _safe_extract(archive, destination, kind)
    steps.append({"step": "extract", "destination": str(destination)})

    binary = destination / binary_name()
    if not binary.is_file():
        found = next((p for p in destination.rglob(binary_name()) if p.is_file()), None)
        if found is None:
            return {"ok": False, "error": "archive did not contain the binary", "steps": steps}
        if found != binary:
            shutil.copy2(found, binary)
    if _platform()[0] != "windows":
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    steps.append({"step": "binary", "path": str(binary)})

    version = _version_of(str(binary))
    if not version:
        return {"ok": False, "error": "the binary did not report a version", "steps": steps}
    steps.append({"step": "probe", "version": version})
    (destination / (binary_name() + ".sha256")).write_text(actual + "\n", encoding="utf-8")
    return {"ok": True, "already": False, "binary": str(binary), "version": version, "steps": steps}


_REPORTS: Dict[Any, Dict[str, Any]] = {}
_CACHE_LIMIT = 8


def _cache_key(binary: str, ini: Path, files: List[str]) -> Any:
    """A turn can describe the same untouched file twice; Vale need not run twice."""
    stamps = []
    for name in files:
        try:
            stat = Path(name).stat()
            stamps.append((name, stat.st_mtime_ns, stat.st_size))
        except OSError:
            stamps.append((name, 0, 0))
    try:
        config_stamp = ini.stat().st_mtime_ns
    except OSError:
        config_stamp = 0
    return (binary, str(ini), config_stamp, tuple(stamps))


def config_path() -> Path:
    """The pack the plugin ships, or a generated fallback in the data directory."""
    shipped = Path(__file__).resolve().parent / ".vale.ini"
    if shipped.is_file():
        return shipped
    fallback = data_dir() / ".vale.ini"
    if not fallback.is_file():
        fallback.parent.mkdir(parents=True, exist_ok=True)
        fallback.write_text(VALE_INI, encoding="utf-8")
    return fallback


def run(paths: List[str], override: str = "", timeout: float = 120.0) -> Dict[str, Any]:
    """Run Vale over files and return its JSON report, or a clear failure."""
    binary = resolve_binary(override)
    if not binary:
        return {"ok": False, "error": "Vale is not installed. Run voice_gate_vale with action=install."}
    files = [str(Path(p).resolve()) for p in paths if Path(p).is_file()]
    if not files:
        return {"ok": False, "error": "no readable files to check"}
    ini = config_path()
    key = _cache_key(binary, ini, files)
    if key in _REPORTS:
        cached = dict(_REPORTS[key])
        cached["cached"] = True
        return cached
    command = [binary, f"--config={ini}", "--output=JSON", *files]
    try:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "command": command}
    try:
        report = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {"ok": False, "error": "Vale returned no JSON report",
                "stderr": (proc.stderr or "")[:800], "command": command}
    counts: Dict[str, int] = {}
    for result in report.values() if isinstance(report, dict) else []:
        # Vale returns a list of alerts per path; older reports nest them under "Alerts".
        alerts = result.get("Alerts") if isinstance(result, dict) else result
        for alert in alerts or []:
            severity = str(alert.get("Severity") or "unknown")
            counts[severity] = counts.get(severity, 0) + 1
    result = {"ok": True, "binary": binary, "files": len(files), "counts": counts, "report": report}
    if len(_REPORTS) >= _CACHE_LIMIT:
        _REPORTS.pop(next(iter(_REPORTS)))
    _REPORTS[key] = result
    return result
