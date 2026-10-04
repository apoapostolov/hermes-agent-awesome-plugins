"""Read Codex remaining quota. Fail open when the host has no reading."""

from __future__ import annotations

import time
from typing import Optional

try:
    from .quota import QuotaReading, QuotaSnapshot, parse_codex_payload
except ImportError:
    from quota import QuotaReading, QuotaSnapshot, parse_codex_payload

_CACHE: dict[str, object] = {"value": None}
_TTL_S = 120.0


def _from_windows(snapshot, now_ms: float) -> Optional[QuotaSnapshot]:
    windows = getattr(snapshot, "windows", None) or ()
    parsed: dict[str, QuotaReading] = {}
    for window in windows:
        label = str(getattr(window, "label", "") or "").lower()
        used = getattr(window, "used_percent", None)
        key = "fiveHour" if "session" in label else "weekly" if "week" in label else ""
        if not key or used is None:
            continue
        reset = getattr(window, "reset_at", None)
        reset_ms = reset.timestamp() * 1000 if hasattr(reset, "timestamp") else None
        parsed[key] = QuotaReading(
            remaining=max(0.0, min(1.0, 1.0 - float(used) / 100.0)),
            reset_at=reset_ms,
        )
    if not parsed:
        return None
    fetched = getattr(snapshot, "fetched_at", None)
    fetched_ms = fetched.timestamp() * 1000 if hasattr(fetched, "timestamp") else now_ms
    return QuotaSnapshot(fetched_at=fetched_ms, windows=parsed)


def read_codex_remaining() -> Optional[QuotaSnapshot]:
    now = time.time()
    cached = _CACHE.get("value")
    if isinstance(cached, QuotaSnapshot) and now - cached.fetched_at / 1000 < _TTL_S:
        return cached
    try:
        from agent.account_usage import fetch_account_usage

        snapshot = fetch_account_usage("openai-codex")
    except Exception:
        return cached if isinstance(cached, QuotaSnapshot) else None
    raw = getattr(snapshot, "raw", None)
    reading = parse_codex_payload(raw, now * 1000) if isinstance(raw, dict) and raw else None
    if reading is None or not reading.windows:
        reading = _from_windows(snapshot, now * 1000)
    if reading is not None and reading.windows:
        _CACHE["value"] = reading
        return reading
    return cached if isinstance(cached, QuotaSnapshot) else None
