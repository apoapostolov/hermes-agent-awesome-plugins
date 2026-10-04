"""Host workarounds that the hook return value cannot do by itself."""

from __future__ import annotations

from typing import Optional

try:
    from .decide import RouteTarget
except ImportError:
    from decide import RouteTarget


def sticky_keep(config, current, decision) -> bool:
    """Pi skips a re-apply when stickiness is on and the target is already active."""
    if not getattr(config, "stickiness", True) or current is None or decision is None:
        return False
    return current.provider == decision.target.provider and current.id == decision.target.model


def current_allowed(gate, current) -> bool:
    if current is None or gate is None:
        return True
    try:
        return bool(gate(RouteTarget(provider=current.provider, model=current.id), current))
    except Exception:
        return True


def should_hold_send(decision, switched: str, current, gate) -> bool:
    """Hold when this turn would still send on a quota-ineligible model."""
    if current_allowed(gate, current):
        return False
    if decision is None:
        return True
    return switched != "switched"


def request_hold(agent, reason: str) -> bool:
    """Set the interrupt the streaming call checks before it opens a socket."""
    interrupt = getattr(agent, "interrupt", None)
    if not callable(interrupt):
        return False
    try:
        interrupt(reason)
        return True
    except Exception:
        return False


def action_glyph(*, sticky: bool, switched: str, mode: str) -> str:
    if sticky:
        return "="
    if mode == "notify":
        return "."
    if switched == "switched":
        return ">"
    if switched in {"skip", "same"}:
        return "x"
    return "x"
