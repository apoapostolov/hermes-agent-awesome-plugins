"""Live availability. A model the provider stopped serving must not win a chain."""

from __future__ import annotations

import logging
import threading
import time
from typing import Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

_TTL_S = 900.0
_lock = threading.Lock()
_cache: dict[str, tuple[float, frozenset[str]]] = {}


def read_ids(provider: str) -> list[str]:
    """Replaceable seam: the live provider catalogue."""
    from hermes_cli.models import cached_provider_model_ids

    return list(cached_provider_model_ids(provider, non_blocking=True))


def _known(provider: str) -> Optional[frozenset[str]]:
    """Ids the provider serves, or None when unknown (cold cache, error, no reader)."""
    key = provider.strip().lower()
    if not key:
        return None
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key)
        if hit is not None and now - hit[0] < _TTL_S:
            return hit[1]
    try:
        ids = read_ids(provider)
    except Exception:
        logger.debug("hermes-jev-routing could not read the %s catalogue", provider, exc_info=True)
        return None
    if not ids:
        return None
    known = frozenset(str(item) for item in ids)
    with _lock:
        _cache[key] = (now, known)
    return known


def live_models(configured):
    """Keep every target the provider still serves. Unknown providers keep everything."""
    try:
        from .decide import AvailableModel
    except ImportError:
        from decide import AvailableModel

    known_by_provider = {}
    kept = []
    for model in configured:
        known = known_by_provider.get(model.provider)
        if model.provider not in known_by_provider:
            known = _known(model.provider)
            known_by_provider[model.provider] = known
        if known is None or model.id in known:
            kept.append(AvailableModel(provider=model.provider, id=model.id))
        else:
            logger.info("hermes-jev-routing skipped %s/%s: not in the provider catalogue", model.provider, model.id)
    return tuple(kept)


def forget() -> None:
    with _lock:
        _cache.clear()


def configure_from(config) -> Mapping[str, object]:
    """Read the ranking knobs the JSON may override. Present for parity with the Pi config."""
    return {
        "cutoffs": dict(getattr(config, "ranking_cutoffs", {}) or {}),
        "spread": bool(getattr(config, "ranking_spread", True)),
        "scores_file": getattr(config, "ranking_scores_file", "") or "",
    }
