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


def hold_for_approval(agent, prompt: str, reason: str) -> bool:
    """Stop the turn now and re-send the original prompt on the accepted model.

    A confirm tier must not answer on the model the user did not approve. This
    interrupts the in-flight send and queues the prompt, so an approval click
    runs the same request on the picked model instead of the held one.
    """
    if agent is None:
        return False
    steer = getattr(agent, "steer", None)
    if not callable(steer) or not prompt:
        return False
    try:
        steer(prompt)
    except Exception:
        return False
    return request_hold(agent, reason)


def should_hold_send(decision, switched: str, current, gate) -> bool:
    """Hold when this turn would still send on a quota-ineligible model."""
    if current_allowed(gate, current):
        return False
    if decision is None:
        return True
    return switched != "switched"


def request_hold(agent, reason: str) -> bool:
    """Set the interrupt both API paths check before they open a socket."""
    interrupt = getattr(agent, "interrupt", None)
    if callable(interrupt):
        try:
            interrupt(reason)
        except Exception:
            return False
    else:
        try:
            agent._interrupt_requested = True
            agent._interrupt_message = reason
        except Exception:
            return False
    original = getattr(agent, "_interruptible_api_call", None)
    if callable(original) and not getattr(original, "_jev_hold", False):
        def wrapped(*args, **kwargs):
            if getattr(agent, "_interrupt_requested", False):
                raise InterruptedError(reason)
            return original(*args, **kwargs)
        wrapped._jev_hold = True
        try:
            agent._interruptible_api_call = wrapped
        except Exception:
            pass
    return True


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
