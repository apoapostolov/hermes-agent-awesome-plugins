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
    from .choice import decision_for_target, parse_confirm_choice, target_for_choice
    from .commands import explain, revert_target
    from .ledger import load_ledger, record_cost, record_jev, save_ledger, spend_snapshot, state_path, usage_cost
    from .notice import publish_route, route_payload
    from .quota import codex_eligibility
    from .quota_live import read_codex_remaining
    from .settings_override import apply_setting_overrides, present_settings
    from .switch import current_model, find_live_agent, maybe_switch, tier_index_for
except ImportError:
    from config import load_router_config, models_from_config
    from decide import Analysis, Decision, decide, same_provider_rewrite
    from jev import JevError, classify
    from choice import decision_for_target, parse_confirm_choice, target_for_choice
    from commands import explain, revert_target
    from ledger import load_ledger, record_cost, record_jev, save_ledger, spend_snapshot, state_path, usage_cost
    from notice import publish_route, route_payload
    from quota import codex_eligibility
    from quota_live import read_codex_remaining
    from settings_override import apply_setting_overrides, present_settings
    from switch import current_model, find_live_agent, maybe_switch, tier_index_for

logger = logging.getLogger(__name__)

_LAST: dict[str, object] = {"mode": "shadow"}
_LOADED: dict[str, object] = {}
_CTX = None


def last_decision() -> dict[str, object]:
    return dict(_LAST)


def _mode(ctx) -> str:
    try:
        mode = str(ctx.get_config("mode", "shadow") or "shadow").strip().lower()
    except Exception:
        mode = "shadow"
    if mode not in {"off", "shadow", "auto", "notify", "confirm"}:
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


def _budget(config):
    caps = _LAST.get("budget_caps")
    if not isinstance(caps, dict) or not caps:
        return config.budget
    from dataclasses import replace
    return replace(
        config.budget,
        daily_usd=caps.get("daily", config.budget.daily_usd),
        monthly_usd=caps.get("monthly", config.budget.monthly_usd),
    )


def _spend(config):
    path = str(_LAST.get("config_path") or "")
    if not path:
        return None
    try:
        from .decide import Spend
    except ImportError:
        from decide import Spend
    snapshot = spend_snapshot(load_ledger(state_path(path)), _budget(config))
    return Spend(pressure=snapshot.pressure, today=snapshot.today), snapshot


def _remember_route(prompt: str, analysis, decision, notes) -> None:
    _LAST["prompt"] = prompt
    _LAST["analysis"] = analysis
    _LAST["decision"] = decision
    _LAST["notes"] = tuple(notes or ())


def on_post_api_request(**kwargs):
    path = str(_LAST.get("config_path") or "")
    if not path:
        return None
    provider = str(kwargs.get("provider") or "")
    model = str(kwargs.get("response_model") or kwargs.get("model") or "")
    usd = usage_cost(kwargs.get("usage"))
    if usd <= 0 or not model:
        return None
    file = state_path(path)
    ledger = load_ledger(file)
    record_cost(ledger, f"{provider}/{model}" if provider else model, usd)
    save_ledger(file, ledger)
    return None


def on_pre_llm_call(**kwargs):
    if _CTX is not None:
        _LAST["mode"] = _mode(_CTX)
        _LAST["config_path"] = _config_path(_CTX)
    mode = str(_LAST.get("mode") or "shadow")
    _LAST["session_id"] = str(kwargs.get("session_id") or "")
    pending = _LAST.pop("pending_revert", None)
    if isinstance(pending, dict):
        target = revert_target(pending)
        if target is not None:
            maybe_switch(decision_for_target(target), _LAST["session_id"], "auto")
    previous = _LAST.get("decision")
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
        if config is None or settings is None:
            return None
        if _CTX is not None:
            config, settings = apply_setting_overrides(config, settings, present_settings(_CTX))
        if not getattr(config, "enabled", True):
            return None
        choice = parse_confirm_choice(prompt)
        if choice:
            target = target_for_choice(config, choice, previous if isinstance(previous, Decision) else None)
            if target is None:
                _LAST["blocked"] = "kept"
                return None
            picked = decision_for_target(target)
            _LAST["decision"] = picked
            switched = maybe_switch(picked, str(kwargs.get("session_id") or ""), mode)
            if switched == "switched":
                _LAST["applied"] = target.model
            elif switched in {"missing-agent", "switch-failed"}:
                _LAST["blocked"] = switched
            return None
        if len(prompt) < config.min_prompt_chars:
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
        file = state_path(path)
        ledger = load_ledger(file)
        record_jev(ledger)
        save_ledger(file, ledger)
        spent = _spend(config)
        gate = codex_eligibility(config, read_codex_remaining(), now_ms=time.time() * 1000)
        decision = decide(
            analysis,
            config,
            models_from_config(config),
            current_index=tier_index_for(config, current.provider, current.id) if current else None,
            current_model=current,
            eligibility=gate,
            spend=spent[0] if spent else None,
        )
        _remember_route(prompt, analysis, decision, getattr(decision, "notes", ()) if decision else ())
        _LAST["quota_notes"] = list(getattr(gate, "notes", ()))
        publish_route(route_payload(
            decision, current, config, str(kwargs.get("session_id") or ""), analysis, mode,
        ))
        changed = current is None or (
            decision is not None
            and (current.provider != decision.target.provider or current.id != decision.target.model)
        )
        hold_confirm = (
            decision is not None
            and changed
            and (
                mode == "confirm"
                or (decision.tier in set(config.confirm_tiers) and config.confirm_on_timeout != "accept")
            )
            and mode not in {"shadow", "notify", "off"}
        )
        if hold_confirm:
            _LAST["blocked"] = "confirm"
            switched = "skip"
        else:
            switched = maybe_switch(decision, str(kwargs.get("session_id") or ""), mode)
        if switched == "switched":
            if current is not None:
                _LAST["previous"] = {"provider": current.provider, "model": current.id}
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
    head = parts[:1]
    if head == ["suggest"]:
        path = str(_LAST.get("config_path") or "")
        if not path:
            return "hermes-jev-routing suggest: no config path"
        try:
            from .ranking import suggestion_text
        except ImportError:
            from ranking import suggestion_text
        return suggestion_text(path, write="--write" in parts)
    if head == ["why"]:
        return explain(_LAST.get("analysis"), _LAST.get("decision") if isinstance(_LAST.get("decision"), Decision) else None, tuple(_LAST.get("notes") or ()))
    if head == ["route"]:
        return _dry_route(" ".join(parts[1:]))
    if head == ["revert"]:
        return _revert()
    if head == ["budget"]:
        return _budget_command(parts[1:])
    return _status()


def _dry_route(text: str) -> str:
    prompt = text.strip() or str(_LAST.get("prompt") or "")
    if not prompt:
        return "usage: /jev-routing route <text>"
    path = str(_LAST.get("config_path") or "")
    loaded = _load(path) if path else (None, None)
    config, settings = loaded
    if config is None or settings is None:
        return "hermes-jev-routing route: no config"
    try:
        key = os.environ.get(settings.api_key_env, "")
        endpoint = os.environ.get(settings.endpoint_env, "") or settings.endpoint
        analysis = classify(
            prompt,
            api_key=key,
            endpoint=endpoint,
            jev_model=settings.jev_model,
            task_kinds=settings.task_kinds,
            timeout_ms=settings.timeout_ms,
        )
    except (JevError, OSError, TimeoutError, ValueError) as exc:
        return f"hermes-jev-routing route: {exc}"
    spent = _spend(config)
    decision = decide(analysis, config, models_from_config(config), spend=spent[0] if spent else None)
    return explain(analysis, decision, tuple(getattr(decision, "notes", ()) or ()))


def _revert() -> str:
    target = revert_target(_LAST.get("previous"))
    if target is None:
        return "no previous model recorded"
    picked = decision_for_target(target)
    switched = maybe_switch(picked, str(_LAST.get("session_id") or ""), "auto")
    if switched == "switched":
        _LAST["applied"] = target.model
        return f"reverted to {target.provider}/{target.model}"
    _LAST["pending_revert"] = {"provider": target.provider, "model": target.model}
    return f"revert to {target.provider}/{target.model} applies on the next send ({switched})"


def _budget_command(parts) -> str:
    if len(parts) < 2 or parts[0] not in {"daily", "monthly"}:
        return "usage: /jev-routing budget daily|monthly <usd>"
    try:
        amount = float(parts[1])
    except ValueError:
        return "usage: /jev-routing budget daily|monthly <usd>"
    if amount <= 0:
        return "usage: /jev-routing budget daily|monthly <usd>"
    caps = dict(_LAST.get("budget_caps") or {})
    caps["daily" if parts[0] == "daily" else "monthly"] = amount
    _LAST["budget_caps"] = caps
    return f"budget {parts[0]} cap: ${amount:.2f} for this session"


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
    global _CTX
    _CTX = ctx
    _LAST["mode"] = _mode(ctx)
    _LAST["config_path"] = _config_path(ctx)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_api_request", on_post_api_request)
    ctx.register_middleware("llm_request", on_llm_request)
    ctx.register_command("jev-routing", _command, description="Status, why, route, revert, budget, or suggest")
    return None
