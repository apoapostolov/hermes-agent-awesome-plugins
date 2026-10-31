"""Fetch and install the agent-desktop binary from its official GitHub release.

The plugin does not bundle the binary. This module downloads the release archive
for the running Windows target, checks it against a digest pinned here for every
release the plugin was tested with (and against the release's own checksums.txt
for any other version), extracts only the expected entry, and then proves the
install by running ``version`` and ``status`` against the new binary.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import agentdesktop_config as settings

RELEASE_BASE = "https://github.com/vercel-labs/agent-desktop/releases/download/v{version}/{name}"
DEFAULT_VERSION = "1.0.2"
USER_AGENT = "hermes-agent-desktop/1.0 (+https://github.com/apoapostolov/hermes-agent-awesome-plugins)"
PLUGIN_DIR = Path(__file__).resolve().parent
ARCHIVE_ENTRY = "agent-desktop.exe"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024

# rust target + installed file name per Windows platform key
TARGETS: Dict[str, Tuple[str, str]] = {
    "win32-x64": ("x86_64-pc-windows-msvc", "agent-desktop-win32-x64.exe"),
    "win32-arm64": ("aarch64-pc-windows-msvc", "agent-desktop-win32-arm64.exe"),
}

# sha256 of agent-desktop-v<version>-<target>.tar.gz, taken from the release's
# checksums.txt and verified locally. A version absent here is not trusted on
# the release's word alone: the install still verifies upstream's checksum, but
# the result says pinned=false so a caller can see the difference.
PINS: Dict[str, Dict[str, str]] = {
    "1.0.2": {
        "win32-x64": "2186c76e7df197c0e67365e45d36d869f74714c56bb8a73817e2a66f3e18e222",
        "win32-arm64": "a0ecd6e17e60a0bcfbb45533a72f2d3a7a73508769588273ef08b0477d2b9687",
    },
}


def platform_key() -> Optional[str]:
    """The Windows target this machine needs, or None when it is not supported."""
    if sys.platform != "win32":
        return None
    machine = (platform.machine() or "").lower()
    if machine in {"arm64", "aarch64"}:
        return "win32-arm64"
    if machine in {"amd64", "x86_64", "x64"}:
        return "win32-x64"
    return None


def install_dir() -> Path:
    configured = str(settings.get("install_dir") or "").strip()
    return Path(configured) if configured else PLUGIN_DIR / "bin"


def installed_binary() -> Optional[Path]:
    key = platform_key()
    if not key:
        return None
    candidate = install_dir() / TARGETS[key][1]
    return candidate if candidate.is_file() else None


def _download(url: str, timeout: float = 120.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError(f"download exceeded {MAX_ARCHIVE_BYTES} bytes")
    return data


def _checksum_from_listing(text: str, name: str) -> Optional[str]:
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[1].lstrip("*") == name:
            return parts[0].lower()
    return None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _extract_binary(archive: bytes) -> bytes:
    """Pull the single expected executable out of the release tarball.

    Anything else in the archive, and any path that could escape the target
    directory, is refused: this runs on a download the plugin did not build.
    """
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as handle:
        names = [member.name for member in handle.getmembers() if member.isfile()]
        unexpected = [name for name in names if os.path.basename(name) != ARCHIVE_ENTRY or os.path.dirname(name)]
        if unexpected:
            raise ValueError(f"archive has unexpected entries: {unexpected}")
        if ARCHIVE_ENTRY not in names:
            raise ValueError(f"archive has no {ARCHIVE_ENTRY}")
        extracted = handle.extractfile(ARCHIVE_ENTRY)
        if extracted is None:
            raise ValueError(f"{ARCHIVE_ENTRY} is not a regular file")
        payload = extracted.read()
    if not payload.startswith(b"MZ"):
        raise ValueError("extracted file is not a Windows executable")
    return payload


def _probe(binary: Path, command: str, timeout: float = 20.0) -> Dict[str, Any]:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    try:
        completed = subprocess.run(
            [str(binary), command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "command": command, "error": str(exc)}
    try:
        envelope = json.loads(completed.stdout or "")
    except json.JSONDecodeError:
        return {"ok": False, "command": command, "error": (completed.stderr or completed.stdout or "")[-400:]}
    return {"ok": bool(envelope.get("ok")), "command": command, "data": envelope.get("data"), "error": envelope.get("error")}


def verify(binary: Optional[Path] = None) -> Dict[str, Any]:
    """Prove a binary actually works: it answers version and status."""
    target = binary or installed_binary()
    if target is None:
        return {"ok": False, "error": "no installed binary to verify"}
    version = _probe(target, "version")
    if not version.get("ok"):
        return {"ok": False, "path": str(target), "version": version, "error": "version probe failed"}
    status = _probe(target, "status")
    return {
        "ok": bool(status.get("ok")),
        "path": str(target),
        "reported_version": (version.get("data") or {}).get("version"),
        "platform": (status.get("data") or {}).get("platform"),
        "accessibility": ((status.get("data") or {}).get("permissions") or {}).get("accessibility", {}).get("state"),
        "status_ok": bool(status.get("ok")),
    }


def status() -> Dict[str, Any]:
    key = platform_key()
    configured = str(settings.get("bin_path") or "").strip()
    binary = installed_binary()
    return {
        "ok": True,
        "platform_key": key,
        "supported": key is not None,
        "settings": settings.snapshot(),
        "install_dir": str(install_dir()),
        "installed_binary": str(binary) if binary else None,
        "configured_bin_path": configured or None,
        "pinned_versions": sorted(PINS),
    }


def install(version: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """Download, verify, install and prove the binary. Safe to re-run."""
    key = platform_key()
    if not key:
        return {"ok": False, "error": "this plugin supports Windows x64 and arm64 only", "platform": sys.platform}

    target_version = str(version or settings.get("version") or DEFAULT_VERSION)
    target_name, binary_name = TARGETS[key]
    destination = install_dir() / binary_name

    if destination.is_file() and not force:
        proof = verify(destination)
        if proof.get("ok"):
            return {
                "ok": True,
                "already_installed": True,
                "version": target_version,
                "binary": str(destination),
                "verification": proof,
                "hint": "pass force=true to reinstall",
            }

    archive_name = f"agent-desktop-v{target_version}-{target_name}.tar.gz"
    archive_url = RELEASE_BASE.format(version=target_version, name=archive_name)
    checksums_url = RELEASE_BASE.format(version=target_version, name="checksums.txt")

    steps = []
    try:
        archive = _download(archive_url)
        steps.append({"step": "download", "url": archive_url, "bytes": len(archive)})
        actual = _sha256(archive)
        pinned = PINS.get(target_version, {}).get(key)
        if pinned:
            if actual != pinned:
                raise ValueError(f"checksum mismatch: expected pinned {pinned}, got {actual}")
            source = "pinned"
        else:
            listing = _download(checksums_url).decode("utf-8", "replace")
            expected = _checksum_from_listing(listing, archive_name)
            if not expected:
                raise ValueError(f"no checksum published for {archive_name}")
            if actual != expected:
                raise ValueError(f"checksum mismatch: expected {expected}, got {actual}")
            source = "upstream-checksums"
        steps.append({"step": "checksum", "sha256": actual, "source": source, "pinned": bool(pinned)})

        payload = _extract_binary(archive)
        steps.append({"step": "extract", "entry": ARCHIVE_ENTRY, "bytes": len(payload)})

        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = destination.with_suffix(destination.suffix + ".install")
        staging.write_bytes(payload)
        os.chmod(staging, os.stat(staging).st_mode | stat.S_IEXEC)
        os.replace(staging, destination)
        (destination.parent / (destination.name + ".sha256")).write_text(actual + "\n", encoding="utf-8")
        steps.append({"step": "write", "path": str(destination)})

        proof = verify(destination)
        steps.append({"step": "verify", "ok": proof.get("ok"), "detail": proof})
        if not proof.get("ok"):
            return {
                "ok": False,
                "error": "installed binary did not answer version and status",
                "binary": str(destination),
                "steps": steps,
            }
        return {
            "ok": True,
            "already_installed": False,
            "version": target_version,
            "binary": str(destination),
            "sha256": actual,
            "checksum_source": source,
            "verification": proof,
            "steps": steps,
        }
    except Exception as exc:  # network, checksum, archive and filesystem failures all land here
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "version": target_version,
            "url": archive_url,
            "steps": steps,
        }
