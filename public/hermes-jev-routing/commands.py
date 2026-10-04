"""Command text for why, revert, and a dry-run classify. None of these switch by themselves."""

from __future__ import annotations

from typing import Optional

try:
    from .decide import Analysis, Decision, Spend, decide
    from .ledger import format_usd
    from .notice import format_jev_line
except ImportError:
    from decide import Analysis, Decision, Spend, decide
    from ledger import format_usd
    from notice import format_jev_line


def explain(analysis: Optional[Analysis], decision: Optional[Decision], notes: tuple[str, ...] = ()) -> str:
    if analysis is None and decision is None:
        return "no routed prompt yet in this session"
    lines = []
    if analysis is not None:
        probs = getattr(analysis, "kind_probabilities", None) or {}
        ranked = ", ".join(
            f"{kind} {float(score) * 100:.0f}%"
            for kind, score in sorted(probs.items(), key=lambda item: float(item[1]), reverse=True)
        )
        lines.append(f"kind: {analysis.kind} (confidence {analysis.kind_confidence:.2f})")
        if ranked:
            lines.append(f"      {ranked}")
        lines.append(
            f"complexity: {analysis.complexity:.2f}/3 (conf {getattr(analysis, 'complexity_confidence', 0):.2f})"
        )
        lines.append(
            f"capability: {analysis.budget_intensity:.2f}/3 (conf {getattr(analysis, 'capability_confidence', 0):.2f})"
        )
        lines.append(f"reasoning: {analysis.deep_reasoning:.2f}")
        if getattr(analysis, "latency_ms", 0):
            lines.append(f"jev latency: {analysis.latency_ms}ms")
    if decision is None:
        lines.append("no route available")
    else:
        lines.append(format_jev_line(decision, analysis) if analysis is not None else format_jev_line(decision))
        if decision.reason:
            lines.append(decision.reason)
    lines.extend(note for note in notes if note)
    return "\n".join(lines)


def dry_run(analysis: Analysis, config, models, **kwargs) -> str:
    """Classify outcome only. The caller must not switch."""
    decision = decide(analysis, config, models, **kwargs)
    return explain(analysis, decision, tuple(getattr(decision, "notes", ()) or ()))


def spend_lines(snapshot) -> str:
    today = format_usd(snapshot.today)
    month = format_usd(snapshot.month)
    if snapshot.daily_cap:
        today = f"{today} / {format_usd(snapshot.daily_cap)}"
    if snapshot.monthly_cap:
        month = f"{month} / {format_usd(snapshot.monthly_cap)}"
    pressure = f"{snapshot.pressure * 100:.0f}%" if snapshot.pressure > 0 else "no caps set"
    return f"spend today: {today}\nspend month: {month}\nbudget pressure: {pressure}"


def revert_target(previous: Optional[dict]):
    if not isinstance(previous, dict):
        return None
    provider = str(previous.get("provider") or "")
    model = str(previous.get("model") or "")
    if not provider or not model:
        return None
    try:
        from .decide import RouteTarget
    except ImportError:
        from decide import RouteTarget
    return RouteTarget(provider=provider, model=model)
