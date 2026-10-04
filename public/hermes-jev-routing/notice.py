"""The line shown after a user prompt, and whether the strip should interrupt."""

from __future__ import annotations

from typing import Optional


def format_jev_line(decision) -> str:
    target = decision.target
    parts = [str(decision.tier), f"{target.provider}/{target.model}"]
    if target.thinking_level:
        parts.append(str(target.thinking_level))
    if decision.reason:
        parts.append(str(decision.reason))
    return " · ".join(parts)


def should_interrupt(decision, current, confirm_tiers) -> bool:
    """The strip interrupts only when the weight wants a different model on a guarded tier."""
    if decision is None or decision.tier not in set(confirm_tiers):
        return False
    if current is None:
        return True
    return current.provider != decision.target.provider or current.id != decision.target.model


def route_payload(decision, current, config, session_id: str) -> Optional[dict]:
    if decision is None:
        return None
    heads = {}
    for tier, chain in config.routes.items():
        if not chain:
            continue
        row = chain[0]
        heads[str(tier)] = {
            "provider": row.provider,
            "model": row.model,
            "thinking": row.thinking_level,
        }
    free = None
    if config.free.enabled and config.free.pool:
        row = config.free.pool[0]
        free = {"provider": row.provider, "model": row.model, "thinking": row.thinking_level}
    return {
        "session_id": session_id,
        "line": format_jev_line(decision),
        "interrupt": should_interrupt(decision, current, config.confirm_tiers),
        "offered_tier": decision.tier,
        "provider": decision.target.provider,
        "model": decision.target.model,
        "thinking": decision.target.thinking_level,
        "heads": heads,
        "free": free,
    }


def publish_route(payload: Optional[dict]) -> None:
    if not payload:
        return
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event

        broadcast_plugin_event("hermes-jev-routing", "routed", payload)
    except Exception:
        return
