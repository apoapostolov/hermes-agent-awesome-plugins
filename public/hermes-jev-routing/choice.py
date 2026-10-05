"""A confirm click names a target. It does not classify the turn."""

from __future__ import annotations

from typing import Optional

try:
    from .decide import Decision, RouteTarget
except ImportError:
    from decide import Decision, RouteTarget

MARKER = "jev-confirm:"
KEEP = {"no", "n", "x", "dismiss"}
ACCEPT = {"yes", "y"}
FREE = {"free", "0"}


def parse_confirm_choice(prompt: str) -> Optional[str]:
    text = str(prompt or "").strip()
    if not text.lower().startswith(MARKER):
        return None
    choice = text.split(":", 1)[1].strip().lower()
    return choice or None


def target_for_choice(config, choice: str, previous: Optional[Decision] = None) -> Optional[RouteTarget]:
    if choice in KEEP:
        return None
    if choice in ACCEPT:
        return previous.target if previous is not None else None
    if choice in FREE:
        pool = config.free.pool if config.free.enabled else ()
        return pool[0] if pool else None
    for tier, chain in config.routes.items():
        if choice == str(tier).lower() and chain:
            return chain[0]
    for kind, chain in config.kind_models.items():
        if choice == str(kind).lower() and chain:
            return chain[0]
    return None


def decision_for_target(target: RouteTarget) -> Decision:
    tier = target.min_tier or "quick"
    return Decision(
        desired_tier=tier,
        tier=tier,
        target=target,
        model=None,
        tier_index=0,
        demand_score=0,
        budget_pressure=0,
        downgraded=False,
        low_confidence_fallback=False,
        kind_specialised=False,
        held=False,
        reason="confirm choice",
        notes=(),
    )
