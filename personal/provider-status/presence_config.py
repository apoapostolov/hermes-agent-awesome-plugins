"""Settings for the Discord presence publisher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PLUGIN_ID = "provider-status"

MODES = ("rotate", "compact")
ACTIVITY_TYPES = ("custom", "playing", "watching", "listening", "competing")

_DEFAULT_MODE = "compact"
_DEFAULT_ACTIVITY = "custom"
_DEFAULT_INTERVAL = 20
_DEFAULT_EMOJI = "📊"

# One lead glyph per presence line, in the order segments render. These are the
# defaults; each line has its own ``discord_emoji_*`` setting so a reader can
# tell the lines apart at a glance, which matters most in rotate mode where only
# one line shows at a time.
GLYPH_TPS = "⚡"
GLYPH_CACHE = "◎"
GLYPH_CONTEXT = "▤"
GLYPH_QUOTA = "◍"
GLYPH_BALANCE = "◈"
GLYPH_TOOL = "⧉"
GLYPH_MODEL = "☤"
GLYPH_LATENCY = "◷"
GLYPH_TOTALS = "Σ"


def _bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off", ""}:
            return False
    return default


def _int(value: Any, default: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _choice(value: Any, allowed: tuple, default: str) -> str:
    if isinstance(value, str) and value.strip().lower() in allowed:
        return value.strip().lower()
    return default


def _emoji(value: Any, default: str) -> str:
    """A line's lead glyph.

    An explicitly empty string is meaningful: it removes the glyph from that
    line. Only an unset (``None``) value falls back to the default.
    """
    if value is None:
        return default
    return str(value)[:8]


@dataclass(frozen=True)
class PresenceConfig:
    enabled: bool = True
    mode: str = _DEFAULT_MODE
    activity_type: str = _DEFAULT_ACTIVITY
    update_interval_seconds: int = _DEFAULT_INTERVAL
    status_emoji: str = _DEFAULT_EMOJI
    idle_after_seconds: int = 180
    context_warn_percent: int = 80
    quota_warn_remaining: int = 20

    # One glyph per line, in render order.
    emoji_tokens_per_second: str = GLYPH_TPS
    emoji_cache: str = GLYPH_CACHE
    emoji_context: str = GLYPH_CONTEXT
    emoji_quota: str = GLYPH_QUOTA
    emoji_balance: str = GLYPH_BALANCE
    emoji_tool: str = GLYPH_TOOL
    emoji_model: str = GLYPH_MODEL
    emoji_latency: str = GLYPH_LATENCY
    emoji_totals: str = GLYPH_TOTALS

    show_tokens_per_second: bool = True
    show_context: bool = True
    show_context_bar: bool = True
    show_quota: bool = True
    show_quota_bar: bool = True
    show_balance: bool = True
    show_cache_hit: bool = False
    show_tool: bool = False
    show_model: bool = False
    show_latency: bool = False
    show_totals: bool = False

    # Discord's member-list sidebar truncates the presence state well before the
    # 128-character cap, so the bar stays short: 5 cells reads at a glance where
    # 10 gets cut off. Widen it with discord_bar_width (3-20) when the status is
    # read somewhere with room, such as /pulse or a full profile.
    bar_width: int = 5
    fill: str = "▰"
    empty: str = "▱"
    separator: str = " · "

    @classmethod
    def from_ctx(cls, ctx: Any) -> PresenceConfig:
        get = getattr(ctx, "get_config", None)
        if get is None:
            return cls()

        def cfg(key: str, default: Any) -> Any:
            try:
                value = get(key, default)
            except Exception:
                return default
            return default if value is None else value

        return cls(
            enabled=_bool(cfg("discord_presence_enabled", True), True),
            mode=_choice(cfg("discord_presence_mode", _DEFAULT_MODE), MODES, _DEFAULT_MODE),
            activity_type=_choice(
                cfg("discord_activity_type", _DEFAULT_ACTIVITY), ACTIVITY_TYPES, _DEFAULT_ACTIVITY
            ),
            update_interval_seconds=_int(
                cfg("discord_update_interval_seconds", _DEFAULT_INTERVAL),
                _DEFAULT_INTERVAL,
                10,
                600,
            ),
            status_emoji=str(cfg("discord_status_emoji", _DEFAULT_EMOJI) or _DEFAULT_EMOJI)[:8],
            idle_after_seconds=_int(cfg("discord_idle_after_seconds", 180), 180, 10, 86_400),
            context_warn_percent=_int(cfg("discord_context_warn_percent", 80), 80, 10, 100),
            quota_warn_remaining=_int(cfg("discord_quota_warn_remaining", 20), 20, 1, 50),
            emoji_tokens_per_second=_emoji(
                cfg("discord_emoji_tokens_per_second", GLYPH_TPS), GLYPH_TPS
            ),
            emoji_cache=_emoji(cfg("discord_emoji_cache", GLYPH_CACHE), GLYPH_CACHE),
            emoji_context=_emoji(cfg("discord_emoji_context", GLYPH_CONTEXT), GLYPH_CONTEXT),
            emoji_quota=_emoji(cfg("discord_emoji_quota", GLYPH_QUOTA), GLYPH_QUOTA),
            emoji_balance=_emoji(cfg("discord_emoji_balance", GLYPH_BALANCE), GLYPH_BALANCE),
            emoji_tool=_emoji(cfg("discord_emoji_tool", GLYPH_TOOL), GLYPH_TOOL),
            emoji_model=_emoji(cfg("discord_emoji_model", GLYPH_MODEL), GLYPH_MODEL),
            emoji_latency=_emoji(cfg("discord_emoji_latency", GLYPH_LATENCY), GLYPH_LATENCY),
            emoji_totals=_emoji(cfg("discord_emoji_totals", GLYPH_TOTALS), GLYPH_TOTALS),
            show_tokens_per_second=_bool(cfg("discord_show_tokens_per_second", True), True),
            show_context=_bool(cfg("discord_show_context", True), True),
            show_context_bar=_bool(cfg("discord_show_context_bar", True), True),
            show_quota=_bool(cfg("discord_show_quota", True), True),
            show_quota_bar=_bool(cfg("discord_show_quota_bar", True), True),
            show_balance=_bool(cfg("discord_show_balance", True), True),
            show_cache_hit=_bool(cfg("discord_show_cache_hit", False), False),
            show_tool=_bool(cfg("discord_show_tool", False), False),
            show_model=_bool(cfg("discord_show_model", False), False),
            show_latency=_bool(cfg("discord_show_latency", False), False),
            show_totals=_bool(cfg("discord_show_totals", False), False),
            bar_width=_int(cfg("discord_bar_width", 5), 5, 3, 20),
            fill=str(cfg("discord_bar_fill", "▰") or "▰")[:2],
            empty=str(cfg("discord_bar_empty", "▱") or "▱")[:2],
            separator=str(cfg("discord_separator", " · ") or " · ")[:8],
        )


# ── manifest mirror ──────────────────────────────────────────────────────────
# The plugin.yaml config_schema is what the Desktop renders; this mapping is the
# single place that documents the same keys for readers of the source. Keep the
# two in sync — plugin.yaml is authoritative for the UI.

CONFIG_SCHEMA: dict = {
    "discord_presence_enabled": {
        "type": "bool",
        "default": True,
        "description": "Publish live session telemetry as the Discord bot presence",
    },
    "discord_presence_mode": {
        "type": "str",
        "choices": list(MODES),
        "default": _DEFAULT_MODE,
        "description": "compact = every metric on one line; rotate = one metric per update",
    },
    "discord_activity_type": {
        "type": "str",
        "choices": list(ACTIVITY_TYPES),
        "default": _DEFAULT_ACTIVITY,
        "description": "Discord activity kind",
    },
    "discord_update_interval_seconds": {
        "type": "int",
        "default": _DEFAULT_INTERVAL,
        "description": "Seconds between presence updates (10-600)",
    },
    "discord_status_emoji": {
        "type": "str",
        "default": _DEFAULT_EMOJI,
        "description": "Emoji for the idle and thinking states (each metric line has its own)",
    },
    "discord_idle_after_seconds": {
        "type": "int",
        "default": 180,
        "description": "Show the idle dot after this long without activity",
    },
    "discord_context_warn_percent": {
        "type": "int",
        "default": 80,
        "description": "Context occupancy that switches the presence to dnd",
    },
    "discord_quota_warn_remaining": {
        "type": "int",
        "default": 20,
        "description": "Remaining quota percent that switches the presence to dnd",
    },
    "discord_emoji_tokens_per_second": {
        "type": "str",
        "default": GLYPH_TPS,
        "description": "Lead emoji for the tokens/sec line",
    },
    "discord_show_tokens_per_second": {
        "type": "bool",
        "default": True,
        "description": "Show tokens/sec",
    },
    "discord_emoji_cache": {
        "type": "str",
        "default": GLYPH_CACHE,
        "description": "Lead emoji for the cache-hit line",
    },
    "discord_show_cache_hit": {
        "type": "bool",
        "default": False,
        "description": "Show prompt-cache hit rate",
    },
    "discord_emoji_context": {
        "type": "str",
        "default": GLYPH_CONTEXT,
        "description": "Lead emoji for the context line",
    },
    "discord_show_context": {
        "type": "bool",
        "default": True,
        "description": "Show context usage",
    },
    "discord_show_context_bar": {
        "type": "bool",
        "default": True,
        "description": "Draw the context bar",
    },
    "discord_emoji_quota": {
        "type": "str",
        "default": GLYPH_QUOTA,
        "description": "Lead emoji for the quota line",
    },
    "discord_show_quota": {
        "type": "bool",
        "default": True,
        "description": "Show current-provider quota",
    },
    "discord_show_quota_bar": {
        "type": "bool",
        "default": True,
        "description": "Draw the quota bar",
    },
    "discord_emoji_balance": {
        "type": "str",
        "default": GLYPH_BALANCE,
        "description": "Lead emoji for the credit-balance line",
    },
    "discord_show_balance": {
        "type": "bool",
        "default": True,
        "description": "Show credit balance when the provider reports dollars",
    },
    "discord_emoji_tool": {
        "type": "str",
        "default": GLYPH_TOOL,
        "description": "Lead emoji for the running-tool line",
    },
    "discord_show_tool": {
        "type": "bool",
        "default": False,
        "description": "Show the running tool",
    },
    "discord_emoji_model": {
        "type": "str",
        "default": GLYPH_MODEL,
        "description": "Lead emoji for the model line",
    },
    "discord_show_model": {
        "type": "bool",
        "default": False,
        "description": "Show the active model",
    },
    "discord_emoji_latency": {
        "type": "str",
        "default": GLYPH_LATENCY,
        "description": "Lead emoji for the latency line",
    },
    "discord_show_latency": {
        "type": "bool",
        "default": False,
        "description": "Show mean request latency",
    },
    "discord_emoji_totals": {
        "type": "str",
        "default": GLYPH_TOTALS,
        "description": "Lead emoji for the lifetime-tokens line",
    },
    "discord_show_totals": {
        "type": "bool",
        "default": False,
        "description": "Show lifetime token totals",
    },
    "discord_bar_width": {"type": "int", "default": 5, "description": "Bar cells (3-20)"},
    "discord_separator": {"type": "str", "default": " · ", "description": "Segment separator"},
}


def describe(config: PresenceConfig | None = None) -> str:
    cfg = config or PresenceConfig()
    return (
        f"provider-status presence: {'on' if cfg.enabled else 'off'} · {cfg.mode} · "
        f"{cfg.activity_type} · every {cfg.update_interval_seconds}s"
    )
