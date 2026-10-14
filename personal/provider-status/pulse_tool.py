"""Tool handlers for the session pulse."""

from __future__ import annotations

import json
from typing import Any

from . import presence_render as render
from .presence_config import PresenceConfig, describe
from .presence_metrics import MetricsCollector


def _collector() -> MetricsCollector:
    from . import get_collector

    return get_collector()


def _config() -> PresenceConfig:
    from . import get_config

    return get_config()


def agent_pulse(args: dict, **kwargs: Any) -> str:
    detail = str((args or {}).get("detail") or "summary").strip().lower()
    if detail not in {"summary", "full"}:
        detail = "summary"
    try:
        snapshot = _collector().snapshot()
        config = _config()
        quota = snapshot.quota if isinstance(snapshot.quota, dict) else {}
        payload: dict = {
            "ok": True,
            "detail": detail,
            "presence": render.render_status(snapshot, config),
            "state": (
                "thinking" if snapshot.inflight
                else f"running {snapshot.current_tool}" if snapshot.current_tool
                else "in_turn" if snapshot.turn_live
                else "idle"
            ),
            "model": snapshot.model,
            "provider": snapshot.provider,
            "platform": snapshot.platform,
            "tokens_per_second": round(snapshot.tps, 2),
            "tokens_per_second_last_request": round(snapshot.instant_tps, 2),
            "cache_hit_pct": (
                None if snapshot.cache_hit_pct is None else round(snapshot.cache_hit_pct, 2)
            ),
            "context_used_tokens": snapshot.context_used,
            "context_length_tokens": snapshot.context_length,
            "context_pct": (
                None if snapshot.context_pct is None else round(snapshot.context_pct, 2)
            ),
            "quota": quota or None,
            "mean_latency_seconds": round(snapshot.latency, 3),
            "current_tool": snapshot.current_tool or None,
            "window_samples": snapshot.requests,
        }
        if detail == "full":
            payload.update(
                {
                    "api_calls": snapshot.api_calls,
                    "errors": snapshot.errors,
                    "compressions_estimate": snapshot.compressions,
                    "total_tokens": snapshot.total_tokens,
                    "window_output_tokens": snapshot.output_tokens,
                    "idle_seconds": round(snapshot.idle_seconds(), 1),
                    "session_id": snapshot.session_id,
                    "presence_config": describe(config),
                    "report": render.render_report(snapshot, config),
                }
            )
        return json.dumps(payload)
    except Exception as exc:
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
