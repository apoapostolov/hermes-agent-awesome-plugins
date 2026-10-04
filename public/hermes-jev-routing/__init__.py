"""Hermes plugin. Shadow by default.

In auto mode the personal edition reaches the cached agent and calls
switch_model before the client sends. A tier listed in confirm.tiers is not
switched. llm_request can still rewrite the model id when the pick stays on
the provider already bound to the turn.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

try:
    from .config import load_router_config, models_from_config
    from .decide import Analysis, Decision, decide, same_provider_rewrite
    from .jev import JevError, classify
    from .quota import codex_eligibility
    from .quota_live import read_codex_remaining
    from .switch import current_model, find_live_agent, maybe_switch, tier_index_for
except ImportError:
    from config import load_router_config, models_from_config
    from decide import Analysis, Decision, decide, same_provider_rewrite
    from jev import JevError, classify
    from quota import codex_eligibility
    from quota_live import read_codex_remaining
    from switch import current_model, find_live_agent, maybe_switch, tier_index_for

logger = logging.getLogger(__name__)

_LAST: dict[str, object] = {"mode": "shadow"}
_LOADED: dict[str, object] = {}


def last_decision() -> dict[str, object]:
    return dict(_LAST)


def _mode(ctx) -> str:
    try:
        mode = str(ctx.get_config("mode", "shadow") or "shadow").strip().lower()
    except Exception:
        mode = "shadow"
    if mode not in {"off", "shadow", "auto"}:
        return "shadow"
    return mode


def _config_path(ctx) -> str:
    try:
        return str(ctx.get_config("config_path", "") or "").strip()
    except Exception:
        return ""


def _load(path: str):
    file = Path(path)
    if not file.is_file():
        return None, None
    stamp = file.stat().st_mtime
    if _LOADED.get("path") == path and _LOADED.get("mtime") == stamp:
        return _LOADED["config"], _LOADED["settings"]
    config, settings = load_router_config(file)
    _LOADED.update(path=path, mtime=stamp, config=config, settings=settings)
    return config, settings


def _history(messages, turns: int) -> str:
    if not isinstance(messages, list):
        return ""
    lines: list[str] = []
    for message in messages[-max(turns, 0) * 2 :]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        content = message.get("content")
        if role in {"user", "assistant"} and isinstance(content, str) and content.strip():
            lines.append(f"{role}: {content.strip()}")
    return "\n".join(lines)[-4000:]


def on_pre_llm_call(**kwargs):
    mode = str(_LAST.get("mode") or "shadow")
    _LAST["blocked"] = ""
    _LAST["applied"] = ""
    _LAST["decision"] = None
    if mode == "off":
        return None
    path = str(_LAST.get("config_path") or "")
    prompt = str(kwargs.get("user_message") or "").strip()
    if not path or not prompt:
        return None
    try:
        config, settings = _load(path)
        if config is None or settings is None or len(prompt) < config.min_prompt_chars:
            return None
        key = os.environ.get(settings.api_key_env, "")
        endpoint = os.environ.get(settings.endpoint_env, "") or settings.endpoint
        active = str(kwargs.get("model") or "")
        agent = find_live_agent(str(kwargs.get("session_id") or ""))
        current = current_model(agent) if agent is not None else None
        analysis = classify(
            prompt,
            api_key=key,
            endpoint=endpoint,
            jev_model=settings.jev_model,
            task_kinds=settings.task_kinds,
            timeout_ms=settings.timeout_ms,
            history=_history(kwargs.get("conversation_history"), settings.history_turns),
            active_model=active,
        )
        gate = codex_eligibility(config, read_codex_remaining(), now_ms=time.time() * 1000)
        decision = decide(
            analysis,
            config,
            models_from_config(config),
            current_index=tier_index_for(config, current.provider, current.id) if current else None,
            current_model=current,
            eligibility=gate,
        )
        _LAST["decision"] = decision
        _LAST["quota_notes"] = list(getattr(gate, "notes", ()))
        hold_confirm = (
            decision is not None
            and decision.tier in set(config.confirm_tiers)
            and config.confirm_on_timeout != "accept"
        )
        if hold_confirm:
            _LAST["blocked"] = "confirm"
            switched = "skip"
        else:
            switched = maybe_switch(decision, str(kwargs.get("session_id") or ""), mode)
        if switched == "switched":
            _LAST["applied"] = decision.target.model if decision else ""
        elif switched in {"missing-agent", "switch-failed"}:
            _LAST["blocked"] = switched
    except (JevError, OSError, TimeoutError, ValueError):
        logger.warning("hermes-jev-routing left the turn unrouted", exc_info=True)
    return None


def on_llm_request(**kwargs):
    mode = str(_LAST.get("mode") or "shadow")
    decision = _LAST.get("decision")
    if mode == "off" or not isinstance(decision, Decision) or _LAST.get("blocked") == "confirm":
        return None
    request = kwargs.get("request") or {}
    bound = str(kwargs.get("provider") or "")
    try:
        rewritten = same_provider_rewrite(request, decision, bound, mode)
    except Exception:
        logger.warning("hermes-jev-routing left the request unchanged", exc_info=True)
        return None
    if rewritten is None:
        if mode == "auto" and not decision.held and decision.target.provider != bound and not _LAST.get("applied"):
            _LAST["blocked"] = _LAST.get("blocked") or "cross-provider"
        return None
    _LAST["applied"] = rewritten.get("model")
    return {
        "request": rewritten,
        "source": "hermes-jev-routing",
        "reason": decision.reason,
    }


def _command(raw: str = "") -> str:
    parts = str(raw or "").split()
    if parts[:1] == ["suggest"]:
        path = str(_LAST.get("config_path") or "")
        if not path:
            return "hermes-jev-routing suggest: no config path"
        try:
            from .ranking import suggestion_text
        except ImportError:
            from ranking import suggestion_text
        return suggestion_text(path, write="--write" in parts)
    return _status()


def _status() -> str:
    decision = _LAST.get("decision")
    if not isinstance(decision, Decision):
        return f"hermes-jev-routing {_LAST.get('mode', 'shadow')}: no decision yet"
    target = f"{decision.target.provider}/{decision.target.model}"
    held = " held" if decision.held else ""
    blocked = _LAST.get("blocked")
    extra = f" blocked:{blocked}" if blocked else ""
    return f"hermes-jev-routing {_LAST.get('mode', 'shadow')}{held}: {decision.reason} -> {target}{extra}"


def remember(decision: Decision | None, mode: str) -> None:
    _LAST.clear()
    _LAST["mode"] = mode
    if decision is not None:
        _LAST["decision"] = decision


def classify_for_tests(analysis: Analysis, config, models, mode: str, **kwargs) -> Decision | None:
    decision = decide(analysis, config, models, **kwargs)
    remember(decision, mode)
    return decision


def register(ctx):
    _LAST["mode"] = _mode(ctx)
    _LAST["config_path"] = _config_path(ctx)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_middleware("llm_request", on_llm_request)
    ctx.register_command("jev-routing", _command, description="Show the last decision, or suggest from a scores file")
    return None
