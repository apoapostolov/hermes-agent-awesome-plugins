"""Catalog edition. No agent lookup and no session switch."""

from __future__ import annotations

from typing import Any, Mapping, Optional


def find_live_agent(session_id: str, frames: Optional[Mapping[int, Any]] = None) -> Any:
    return None


def tier_index_for(config: Any, provider: str, model_id: str) -> Optional[int]:
    try:
        from .decide import TIERS
    except ImportError:
        from decide import TIERS

    for index, tier in enumerate(TIERS):
        for target in config.routes.get(tier) or ():
            if target.provider == provider and target.model == model_id:
                return index
    return None


def current_model(agent: Any) -> Any:
    return None


def maybe_switch(decision: Any, session_id: str, mode: str, frames: Optional[Mapping[int, Any]] = None) -> str:
    if mode != "auto" or decision is None or getattr(decision, "held", False):
        return "skip"
    return "missing-agent"
