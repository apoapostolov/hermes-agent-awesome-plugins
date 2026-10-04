"""Prompts that must not re-route. Mirrors the Pi router's shouldSkip."""

from __future__ import annotations

from typing import Optional

_ACK = {
    "y", "yes", "yeah", "yep", "ok", "okay", "sure", "continue", "go on", "go ahead",
    "do it", "proceed", "nice", "thanks", "thank you", "ty",
}


def should_skip(text: str, min_prompt_chars: int = 12, has_history: bool = False) -> Optional[str]:
    """Return the skip reason, or None when the turn should be routed."""
    trimmed = (text or "").strip()
    if not trimmed:
        return "empty"
    if trimmed.startswith("/"):
        return "slash command"
    bare = trimmed.rstrip(".!").lower()
    if bare in _ACK:
        return "acknowledgement"
    if len(trimmed) < max(0, int(min_prompt_chars)) and has_history:
        return "short continuation"
    return None


def skip_note(reason: str) -> str:
    return f"jev skipped: {reason}"
