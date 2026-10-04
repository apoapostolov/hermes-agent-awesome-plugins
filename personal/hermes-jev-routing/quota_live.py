"""Read Codex remaining quota. Fail open when the host has no reading."""

from __future__ import annotations

import time
from typing import Optional

_CACHE: dict[str, object] = {"at": 0.0, "value": None}
_TTL_S = 120.0


def _remaining_from_snapshot(snapshot) -> Optional[dict[str, Optional[float]]]:
    windows = getattr(snapshot, "windows", None) or ()
    reading: dict[str, Optional[float]] = {}
    for window in windows:
        label = str(getattr(window, "label", "") or "")
        used = getattr(window, "used_percent", None)
        key = "fiveHour" if "session" in label.lower() else "weekly" if "week" in label.lower() else ""
        if not key or used is None:
            continue
        reading[key] = max(0.0, min(1.0, 1.0 - float(used) / 100.0))
    return reading or None


def read_codex_remaining() -> Optional[dict[str, Optional[float]]]:
    now = time.monotonic()
    if now - float(_CACHE["at"]) < _TTL_S and _CACHE["value"] is not None:
        return _CACHE["value"]  # type: ignore[return-value]
    try:
        from agent.account_usage import fetch_account_usage

        snapshot = fetch_account_usage("openai-codex")
    except Exception:
        return None
    reading = _remaining_from_snapshot(snapshot)
    if reading is not None:
        _CACHE["at"] = now
        _CACHE["value"] = reading
    return reading
