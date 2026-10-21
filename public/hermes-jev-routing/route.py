"""Request-level routing. Nothing here reaches into a running agent.

The catalog edition can only change what the next provider request carries:
the model id on the client already bound to the turn, and the reasoning level
when the request has a wire field for it. It cannot open another provider and
it cannot stop a send, so a cross-provider pick is reported and left alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

TIERS = ("quick", "standard", "high", "premium", "xpremium")
# Wire fields that carry a reasoning level. Set only a field the request already
# has: adding one to a provider that does not accept it fails the send.
REASONING_FIELDS = ("reasoning_effort", "reasoning")


@dataclass(frozen=True)
class BoundModel:
    """The model the turn was built for. `provider` is empty when unknown."""

    provider: str
    id: str


def current_from(kwargs: Mapping[str, Any]) -> Optional[BoundModel]:
    """The active model, from the hook payload alone."""
    model = str(kwargs.get("model") or "")
    if not model:
        return None
    return BoundModel(provider="", id=model)


def current_from_request(kwargs: Mapping[str, Any]) -> Optional[BoundModel]:
    """The bound provider and model, from the middleware payload."""
    provider = str(kwargs.get("provider") or "")
    request = kwargs.get("request") or {}
    model = str(request.get("model") or kwargs.get("model") or "") if isinstance(request, Mapping) else ""
    if not provider or not model:
        return None
    return BoundModel(provider=provider, id=model)


def tier_index_for(config: Any, provider: str, model_id: str) -> Optional[int]:
    """The tier whose chain holds this model. A provider match wins when known."""
    if not model_id:
        return None
    loose: Optional[int] = None
    for index, tier in enumerate(TIERS):
        for target in config.routes.get(tier) or ():
            if target.model != model_id:
                continue
            if provider and target.provider == provider:
                return index
            if loose is None:
                loose = index
    return loose


def sticky_keep(config: Any, current: Optional[BoundModel], decision) -> bool:
    """Keep the current model when it is already the pick and stickiness is on."""
    if not getattr(config, "stickiness", True) or current is None or decision is None:
        return False
    if current.id != decision.target.model:
        return False
    return current.provider == decision.target.provider if current.provider else True


def crosses_provider(decision, bound_provider: str) -> bool:
    return bool(decision is not None and bound_provider and decision.target.provider != bound_provider)


def rewrite(
    request: Mapping[str, Any], decision, bound_provider: str, mode: str = "auto"
) -> Optional[dict]:
    """Return a rewritten request, or None when this edition cannot send the pick."""
    if mode != "auto" or decision is None or decision.held or decision.model is None:
        return None
    if decision.target.provider != bound_provider:
        return None
    updated = dict(request)
    updated["model"] = decision.target.model
    level = str(decision.target.thinking_level or "").strip().lower()
    if level and level not in {"off", "none", "false", "disabled"}:
        for field in REASONING_FIELDS:
            if field in updated:
                updated[field] = level
                break
    return updated


def action_glyph(*, sticky: bool, status: str, mode: str) -> str:
    if sticky:
        return "="
    if mode == "notify":
        return "."
    if status == "applied":
        return ">"
    return "x"
