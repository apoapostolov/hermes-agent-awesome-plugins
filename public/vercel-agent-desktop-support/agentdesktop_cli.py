"""Run the agent-desktop binary and hand back its JSON envelope.

Every agent-desktop command prints exactly one envelope with ``ok`` and either
``data`` or ``error``. The tools return that envelope as text, unchanged, so a
caller can branch on ``error.code`` and ``error.disposition`` instead of
guessing from prose.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import agentdesktop_config as settings
from . import agentdesktop_install as install

ENV_BIN = "AGENT_DESKTOP_BIN"
DEFAULT_TIMEOUT = 30.0
# a real interactive snapshot of a dense window runs 40-70 KB; cutting that
# would drop the tree the caller came for, so the cap is generous
MAX_OUTPUT_CHARS = 80000

# npm's Windows global prefix, the documented install location on this host
_NPM_BIN = Path(os.environ.get("APPDATA", "")) / "npm" / "node_modules" / "agent-desktop" / "bin"
_FALLBACK_NAMES = ("agent-desktop-win32-x64.exe", "agent-desktop-win32-arm64.exe", "agent-desktop")


def _candidate_paths() -> List[Path]:
    """Where the binary may live, most specific first.

    The plugin's own setting wins, then its installed copy, then whatever the
    host already had, so a user who points the plugin at a specific build gets
    that build.
    """
    candidates: List[Path] = []
    configured = str(settings.get("bin_path") or "").strip()
    if configured:
        candidates.append(Path(configured))
    own = install.installed_binary()
    if own is not None:
        candidates.append(own)
    override = os.environ.get(ENV_BIN)
    if override:
        candidates.append(Path(override))
    found = shutil.which("agent-desktop")
    if found:
        candidates.append(Path(found))
    candidates.extend(_NPM_BIN / name for name in _FALLBACK_NAMES)
    return candidates


def resolve_binary() -> Optional[str]:
    """Absolute path of the agent-desktop executable, or None when it is missing."""
    for candidate in _candidate_paths():
        try:
            if candidate.is_file():
                return str(candidate)
        except OSError:
            continue
    return None


def _envelope_error(code: str, message: str, **extra: Any) -> str:
    error: Dict[str, Any] = {"code": code, "message": message}
    error.update(extra)
    return json.dumps({"ok": False, "command": None, "error": error}, ensure_ascii=False)


def _flag(name: str, value: Any) -> Optional[str]:
    """Render one CLI flag, or None when the caller left it out."""
    if value is None:
        return None
    if isinstance(value, bool):
        return f"--{name}" if value else None
    text = str(value)
    if text == "":
        return None
    return f"--{name}={text}"


def build_argv(binary: str, command: str, flags: Sequence[Optional[str]], positional: Sequence[str] = ()) -> List[str]:
    argv = [binary, command]
    argv.extend(flag for flag in flags if flag)
    argv.extend(str(item) for item in positional)
    return argv


def _trim_tree(tree: Any, budget: int) -> tuple[Any, int]:
    """Keep the shape of a snapshot tree but stop after ``budget`` nodes.

    Dropping the whole tree makes an oversized snapshot useless; pruning it
    leaves the top of the window readable and says how much was cut. Children
    past the budget are cut from the array (``children_truncated``) instead of
    being emitted one by one, or the trim would cost as much as the tree.
    """
    remaining = [max(1, budget)]
    dropped = [0]

    def walk(node: Any) -> Any:
        if not isinstance(node, dict):
            return node
        if remaining[0] <= 0:
            dropped[0] += 1
            return None
        remaining[0] -= 1
        out = dict(node)
        children = node.get("children")
        if isinstance(children, list):
            kept = []
            for child in children:
                if remaining[0] <= 0:
                    dropped[0] += len(children) - len(kept)
                    out["children_truncated"] = True
                    break
                walked = walk(child)
                if walked is not None:
                    kept.append(walked)
            out["children"] = kept
        return out

    pruned = walk(tree)
    return pruned, dropped[0]


def run(
    command: str,
    flags: Sequence[Optional[str]] = (),
    positional: Sequence[str] = (),
    *,
    headed: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
    max_chars: int = MAX_OUTPUT_CHARS,
) -> str:
    """Run one agent-desktop command and return its envelope as JSON text."""
    binary = resolve_binary()
    install_error = None
    if not binary and settings.as_bool("auto_install"):
        outcome = install.install()
        binary = resolve_binary()
        if not binary:
            install_error = outcome.get("error")
    if not binary:
        extra: Dict[str, Any] = {
            "suggestion": "run desktop_install with action=install, or npm install -g agent-desktop",
            "env_var": ENV_BIN,
        }
        if install_error:
            extra["auto_install_error"] = install_error
        return _envelope_error(
            "BINARY_NOT_FOUND",
            "agent-desktop is not installed or not on PATH",
            **extra,
        )

    argv = build_argv(binary, command, flags, positional)
    if headed:
        argv.insert(2, "--headed")

    creationflags = 0
    if os.name == "nt":
        # never flash a console window into Apo's session
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=creationflags,
        )
    except subprocess.TimeoutExpired:
        return _envelope_error(
            "TIMEOUT",
            f"agent-desktop {command} did not finish within {timeout:g}s",
            retry="safe",
        )
    except OSError as exc:
        return _envelope_error("SPAWN_FAILED", f"could not run {argv[0]}: {exc}")

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if not stdout:
        return _envelope_error(
            "NO_OUTPUT",
            f"agent-desktop {command} printed nothing",
            exit_code=completed.returncode,
            stderr=stderr[-2000:],
        )

    try:
        parsed = json.loads(stdout)
    except json.JSONDecodeError:
        # not an envelope: keep the text rather than pretending it parsed
        payload = {
            "ok": completed.returncode == 0,
            "command": command,
            "raw": stdout[:max_chars],
            "exit_code": completed.returncode,
        }
        if stderr:
            payload["stderr"] = stderr[-2000:]
        return json.dumps(payload, ensure_ascii=False)

    if len(stdout) <= max_chars:
        return stdout

    data = parsed.get("data")
    if isinstance(data, dict) and isinstance(data.get("tree"), dict):
        # prune the tree until it fits, so the caller keeps a usable snapshot
        budget = max(8, max_chars // 60)
        while budget >= 4:
            pruned, dropped = _trim_tree(data["tree"], budget)
            candidate = dict(parsed)
            candidate_data = dict(data)
            candidate_data["tree"] = pruned
            candidate_data["tree_nodes_dropped"] = dropped
            candidate_data["original_chars"] = len(stdout)
            candidate["data"] = candidate_data
            text = json.dumps(candidate, ensure_ascii=False)
            if len(text) <= max_chars or dropped == 0:
                if dropped:
                    candidate_data["hint"] = (
                        "tree pruned to fit: re-run with a smaller scope (root=<ref>, skeleton=true, "
                        "lower max_depth) or raise max_chars"
                    )
                return text
            budget //= 2

    trimmed: Dict[str, Any] = dict(parsed)
    if isinstance(data, dict):
        kept = {k: v for k, v in data.items() if k != "tree"}
        kept["tree"] = "<truncated: output exceeded max_chars>"
        kept["tree_truncated_by_plugin"] = True
        kept["original_chars"] = len(stdout)
        kept["hint"] = "re-run with a smaller scope: --root <ref>, --skeleton, or a lower max_depth"
        trimmed["data"] = kept
    else:
        trimmed["data"] = data
        trimmed["raw_truncated"] = True
        trimmed["original_chars"] = len(stdout)
    return json.dumps(trimmed, ensure_ascii=False)[:max_chars]


def flags(**kwargs: Any) -> List[str]:
    """Build a flag list from keyword arguments, dropping unset ones.

    ``window_id="w-1"`` becomes ``--window-id=w-1``; ``compact=True`` becomes
    ``--compact``; ``compact=False`` and ``None`` disappear entirely.
    """
    rendered = (_flag(name.replace("_", "-"), value) for name, value in kwargs.items())
    return [flag for flag in rendered if flag]
