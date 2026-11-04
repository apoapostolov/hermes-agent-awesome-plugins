"""voice-gate: lint the Markdown a turn changed before the turn is allowed to finish.

Hermes fires ``pre_verify`` once per turn when files were edited, and a hook may
return ``{"action": "continue", "message": ...}`` to keep the agent going. This
plugin spends that nudge on the prose the turn just wrote: it reads the Markdown
files the turn changed and names the shapes that make writing read as machine
made, so the next pass can fix the passage instead of guessing.

The rules ship inside the plugin (``rules.py``). Nothing is fetched and nothing
is imported from another package, so it behaves the same on a fresh install with
no writing skills. Every failure path returns ``None``: a missing file, an
unreadable path, or a broken rule can never block a turn.

Settings live at ``plugins.entries.voice-gate.settings``. ``mode`` is ``warn``
(ask once), ``improve`` (keep asking until the tells are gone, within the host's
nudge budget) or ``skip`` (off). ``min_words`` is the smallest document worth
checking, default 200.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import rules
from . import vale

log = logging.getLogger(__name__)

PROSE_SUFFIXES = {".md", ".markdown", ".mdx"}
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
DEFAULT_MIN_WORDS = 200
_SKIP_WORDS = {"off", "skip", "false", "no", "0"}

_CTX: Any = None


def _setting(key: str, default: Any) -> Any:
    if _CTX is None:
        return default
    try:
        value = _CTX.get_config(key, default)
        return default if value is None else value
    except Exception:
        return default


def _mode() -> str:
    raw = str(_setting("mode", "warn")).strip().lower()
    if raw in _SKIP_WORDS:
        return "skip"
    return raw if raw in ("warn", "improve") else "warn"


def _min_words() -> int:
    try:
        value = int(_setting("min_words", DEFAULT_MIN_WORDS))
    except (TypeError, ValueError):
        return DEFAULT_MIN_WORDS
    return value if value > 0 else DEFAULT_MIN_WORDS


def _resolve(raw: str) -> Optional[Path]:
    """Absolute file path for a changed Markdown file, or None to skip it."""
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        if not path.is_file() or path.suffix.lower() not in PROSE_SUFFIXES:
            return None
        if any(part in SKIP_PARTS for part in path.parts):
            return None
        return path
    except Exception:
        return None


def _message(found: List[Tuple[str, List[str]]], mode: str, note: str = "") -> str:
    listed = "; ".join(f"{name}: {', '.join(calls)}" for name, calls in found)
    pieces: List[str] = []
    if listed:
        if mode == "improve":
            pieces.append(f"fix {len(found)} file(s) before this turn ends. {listed}.")
        else:
            pieces.append(f"tells in {len(found)} changed file(s). {listed}.")
    if note:
        pieces.append(note)
    if mode == "improve":
        tail = "Rewrite the passages whose job is explanation, then re-read the file."
        return f"voice-gate improve: {' '.join(pieces)} {tail}"
    tail = "Rewrite the passages whose job is explanation, or say why the shape is deliberate."
    return f"voice-gate: {' '.join(pieces)} {tail}"


VALE_OFF = {"off", "skip", "no", "false", "0", ""}


def _vale_advisory(paths: List[Path]) -> Optional[str]:
    """A second opinion from Vale, when it is installed and switched on.

    The pack under ``styles/`` is generated from the same families, so Vale
    contributes positions and a per-rule breakdown rather than different words.
    Fail-open in every direction: no binary, no report, or fewer alerts than the
    threshold, and the gate says nothing on its behalf.
    """
    mode = str(_setting("vale_mode", "off") or "off").strip().lower()
    if mode in VALE_OFF or not paths:
        return None
    override = _vale_path()
    if not vale.resolve_binary(override):
        return None
    report = vale.run([str(path) for path in paths[:6]], override)
    if not report.get("ok"):
        return None
    alerts: List[Dict[str, Any]] = []
    for results in (report.get("report") or {}).values():
        for alert in results or []:
            if str(alert.get("Severity") or "").lower() in ("error", "warning"):
                alerts.append(alert)
    try:
        floor = int(_setting("vale_min_alerts", 3) or 3)
    except (TypeError, ValueError):
        floor = 3
    if len(alerts) < floor:
        return None
    counts: Dict[str, int] = {}
    for alert in alerts:
        name = str(alert.get("Check") or "rule").split(".")[-1]
        counts[name] = counts.get(name, 0) + 1
    summary = ", ".join(f"{name} {count}" for name, count in
                        sorted(counts.items(), key=lambda item: -item[1])[:4])
    first = alerts[0]
    files = len(report.get("report") or {})
    return (f"Vale reports {len(alerts)} alert(s) in {files} file(s) ({summary}); "
            f"first at line {first.get('Line')}: {first.get('Match')}.")


def _on_pre_verify(**kwargs: Any) -> Optional[Dict[str, Any]]:
    try:
        mode = _mode()
        if mode == "skip":
            return None
        # warn asks once per turn; improve keeps asking while the host allows it.
        attempt = int(kwargs.get("attempt") or 0)
        if mode == "warn" and attempt != 0:
            return None
        min_words = _min_words()
        found: List[Tuple[str, List[str]]] = []
        checked: List[Path] = []
        for raw in kwargs.get("changed_paths") or []:
            path = _resolve(str(raw))
            if path is None:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            result = rules.lint(text)
            if int(result.get("words") or 0) < min_words:
                continue
            checked.append(path)
            calls = rules.gate_findings(result)
            if calls:
                found.append((path.name, calls))
        advisory = _vale_advisory(checked) or ""
        if not found and not advisory:
            return None
        return {"action": "continue", "message": _message(found, mode, advisory)}
    except Exception:
        log.debug("voice-gate pre_verify failed", exc_info=True)
        return None


VALE_SCHEMA = {
    "name": "voice_gate_vale",
    "description": (
        "Install and run Vale, the prose linter, on Markdown you name. action=status reports what is "
        "installed; action=install downloads the pinned release after the digest is checked; "
        "action=check runs it over files and returns the alerts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "install", "check"],
                       "description": "status, install, or check."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Markdown files for action=check."},
            "path": {"type": "string",
                     "description": "Optional path to a Vale binary to use instead of the plugin's copy."},
        },
        "required": ["action"],
    },
}


def _vale_path() -> str:
    return str(_setting("vale_path", "") or "").strip()


def _tool_vale(args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "status").strip().lower()
    override = str(args.get("path") or "").strip() or _vale_path()
    if action == "status":
        return vale.status(override)
    if action == "install":
        return vale.install(override)
    if action == "check":
        return vale.run([str(p) for p in (args.get("paths") or [])], override)
    return {"ok": False, "error": f"unknown action {action!r}"}


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **_kwargs: Any) -> Optional[Dict[str, Any]]:
    """Send the one call that downloads and runs a binary to the approval prompt."""
    if tool_name != VALE_SCHEMA["name"] or not isinstance(args, dict):
        return None
    if str(args.get("action") or "").strip().lower() != "install":
        return None
    name, digest, _kind = vale.asset()
    return {
        "action": "approve",
        "message": (
            f"voice_gate_vale install will download {name} from GitHub "
            f"(vale {vale.VERSION}), check sha256 {digest[:16]}…, and run the unpacked binary from "
            f"{vale.data_dir()}"
        ),
    }


def _as_handler(fn, name: str):
    def handler(args: Optional[dict] = None, **_kwargs) -> str:
        try:
            return json.dumps(fn(dict(args or {})), ensure_ascii=False)
        except Exception as exc:
            log.exception("voice-gate tool %s failed", name)
            return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return handler


def register(ctx: Any) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_verify", _on_pre_verify)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_tool(
        name=VALE_SCHEMA["name"],
        toolset="voice_gate",
        schema=VALE_SCHEMA,
        handler=_as_handler(_tool_vale, VALE_SCHEMA["name"]),
        emoji="🪶",
    )
