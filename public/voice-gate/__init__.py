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

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import rules

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


def _message(found: List[Tuple[str, List[str]]], mode: str) -> str:
    listed = "; ".join(f"{name}: {', '.join(calls)}" for name, calls in found)
    if mode == "improve":
        return (
            f"voice-gate improve: fix {len(found)} file(s) before this turn ends. {listed}. "
            "Rewrite the passages whose job is explanation, then re-read the file."
        )
    return (
        f"voice-gate: tells in {len(found)} changed file(s). {listed}. "
        "Rewrite the passages whose job is explanation, or say why the shape is deliberate."
    )


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
            calls = rules.gate_findings(result)
            if calls:
                found.append((path.name, calls))
        if not found:
            return None
        return {"action": "continue", "message": _message(found, mode)}
    except Exception:
        log.debug("voice-gate pre_verify failed", exc_info=True)
        return None


def register(ctx: Any) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_verify", _on_pre_verify)
