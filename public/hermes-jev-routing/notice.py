"""The line shown after a user prompt, and whether the strip should interrupt."""

from __future__ import annotations

from typing import Optional


def format_jev_line(decision, analysis=None) -> str:
    target = decision.target
    parts = [f"tier {decision.tier}", f"{target.provider}/{target.model}"]
    if target.thinking_level:
        parts.append(f"thinking {target.thinking_level}")
    if analysis is None:
        return " · ".join(parts)
    parts.extend(
        [
            f"kind {analysis.kind}",
            f"complexity {analysis.complexity:.2f}/3",
            f"capability {analysis.budget_intensity:.2f}/3",
            f"reasoning {analysis.deep_reasoning:.2f}/1",
        ]
    )
    return " · ".join(parts)


def should_interrupt(decision, current, confirm_tiers, mode: str = "auto") -> bool:
    """The strip interrupts when the weight wants a different model."""
    if decision is None or mode in {"off", "shadow", "notify"}:
        return False
    changed = current is None or current.provider != decision.target.provider or current.id != decision.target.model
    if not changed:
        return False
    if mode == "confirm":
        return True
    return decision.tier in set(confirm_tiers)


def route_payload(decision, current, config, session_id: str, analysis=None, mode: str = "auto", glyph: str = "", prompt: str = "", status: str = "", held: bool = False) -> Optional[dict]:
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
    changed = current is None or current.provider != decision.target.provider or current.id != decision.target.model
    return {
        "session_id": session_id,
        "line": f"{glyph} {format_jev_line(decision, analysis)}".strip(),
        "glyph": glyph,
        "prompt": prompt[:80],
        "status": status,
        "held": bool(held),
        "owed_prompt": prompt if held else "",
        "apply": bool(changed and mode == "auto" and not should_interrupt(decision, current, config.confirm_tiers, mode)),
        "interrupt": should_interrupt(decision, current, config.confirm_tiers, mode),
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
