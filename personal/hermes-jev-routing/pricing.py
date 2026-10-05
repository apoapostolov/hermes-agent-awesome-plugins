"""Real prices and reasoning support, so the cache guard has something to price.

Personal edition only. Every failure returns None, and a None cost makes the
penalty estimate 0, so a missing price can never hold a turn.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TTL_S = 3600.0
_lock = threading.Lock()
_cache: dict[tuple[str, str], tuple[float, object]] = {}


def _rate(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def cost_for(provider: str, model: str) -> Optional[dict]:
    """Per-million rates for one model, or None when unpriced."""
    if not model:
        return None
    key = (provider.strip().lower(), model)
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < _TTL_S:
            return hit[1]
    try:
        from agent.usage_pricing import get_pricing_entry
    except Exception:
        return None
    try:
        entry = get_pricing_entry(model, provider=provider, api_key="")
    except Exception:
        logger.debug("hermes-jev-routing could not price %s/%s", provider, model, exc_info=True)
        return None
    if entry is None:
        return None
    rate_input = _rate(getattr(entry, "input_cost_per_million", None))
    if rate_input is None:
        # An unpriced row must stay unknown, not free.
        with _lock:
            _cache[key] = (now, None)
        return None
    cost = {
        "input": rate_input,
        "output": _rate(getattr(entry, "output_cost_per_million", None)) or 0.0,
        "cache_read": _rate(getattr(entry, "cache_read_cost_per_million", None)) or 0.0,
        "cache_write": _rate(getattr(entry, "cache_write_cost_per_million", None)) or 0.0,
    }
    with _lock:
        _cache[key] = (now, cost)
    return cost


def supports_reasoning(provider: str, model: str) -> bool:
    """Whether a thinking level means anything on this route."""
    if not model:
        return False
    try:
        from agent.model_metadata import get_model_capabilities
    except Exception:
        return False
    try:
        caps = get_model_capabilities(model, provider=provider)
    except Exception:
        return False
    if caps is None:
        return False
    for attr in ("reasoning", "supports_reasoning", "supports_thinking"):
        if getattr(caps, attr, None):
            return True
    return False


def forget() -> None:
    with _lock:
        _cache.clear()
