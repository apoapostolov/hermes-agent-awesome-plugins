"""RSS Reader desktop UI and slash-command bridge."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


_REFRESH_RE = re.compile(r"^(?P<minutes>[1-9]\d{0,3})m$", re.IGNORECASE)
_REFINE_RE = re.compile(r"^(?P<days>[1-9]\d{0,2})d$", re.IGNORECASE)
_MAX_MINUTES = 1440
_MAX_DAYS = 365
_MAX_TEXT = 200


def _hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes"
    return Path.home() / ".hermes"


def _queue_path() -> Path:
    return _hermes_home() / "rss-reader" / "commands.jsonl"


def _usage() -> str:
    return (
        "Usage: /rss refresh [XXm] | /rss mute <keyword> | /rss refine <XXd> | "
        "/rss add <url or website>[, name] to <folder>"
    )


def _parse(raw_args: str) -> tuple[str, dict[str, Any]] | None:
    raw = str(raw_args or "").strip()
    if not raw or raw.lower() in {"help", "--help", "-h"}:
        return None

    parts = raw.split(None, 1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) == 2 else ""

    if action == "refresh":
        if not rest:
            return "refresh", {}
        match = _REFRESH_RE.fullmatch(rest)
        if not match or int(match.group("minutes")) > _MAX_MINUTES:
            raise ValueError("Refresh period must be 1m to 1440m, for example 30m.")
        return "refresh-period", {"minutes": int(match.group("minutes"))}

    if action == "mute":
        phrase = rest[:_MAX_TEXT].strip()
        if not phrase:
            raise ValueError("Usage: /rss mute <keyword or phrase>")
        return "mute", {"phrase": phrase}

    if action == "refine":
        if not rest:
            return "refine", {"days": 30}
        match = _REFINE_RE.fullmatch(rest)
        if not match or int(match.group("days")) > _MAX_DAYS:
            raise ValueError("Refinement period must be 1d to 365d, for example 30d.")
        return "refine", {"days": int(match.group("days"))}

    if action == "add":
        match = re.fullmatch(r"(.+?)\s+to\s+(.+)", rest, re.IGNORECASE)
        source = (match.group(1) if match else rest).strip()[:_MAX_TEXT]
        folder = (match.group(2) if match else "").strip()[:100]
        if not source:
            raise ValueError("Give a feed URL or website name to add.")
        return "add", {"source": source, "folder": folder}

    raise ValueError(f"Unknown RSS action '{action}'. {_usage()}")


def _enqueue(action: str, payload: dict[str, Any]) -> str:
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "id": str(uuid.uuid4()),
        "action": action,
        "payload": payload,
        "created_at": time.time(),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record["id"]


def _handle(raw_args: str) -> str:
    try:
        parsed = _parse(raw_args)
        if parsed is None:
            return _usage()
        action, payload = parsed
        _enqueue(action, payload)
    except ValueError as exc:
        return f"RSS Reader: {exc}"
    except OSError as exc:
        return f"RSS Reader could not queue the command: {exc}"

    if action == "refresh":
        return "RSS Reader refresh queued."
    if action == "refresh-period":
        return f"RSS Reader refresh period change queued: every {payload['minutes']} minutes."
    if action == "mute":
        return f"RSS Reader mute queued for: {payload['phrase']}"
    if action == "refine":
        return f"RSS Reader refinement queued for the last {payload['days']} days."
    return f"RSS Reader subscription queued for {payload['source']}."


def register(ctx=None):
    if ctx is not None:
        ctx.register_command(
            "rss",
            handler=_handle,
            description="Control RSS Reader feeds, refresh, mutes, and grading preferences.",
            args_hint="refresh [XXm] | mute <keyword> | refine <XXd> | add <website> to <folder>",
            argument_mode="mixed",
        )
    return None


__all__ = ["register", "_handle", "_parse"]
