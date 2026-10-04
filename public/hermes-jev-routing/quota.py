"""Quota floors for a provider reading.

A reading maps a window name to remaining ratio, 0 to 1. None means the
window was not reported. A missing reading follows on_unknown: use admits
the model, skip rejects it. Equality passes. The stricter of the provider
floor and the target floor wins.
"""

from __future__ import annotations

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


def quota_allows(
    reading: Optional[Mapping[str, Optional[float]]],
    floors: Mapping[str, float],
    on_unknown: str = "use",
) -> bool:
    if not floors:
        return True
    if reading is None:
        return on_unknown != "skip"
    for window, floor in floors.items():
        remaining = reading.get(window)
        if remaining is None:
            if on_unknown == "skip":
                return False
            continue
        if float(remaining) < float(floor):
            return False
    return True


def codex_eligibility(config, reading: Optional[Mapping[str, Optional[float]]]):
    """Return a decide() eligibility callback. Non-Codex targets always pass."""

    def eligible(target, _model) -> bool:
        if target.provider != "openai-codex":
            return True
        floors = stricter(config.quota_floors.get("openai-codex"), target.min_quota)
        if not floors:
            return True
        return quota_allows(reading, floors, config.quota_on_unknown.get("openai-codex", "use"))

    return eligible
