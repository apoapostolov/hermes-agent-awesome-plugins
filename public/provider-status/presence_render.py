"""Pure rendering: snapshot + config → the strings Discord shows."""

from __future__ import annotations

from .presence_metrics import Snapshot

GLYPH_TPS = "⚡"
GLYPH_CACHE = "◎"
GLYPH_TOOL = "⧉"
GLYPH_MODEL = "☤"
GLYPH_LATENCY = "◷"
GLYPH_TOTALS = "Σ"
GLYPH_QUOTA = "◍"

_MAX_STATUS = 110


def _compact_tokens(count: int) -> str:
    value = float(max(0, count))
    for limit, suffix in ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K")):
        if value >= limit:
            return f"{value / limit:.1f}{suffix}"
    return str(int(value))


def build_context_bar(pct: float | None, width: int, fill: str, empty: str) -> str:
    safe = 0.0 if pct is None else max(0.0, min(100.0, pct))
    filled = int(round((safe / 100.0) * max(1, width)))
    filled = max(0, min(width, filled))
    return f"{fill * filled}{empty * max(0, width - filled)}"


def _fmt_pct(value: float | None, precision: int = 1) -> str:
    return "--" if value is None else f"{value:.{precision}f}%"


def _quota_remaining(quota: dict | None) -> float | None:
    if not isinstance(quota, dict) or not quota.get("ok"):
        return None
    remaining = quota.get("remaining")
    try:
        if remaining is not None:
            return max(0.0, min(100.0, float(remaining)))
    except (TypeError, ValueError):
        pass
    return None


def _quota_balance(quota: dict | None) -> float | None:
    if not isinstance(quota, dict) or not quota.get("ok"):
        return None
    if quota.get("kind") != "credit":
        return None
    try:
        value = float(quota.get("balance"))
    except (TypeError, ValueError):
        return None
    return value


def _quota_label(quota: dict | None) -> str:
    if not isinstance(quota, dict):
        return ""
    return str(quota.get("name") or quota.get("id") or "").strip()


def segments(snapshot: Snapshot, config) -> list[tuple[str, str]]:
    sep = config.separator
    out: list[tuple[str, str]] = []

    if config.show_tokens_per_second and snapshot.tps > 0:
        out.append(("tps", f"{GLYPH_TPS} {snapshot.tps:.0f} tok/s"))
    if config.show_cache_hit and snapshot.cache_hit_pct is not None:
        out.append(("cache", f"{GLYPH_CACHE} {_fmt_pct(snapshot.cache_hit_pct, 0)} cache"))
    if config.show_context and snapshot.context_pct is not None:
        used = _compact_tokens(snapshot.context_used)
        total = _compact_tokens(snapshot.context_length)
        parts: list[str] = []
        if config.show_context_bar:
            parts.append(
                build_context_bar(snapshot.context_pct, config.bar_width, config.fill, config.empty)
            )
        parts.append(f"{snapshot.context_pct:.0f}% ctx")
        if total != "0":
            parts.append(f"{used}/{total}")
        out.append(("context", f"{sep.join(parts)}"))

    quota = snapshot.quota if isinstance(snapshot.quota, dict) else None
    remaining = _quota_remaining(quota)
    balance = _quota_balance(quota)
    label = _quota_label(quota)
    if config.show_quota and remaining is not None:
        used = max(0.0, min(100.0, 100.0 - remaining))
        parts = []
        if config.show_quota_bar:
            parts.append(build_context_bar(used, config.bar_width, config.fill, config.empty))
        name = label or "quota"
        parts.append(f"{remaining:.0f}% {name}")
        out.append(("quota", f"{GLYPH_QUOTA} {sep.join(parts)}"))
    if config.show_balance and balance is not None:
        name = label or "credits"
        out.append(("balance", f"{name} ${balance:.2f}"))

    if config.show_tool and snapshot.current_tool:
        out.append(("tool", f"{GLYPH_TOOL} {snapshot.current_tool}"))
    if config.show_latency and snapshot.latency > 0:
        out.append(("latency", f"{GLYPH_LATENCY} {snapshot.latency:.1f}s"))
    if config.show_model and snapshot.model:
        model = snapshot.model.split("/")[-1]
        if len(model) > 22:
            model = f"{model[:19]}..."
        out.append(("model", f"{GLYPH_MODEL} {model}"))
    if config.show_totals and snapshot.total_tokens > 0:
        out.append(("totals", f"{GLYPH_TOTALS} {_compact_tokens(snapshot.total_tokens)} tok"))
    return out


def idle_status(config, now: float, snapshot: Snapshot | None = None) -> str:
    if snapshot is not None and snapshot.inflight:
        return f"{config.status_emoji} thinking…"
    return f"{config.status_emoji} idle · waiting for you"


def rotate_status(snapshot: Snapshot, config, turn: int) -> str:
    parts = segments(snapshot, config)
    if not parts:
        return idle_status(config, 0.0, snapshot)
    if snapshot.inflight and not snapshot.current_tool:
        return f"{config.status_emoji} thinking…"
    return f"{config.status_emoji} {parts[turn % len(parts)][1]}"


def compact_status(snapshot: Snapshot, config) -> str:
    parts = [text for _, text in segments(snapshot, config)]
    if not parts:
        return idle_status(config, 0.0, snapshot)
    text = config.separator.join(parts)
    if len(text) > _MAX_STATUS:
        while parts and len(config.separator.join(parts)) > _MAX_STATUS:
            parts.pop()
        text = config.separator.join(parts) or text[:_MAX_STATUS]
    return f"{config.status_emoji} {text}"


def render_status(snapshot: Snapshot, config, turn: int = 0) -> str:
    if config.mode == "compact":
        return compact_status(snapshot, config)
    return rotate_status(snapshot, config, turn)


def presence_status(snapshot: Snapshot, config, now: float):
    remaining = _quota_remaining(snapshot.quota if isinstance(snapshot.quota, dict) else None)
    if remaining is not None and remaining <= config.quota_warn_remaining:
        return "dnd"
    if snapshot.context_pct is not None and snapshot.context_pct >= config.context_warn_percent:
        return "dnd"
    if snapshot.busy_at(now):
        return "online"
    if snapshot.idle_seconds(now) >= config.idle_after_seconds:
        return "idle"
    return "online"


def render_report(snapshot: Snapshot, config) -> str:
    lines: list[str] = ["**Hermes session pulse**", ""]

    state = (
        "thinking…" if snapshot.inflight
        else f"running `{snapshot.current_tool}`" if snapshot.current_tool
        else "in a turn" if snapshot.busy
        else "idle"
    )
    lines.append(f"State: **{state}**")
    if snapshot.model:
        route = f"{snapshot.provider}/{snapshot.model}" if snapshot.provider else snapshot.model
        lines.append(f"Model: `{route}`")
    lines.append("")

    if snapshot.tps > 0:
        lines.append(
            f"{GLYPH_TPS} **{snapshot.tps:.1f} tok/s** windowed "
            f"({snapshot.instant_tps:.1f} tok/s last request, {snapshot.requests} samples)"
        )
    if snapshot.cache_hit_pct is not None:
        lines.append(f"{GLYPH_CACHE} Cache hit: **{_fmt_pct(snapshot.cache_hit_pct)}**")
    if snapshot.context_pct is not None:
        bar = build_context_bar(
            snapshot.context_pct, config.bar_width * 2, config.fill, config.empty
        )
        lines.append(
            f"Context: `{bar}` **{snapshot.context_pct:.1f}%** "
            f"({snapshot.context_used:,} / {snapshot.context_length:,} tokens)"
        )
    quota = snapshot.quota if isinstance(snapshot.quota, dict) else None
    remaining = _quota_remaining(quota)
    balance = _quota_balance(quota)
    label = _quota_label(quota)
    if remaining is not None:
        used = max(0.0, min(100.0, 100.0 - remaining))
        bar = build_context_bar(used, config.bar_width * 2, config.fill, config.empty)
        lines.append(
            f"{GLYPH_QUOTA} {label or 'Quota'}: `{bar}` **{remaining:.0f}% left**"
        )
    if balance is not None:
        lines.append(f"Credits: **${balance:.2f}**")
    if snapshot.latency > 0:
        lines.append(f"{GLYPH_LATENCY} Mean latency: {snapshot.latency:.2f}s")
    lines.append("")
    lines.append(
        f"Session: {snapshot.api_calls} API calls · {snapshot.errors} errors · "
        f"{snapshot.compressions} compressions · "
        f"{GLYPH_TOTALS} {snapshot.total_tokens:,} tokens"
    )
    if snapshot.platform:
        lines.append(f"Surface: `{snapshot.platform}`")
    return "\n".join(lines)
