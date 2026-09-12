"""Memory Review Command backend. Mounted at /api/plugins/memory-review-command/."""

from __future__ import annotations

import os
import re
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

_DEFAULT_MEMORY_LIMIT = 2200
_DEFAULT_USER_LIMIT = 1375
_LIMIT_RE = re.compile(
    r"^(?:[ \t]*)(memory_char_limit|user_char_limit)[ \t]*:[ \t]*(\d+)",
    re.MULTILINE,
)


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


def store_chars(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8"))
    except OSError:
        return 0


def pending_count(home: Path) -> int:
    folder = home / "pending" / "memory"
    if not folder.is_dir():
        return 0
    try:
        return sum(1 for p in folder.glob("*.json") if p.is_file())
    except OSError:
        return 0


def char_limits(home: Path) -> tuple[int, int]:
    memory_limit = _DEFAULT_MEMORY_LIMIT
    user_limit = _DEFAULT_USER_LIMIT
    cfg = home / "config.yaml"
    if not cfg.is_file():
        return memory_limit, user_limit
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return memory_limit, user_limit
    for match in _LIMIT_RE.finditer(text):
        key, raw = match.group(1), int(match.group(2))
        if key == "memory_char_limit":
            memory_limit = raw
        else:
            user_limit = raw
    return memory_limit, user_limit


def read_state(home: Path | None = None) -> dict:
    root = home if home is not None else hermes_home()
    try:
        memory_limit, user_limit = char_limits(root)
        memories = root / "memories"
        mem_used = store_chars(memories / "MEMORY.md")
        user_used = store_chars(memories / "USER.md")
        return {
            "ok": True,
            "pending": pending_count(root),
            "memory_full": bool(memory_limit) and mem_used >= memory_limit,
            "user_full": bool(user_limit) and user_used >= user_limit,
        }
    except Exception:
        return {"ok": False}


@router.get("/state")
def get_state() -> dict:
    return read_state()
