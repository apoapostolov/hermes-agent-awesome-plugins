"""Prices from the operator's own rate card, declared in the routing JSON.

The catalog edition cannot read the host rate card, so a price exists only when
the operator wrote one into the config under ``pricing``. An unpriced model keeps
``cost=None``, which makes the cache penalty estimate 0 and therefore never
holds a turn. A missing price never invents a number.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

# provider/model -> {"input": $/M, "output": $/M, "cache_read": $/M, "cache_write": $/M}
_RATES: dict[str, dict[str, float]] = {}
_FIELDS = ("input", "output", "cache_read", "cache_write", "cached")


def _rate(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _key(provider: str, model: str) -> str:
    return f"{str(provider or '').strip()}/{str(model or '').strip()}"


def set_rates(raw: Any) -> int:
    """Replace the rate card. Accepts ``{"provider/model": {...}}`` only."""
    _RATES.clear()
    if not isinstance(raw, Mapping):
        return 0
    for key, row in raw.items():
        if not isinstance(row, Mapping):
            continue
        name = str(key or "").strip()
        if "/" not in name:
            continue
        priced: dict[str, float] = {}
        for field in _FIELDS:
            value = _rate(row.get(field))
            if value is not None:
                priced["cache_read" if field == "cached" else field] = value
        if priced:
            _RATES[name] = priced
    return len(_RATES)


def cost_for(provider: str, model: str) -> Optional[dict]:
    """Per-million rates for one model, or None when the operator did not price it."""
    if not model:
        return None
    row = _RATES.get(_key(provider, model))
    return dict(row) if row else None


def supports_reasoning(provider: str, model: str) -> bool:
    """No capability table without a host read, so reasoning support stays unknown."""
    return False


def forget() -> None:
    _RATES.clear()
