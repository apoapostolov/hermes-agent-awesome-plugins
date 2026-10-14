"""Provider Status — dashboard plugin plus Discord session presence.

Agent-plugin register wires observer hooks, a Discord presence publisher,
``/pulse``, the ``agent_pulse`` tool, and ``hermes session-pulse``. The
desktop UI stays in desktop/plugin.js and the quota backend in
dashboard/plugin_api.py.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from . import presence, pulse_tool, schemas
from .presence_config import PresenceConfig, describe
from .presence_metrics import DEFAULT_WINDOW, MetricsCollector

logger = logging.getLogger(__name__)

_collector: MetricsCollector | None = None
_config: PresenceConfig | None = None
_ctx: Any = None


def get_collector() -> MetricsCollector:
    global _collector
    if _collector is None:
        _collector = MetricsCollector(window=DEFAULT_WINDOW)
    return _collector


def get_config() -> PresenceConfig:
    global _config
    if _config is None:
        _config = PresenceConfig()
    return _config


def _set_config(config: PresenceConfig) -> None:
    global _config
    _config = config


def _on_pre_api_request(**kwargs: Any) -> None:
    get_collector().on_pre_api_request(**kwargs)


def _on_post_api_request(**kwargs: Any) -> None:
    get_collector().on_post_api_request(**kwargs)


def _on_api_request_error(**kwargs: Any) -> None:
    get_collector().on_api_request_error(**kwargs)


def _on_pre_tool_call(**kwargs: Any) -> None:
    get_collector().on_pre_tool_call(**kwargs)


def _on_post_tool_call(**kwargs: Any) -> None:
    get_collector().on_post_tool_call(**kwargs)


def _on_pre_llm_call(**kwargs: Any) -> None:
    get_collector().on_pre_llm_call(**kwargs)


def _on_post_llm_call(**kwargs: Any) -> None:
    get_collector().on_post_llm_call(**kwargs)


def _handle_pulse(raw_args: str) -> str:
    from . import presence_render as render

    collector = get_collector()
    config = get_config()
    snapshot = collector.snapshot()
    detail = (raw_args or "").strip().lower()
    if detail in {"config", "settings"}:
        return describe(config)
    if detail in {"full", "-v", "verbose"}:
        return render.render_report(snapshot, config) + "\n\n" + describe(config)
    return render.render_report(snapshot, config)


def _cli_command(args: Any) -> None:
    import json

    sub = str(getattr(args, "session_pulse_command", "") or "status").strip().lower()
    config = get_config()
    collector = get_collector()

    if sub in {"config", "settings"}:
        print(describe(config))
        for field, value in config.__dict__.items():
            print(f"  {field:<34} {value!r}")
        return

    if sub == "reset":
        collector.reset()
        print("provider-status: counters reset")
        return

    snapshot = collector.snapshot()
    print(describe(config))
    print(f"  publishers live        {presence.active_publishers()}")
    print(
        f"  state                  "
        f"{'thinking' if snapshot.inflight else snapshot.current_tool or 'idle'}"
    )
    print(f"  model                  {snapshot.model or '—'}")
    print(f"  provider               {snapshot.provider or '—'}")
    print(f"  tokens/sec (windowed)  {snapshot.tps:.1f} over {snapshot.requests} samples")
    print(f"  tokens/sec (last)      {snapshot.instant_tps:.1f}")
    cache = "—" if snapshot.cache_hit_pct is None else f"{snapshot.cache_hit_pct:.1f}%"
    print(f"  cache hit              {cache}")
    ctx_pct = "—" if snapshot.context_pct is None else f"{snapshot.context_pct:.1f}%"
    print(
        f"  context                {snapshot.context_used:,} / "
        f"{snapshot.context_length:,} ({ctx_pct})"
    )
    quota = snapshot.quota if isinstance(snapshot.quota, dict) else {}
    if quota:
        remaining = quota.get("remaining")
        balance = quota.get("balance")
        print(
            f"  quota                  {quota.get('name') or quota.get('id') or '—'} "
            f"{'' if remaining is None else f'{remaining:.0f}% left '}"
            f"{'' if balance is None else f'${balance:.2f}'}"
        )
    else:
        print("  quota                  —")
    print(f"  mean latency           {snapshot.latency:.3f}s")
    print(f"  api calls / errors     {snapshot.api_calls} / {snapshot.errors}")
    print(f"  compressions (est.)    {snapshot.compressions}")
    print(f"  lifetime tokens        {snapshot.total_tokens:,}")
    if sub == "json":
        print(json.dumps(snapshot.as_dict(), indent=2))


def _setup_argparse(subparser: Any) -> None:
    subs = subparser.add_subparsers(dest="session_pulse_command")
    subs.add_parser("status", help="Show live telemetry and presence state")
    subs.add_parser("json", help="Same, as raw JSON")
    subs.add_parser("config", help="Show the resolved settings")
    subs.add_parser("reset", help="Zero the counters")


def _register_read_surfaces(ctx: Any, *, enabled: bool) -> None:
    ctx.register_command(
        "pulse", _handle_pulse, description="Show live session telemetry and current-provider quota",
    )
    ctx.register_cli_command(
        name="session-pulse",
        help=(
            "Show live session telemetry (tokens/sec, context, quota)"
            if enabled
            else "Show live session telemetry (Discord presence is disabled)"
        ),
        setup_fn=_setup_argparse,
        handler_fn=_cli_command,
    )
    ctx.register_tool(
        name="agent_pulse",
        toolset="provider_status",
        schema=schemas.AGENT_PULSE,
        handler=pulse_tool.agent_pulse,
    )


def register(ctx=None):
    if ctx is None:
        return None

    global _ctx
    _ctx = ctx

    config = PresenceConfig.from_ctx(ctx)
    _set_config(config)

    if not config.enabled:
        logger.info("provider-status presence: disabled via settings — hooks stay inert")
        _register_read_surfaces(ctx, enabled=False)
        return None

    ctx.register_hook("pre_api_request", _on_pre_api_request)
    ctx.register_hook("post_api_request", _on_post_api_request)
    ctx.register_hook("api_request_error", _on_api_request_error)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("pre_llm_call", _on_pre_llm_call)
    ctx.register_hook("post_llm_call", _on_post_llm_call)

    def _wire_discord(bot: Any, adapter: Any) -> None:
        presence.wire(bot, adapter, get_collector(), get_config())

    ctx.register_platform_handler("discord", _wire_discord)
    _register_read_surfaces(ctx, enabled=True)

    skills_dir = Path(__file__).parent / "skills"
    for child in sorted(skills_dir.iterdir()) if skills_dir.is_dir() else []:
        skill_md = child / "SKILL.md"
        if child.is_dir() and skill_md.is_file():
            ctx.register_skill(child.name, skill_md)

    logger.info(
        "provider-status presence: armed (%s mode, %s activity, every %ss)",
        config.mode, config.activity_type, config.update_interval_seconds,
    )
    return None
