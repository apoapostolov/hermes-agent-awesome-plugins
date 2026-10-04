"""Quota floors for a Codex reading.

A window is known only when the snapshot is inside its cache TTL and the
window has not reset. A missing, stale, or reset window follows on_unknown.
Equality passes. The stricter of the provider floor and the row floor wins.
A disabled block does not gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

WINDOW_ALIASES = {
    "fivehour": "fiveHour",
    "five_hour": "fiveHour",
    "5h": "fiveHour",
    "session": "fiveHour",
    "current session": "fiveHour",
    "weekly": "weekly",
    "week": "weekly",
    "current week": "weekly",
    "seven_day": "weekly",
}
WINDOW_SECONDS = {18000: "fiveHour", 604800: "weekly"}


def canonical_window(name: str) -> str:
    key = str(name or "").strip().lower()
    return WINDOW_ALIASES.get(key, name)


def stricter(*groups: Optional[Mapping[str, float]]) -> dict[str, float]:
    floors: dict[str, float] = {}
    for group in groups:
        if not group:
            continue
        for name, value in group.items():
            window = canonical_window(str(name))
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            floors[window] = max(floors.get(window, 0.0), number)
    return floors


@dataclass(frozen=True)
class QuotaReading:
    remaining: float
    reset_at: Optional[float] = None


@dataclass(frozen=True)
class QuotaSnapshot:
    fetched_at: float
    windows: Mapping[str, QuotaReading] = field(default_factory=dict)


def parse_codex_payload(payload: object, now_ms: float) -> QuotaSnapshot:
    """Window duration, not position, names the window. Keep the lower remaining."""
    limits = payload.get("rate_limit") if isinstance(payload, Mapping) else None
    if not isinstance(limits, Mapping):
        limits = {}
    windows: dict[str, QuotaReading] = {}
    for key in ("primary_window", "secondary_window"):
        raw = limits.get(key)
        if not isinstance(raw, Mapping):
            continue
        name = WINDOW_SECONDS.get(raw.get("limit_window_seconds"))
        used = raw.get("used_percent")
        if not name or not isinstance(used, (int, float)) or used < 0 or used > 100:
            continue
        reset = raw.get("reset_at")
        reading = QuotaReading(
            remaining=(100 - float(used)) / 100,
            reset_at=float(reset) * 1000 if isinstance(reset, (int, float)) and reset > 0 else None,
        )
        current = windows.get(name)
        if current is None or reading.remaining < current.remaining:
            windows[name] = reading
    return QuotaSnapshot(fetched_at=now_ms, windows=windows)


def snapshot_from_remaining(reading, now_ms: float):
    if reading is None:
        return None
    if isinstance(reading, QuotaSnapshot):
        return reading
    windows = {
        canonical_window(str(name)): QuotaReading(remaining=float(value))
        for name, value in reading.items()
        if value is not None
    }
    return QuotaSnapshot(fetched_at=now_ms, windows=windows)


def evaluate_codex(target, *, enabled, floors, on_unknown, ttl_sec, snapshot, now_ms):
    if getattr(target, "provider", "") != "openai-codex" or not enabled:
        return True, []
    combined = stricter(floors, getattr(target, "min_quota", None))
    if not combined:
        return True, []
    allowed = True
    notes = []
    fresh = (
        snapshot is not None
        and now_ms >= snapshot.fetched_at
        and now_ms - snapshot.fetched_at < max(1, ttl_sec) * 1000
    )
    for window, floor in combined.items():
        if floor <= 0:
            continue
        reading = snapshot.windows.get(window) if snapshot is not None else None
        known = (
            fresh
            and reading is not None
            and (reading.reset_at is None or now_ms < reading.reset_at)
        )
        if not known:
            skip = on_unknown == "skip"
            if skip:
                allowed = False
            notes.append(
                f"{target.model} {'skipped' if skip else 'admitted'}: codex {window} quota unknown; onUnknown={on_unknown}"
            )
        elif reading.remaining < floor:
            allowed = False
            notes.append(
                f"{target.model} skipped: codex {window} {reading.remaining * 100:.1f}% < {floor * 100:.1f}%"
            )
    return allowed, notes


def quota_allows(reading, floors, on_unknown="use", now_ms=0):
    allowed, _notes = evaluate_codex(
        type("T", (), {"provider": "openai-codex", "model": "codex", "min_quota": None})(),
        enabled=True,
        floors=floors,
        on_unknown=on_unknown,
        ttl_sec=120,
        snapshot=snapshot_from_remaining(reading, now_ms),
        now_ms=now_ms,
    )
    return allowed


def codex_eligibility(config, reading, now_ms=0):
    """Return a decide() callback. A plain remaining map is treated as fresh."""
    notes = []
    snapshot = snapshot_from_remaining(reading, now_ms)
    enabled = bool(config.quota_enabled.get("openai-codex", bool(config.quota_floors.get("openai-codex"))))

    def eligible(target, _model):
        allowed, extra = evaluate_codex(
            target,
            enabled=enabled,
            floors=config.quota_floors.get("openai-codex") or {},
            on_unknown=config.quota_on_unknown.get("openai-codex", "use"),
            ttl_sec=int(config.quota_ttl_sec.get("openai-codex", 120)),
            snapshot=snapshot,
            now_ms=now_ms,
        )
        notes.extend(extra)
        return allowed

    eligible.notes = notes
    return eligible
