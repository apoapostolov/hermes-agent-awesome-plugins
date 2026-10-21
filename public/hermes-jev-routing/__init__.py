"""Per-turn Jev routing inside the plugin SDK.

Shadow by default. In auto mode the pick is applied to the provider request
through ``llm_request`` middleware, and the desktop half moves the live session
onto the same model through the app's own model-switch request. The catalog
edition never rebinds agent internals: it cannot open another provider and it
cannot stop a send, so a cross-provider pick is reported and left alone.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

try:
    from .config import load_router_config, models_from_config
    from .decide import Analysis, AvailableModel, Decision, decide
    from .jev import JevError, classify
    from .choice import decision_for_target, parse_confirm_choice, target_for_choice
    from .availability import live_models
    from .commands import explain, revert_target, spend_lines
    from .ledger import load_ledger, record_cost, record_jev, save_ledger, spend_snapshot, state_path, usage_usd
    from .notice import publish_route, route_payload
    from .quota import codex_eligibility
    from .quota_live import read_codex_remaining
    from .route import (
        TIERS,
        action_glyph,
        crosses_provider,
        current_from,
        rewrite,
        sticky_keep,
        tier_index_for,
    )
    from .settings_override import apply_setting_overrides, present_settings
    from .skip import should_skip
except ImportError:
    from config import load_router_config, models_from_config
    from decide import Analysis, AvailableModel, Decision, decide
    from jev import JevError, classify
    from choice import decision_for_target, parse_confirm_choice, target_for_choice
    from availability import live_models
    from commands import explain, revert_target, spend_lines
    from ledger import load_ledger, record_cost, record_jev, save_ledger, spend_snapshot, state_path, usage_usd
    from notice import publish_route, route_payload
    from quota import codex_eligibility
    from quota_live import read_codex_remaining
    from route import (
        TIERS,
        action_glyph,
        crosses_provider,
        current_from,
        rewrite,
        sticky_keep,
        tier_index_for,
    )
    from settings_override import apply_setting_overrides, present_settings
    from skip import should_skip

logger = logging.getLogger(__name__)

API_KEY_ENV = "TYPESAFE_API_KEY"
# Rough characters per token, used only to fill Jev's context estimate in the
# hook payload. It is an estimate, not a billed count, and it never prices a row.
CHARS_PER_TOKEN = 4

_LAST: dict[str, object] = {"mode": "shadow"}
_LOADED: dict[str, object] = {}
_CTX = None
_SESSIONS: dict[str, dict[str, object]] = {}
SESSION_LIMIT = 64
# Turn facts copied into the owning session. Overrides (mode, enabled, budget
# caps) are never copied: they belong to the command that set them.
_TURN_KEYS = ("decision", "blocked", "applied", "prompt", "previous", "analysis", "notes", "pin")


def _trim_sessions() -> None:
    while len(_SESSIONS) > SESSION_LIMIT:
        oldest = min(_SESSIONS, key=lambda key: float(_SESSIONS[key].get("touched") or 0))
        _SESSIONS.pop(oldest, None)


def _slot(session_id: object) -> dict[str, object]:
    """Overrides and last routed turn for one session, capped in size."""
    sid = str(session_id or "")
    slot = _SESSIONS.get(sid)
    if slot is None:
        slot = {}
        _SESSIONS[sid] = slot
    slot["touched"] = time.time()
    _trim_sessions()
    return slot


def _mirror_turn(session_id: str) -> None:
    """Copy this turn's facts into the session that owns it, on every exit."""
    slot = _slot(session_id)
    for key in _TURN_KEYS:
        if key in _LAST:
            slot[key] = _LAST[key]


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


def _env(name: str) -> str:
    """Read a declared name through the host secret scope, never the raw process env."""
    if not name:
        return ""
    try:
        from agent.secret_scope import get_secret

        return str(get_secret(name) or "")
    except Exception:
        return ""


def _api_key() -> str:
    """The Jev key, from the host secret scope under its declared name."""
    return _env(API_KEY_ENV)


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


def _context_estimate(messages) -> int | None:
    """Characters over four. An estimate the hook payload can carry, nothing more."""
    if not isinstance(messages, list) or not messages:
        return None
    total = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += len(part["text"])
    if total <= 0:
        return None
    return max(total // CHARS_PER_TOKEN, 1)


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


def _model_view(current):
    """A hook-payload model as the decide() model row. Unpriced, so no cache penalty."""
    if current is None:
        return None
    return AvailableModel(provider=current.provider, id=current.id)


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
    if not model:
        return None
    usd = usage_usd(kwargs.get("usage"), provider, model)
    if usd <= 0:
        return None
    file = state_path(path)
    ledger = load_ledger(file)
    record_cost(ledger, f"{provider}/{model}" if provider else model, usd)
    save_ledger(file, ledger)
    return None


def on_pre_llm_call(**kwargs):
    session_id = str(kwargs.get("session_id") or "")
    try:
        return _pre_llm_call(**kwargs)
    finally:
        _mirror_turn(session_id)


def _pre_llm_call(**kwargs):
    session_id = str(kwargs.get("session_id") or "")
    if _CTX is not None:
        _LAST["mode"] = _mode(_CTX)
        _LAST["config_path"] = _config_path(_CTX)
    slot = _slot(session_id)
    # A /jev-routing override belongs to the session that asked for it, and it
    # has to survive the config read above, which reset it on every turn.
    if slot.get("mode"):
        _LAST["mode"] = str(slot["mode"])
    if "enabled" in slot:
        _LAST["enabled"] = slot["enabled"]
    else:
        _LAST.pop("enabled", None)
    if isinstance(slot.get("budget_caps"), dict):
        _LAST["budget_caps"] = slot["budget_caps"]
    mode = str(_LAST.get("mode") or "shadow")
    _LAST["session_id"] = session_id
    # Record the prompt up front so /jev-routing why can explain a turn that
    # was skipped before any decision was stored.
    _LAST["prompt"] = str(kwargs.get("user_message") or "").strip()
    previous = _LAST.get("decision")
    _LAST["blocked"] = ""
    _LAST["applied"] = ""
    _LAST["decision"] = None
    if mode == "off" or _LAST.get("enabled") is False:
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
            _LAST["pin"] = {
                "provider": target.provider,
                "model": target.model,
                "thinking": target.thinking_level,
            }
            _LAST["applied"] = target.model
            return None
        history = _history(kwargs.get("conversation_history"), settings.history_turns)
        skip = should_skip(prompt, config.min_prompt_chars, bool(history))
        if skip:
            _LAST["blocked"] = f"skip:{skip}"
            return None
        endpoint = str(_env(settings.endpoint_env) or settings.endpoint)
        active = str(kwargs.get("model") or "")
        current = current_from(kwargs)
        spent = _spend(config)
        analysis = classify(
            prompt,
            api_key=_api_key(),
            endpoint=endpoint,
            jev_model=settings.jev_model,
            task_kinds=settings.task_kinds,
            timeout_ms=settings.timeout_ms,
            history=history,
            active_model=active,
            context_tokens=_context_estimate(kwargs.get("conversation_history")),
            spend=spent[1].as_state() if spent is not None else None,
        )
        file = state_path(path)
        ledger = load_ledger(file)
        record_jev(ledger)
        save_ledger(file, ledger)
        gate = codex_eligibility(config, read_codex_remaining(), now_ms=time.time() * 1000)
        decision = decide(
            analysis,
            config,
            live_models(models_from_config(config)),
            current_index=tier_index_for(config, current.provider, current.id) if current else None,
            current_model=_model_view(current),
            eligibility=gate,
            spend=spent[0] if spent else None,
        )
        _remember_route(prompt, analysis, decision, getattr(decision, "notes", ()) if decision else ())
        _LAST["quota_notes"] = list(getattr(gate, "notes", ()))
        sticky = sticky_keep(config, current, decision)
        status = "offered"
        if sticky:
            status = "same"
            _LAST["blocked"] = "kept"
        elif decision is None:
            status = "none"
        elif (
            mode not in {"shadow", "notify", "off"}
            and (mode == "confirm" or decision.tier in set(config.confirm_tiers))
        ):
            # No send can be stopped from here, so the pick waits for the approve
            # row instead of changing the turn that already went out.
            status = "offered"
            _LAST["blocked"] = "confirm"
        logger.info(
            "hermes-jev-routing pick %s status=%s",
            getattr(getattr(decision, "target", None), "model", ""),
            status,
        )
        if current is not None:
            _LAST["previous"] = {"provider": current.provider, "model": current.id}
        glyph = action_glyph(sticky=sticky, status=status, mode=mode)
        label = f"jev {decision.tier}" if decision is not None else "jev"
        if spent is not None and spent[1].pressure > 0:
            label = f"{label} {spent[1].pressure * 100:.0f}%"
        publish_route(route_payload(
            decision, current, config, session_id, analysis, mode,
            glyph=glyph, prompt=prompt, status=label, held=False,
        ))
    except (JevError, OSError, TimeoutError, ValueError):
        logger.warning("hermes-jev-routing left the turn unrouted", exc_info=True)
    return None


def _mark(slot: dict[str, object], state: str) -> None:
    _LAST["blocked"] = state
    if slot:
        slot["blocked"] = state


def on_llm_request(**kwargs):
    """Apply the pick to the request that is about to be sent."""
    session_id = str(kwargs.get("session_id") or "")
    slot = _SESSIONS.get(session_id) or {}
    mode = str(slot.get("mode") or _LAST.get("mode") or "shadow")
    if mode == "off" or _LAST.get("enabled") is False:
        return None
    request = kwargs.get("request")
    if not isinstance(request, dict):
        return None
    bound = str(kwargs.get("provider") or "")
    if not bound:
        return None
    pin = slot.get("pin") if "pin" in slot else _LAST.get("pin")
    if isinstance(pin, dict) and pin.get("model"):
        if pin.get("provider") and pin["provider"] != bound:
            _mark(slot, "cross-provider")
            return None
        updated = dict(request)
        updated["model"] = str(pin["model"])
        level = str(pin.get("thinking") or "").strip().lower()
        if level and level not in {"off", "none", "false", "disabled"}:
            for field in ("reasoning_effort", "reasoning"):
                if field in updated:
                    updated[field] = level
                    break
        _LAST.pop("pin", None)
        slot.pop("pin", None)
        _LAST["applied"] = str(pin["model"])
        if slot:
            slot["applied"] = str(pin["model"])
        return {
            "request": updated,
            "source": "hermes-jev-routing",
            "reason": "pinned by /jev-routing revert",
        }
    decision = slot.get("decision") if "decision" in slot else _LAST.get("decision")
    blocked = slot.get("blocked") if "blocked" in slot else _LAST.get("blocked")
    if mode != "auto" or not isinstance(decision, Decision) or blocked == "confirm":
        return None
    try:
        rewritten = rewrite(request, decision, bound, mode)
    except Exception:
        logger.warning("hermes-jev-routing left the request unchanged", exc_info=True)
        return None
    if rewritten is None:
        if crosses_provider(decision, bound):
            _mark(slot, "cross-provider")
        return None
    _LAST["applied"] = rewritten.get("model")
    if slot:
        slot["applied"] = rewritten.get("model")
    return {
        "request": rewritten,
        "source": "hermes-jev-routing",
        "reason": decision.reason,
    }


def _command(raw: str = "", *, session_id: str = "") -> str:
    slot = _slot(session_id)
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
    if head == ["on"]:
        slot["enabled"] = True
        return "jev-routing enabled for this session"
    if head == ["off"]:
        slot["enabled"] = False
        return "jev-routing disabled for this session"
    if head == ["mode"]:
        name = (parts[1] if len(parts) > 1 else "").lower()
        if name not in {"auto", "confirm", "notify", "shadow", "off"}:
            return "usage: /jev-routing mode auto|confirm|notify|shadow|off"
        slot["mode"] = name
        return f"jev-routing mode: {name} for this session"
    if head == ["why"]:
        return _dry_route(str(slot.get("prompt") or _LAST.get("prompt") or ""))
    if head == ["route"]:
        return _dry_route(" ".join(parts[1:]))
    if head == ["revert"]:
        return _revert(session_id, slot)
    if head == ["budget"]:
        return _budget_command(parts[1:], slot)
    return _status(slot)


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
        endpoint = str(_env(settings.endpoint_env) or settings.endpoint)
        analysis = classify(
            prompt,
            api_key=_api_key(),
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


def _revert(session_id: str = "", slot: dict[str, object] | None = None) -> str:
    """Pin the previous model onto the next request that can carry it."""
    slot = slot if slot is not None else _slot(session_id)
    previous = slot.get("previous") if "previous" in slot else _LAST.get("previous")
    target = revert_target(previous)
    if target is None:
        return "no previous model recorded"
    values = {"provider": target.provider, "model": target.model, "thinking": target.thinking_level}
    _LAST["pin"] = values
    slot["pin"] = values
    return f"revert to {target.provider}/{target.model} applies on the next send from that provider"


def _budget_command(parts, slot: dict[str, object] | None = None) -> str:
    if len(parts) < 2 or parts[0] not in {"daily", "monthly"}:
        return "usage: /jev-routing budget daily|monthly <usd>"
    try:
        amount = float(parts[1])
    except ValueError:
        return "usage: /jev-routing budget daily|monthly <usd>"
    if amount <= 0:
        return "usage: /jev-routing budget daily|monthly <usd>"
    caps = dict((slot or {}).get("budget_caps") or _LAST.get("budget_caps") or {})
    caps["daily" if parts[0] == "daily" else "monthly"] = amount
    _LAST["budget_caps"] = caps
    if slot is not None:
        slot["budget_caps"] = caps
    return f"budget {parts[0]} cap: ${amount:.2f} for this session"


def _status(slot: dict[str, object] | None = None) -> str:
    slot = slot or {}
    decision = slot.get("decision") if "decision" in slot else _LAST.get("decision")
    path = str(_LAST.get("config_path") or "")
    loaded = _load(path) if path else (None, None)
    config = loaded[0]
    mode = str(slot.get("mode") or _LAST.get("mode") or "shadow")
    lines = [f"mode: {mode}"]
    if "enabled" in slot:
        lines.append(f"enabled: {'yes' if slot['enabled'] else 'no'} (this session)")
    if config is not None:
        spent = _spend(config)
        if spent is not None:
            lines.append(spend_lines(spent[1]))
        lines.append("routes:")
        for tier in TIERS:
            chain = config.routes.get(tier) or ()
            if not chain:
                lines.append(f"  {tier}: (none)")
                continue
            head = chain[0]
            extra = f" (+{len(chain) - 1})" if len(chain) > 1 else ""
            lines.append(f"  {tier}: {head.provider}/{head.model}{extra}")
    if isinstance(decision, Decision):
        lines.append(f"last: {decision.reason} -> {decision.target.provider}/{decision.target.model}")
    else:
        lines.append("last: none")
    blocked = slot.get("blocked") if "blocked" in slot else _LAST.get("blocked")
    if blocked:
        lines.append(f"blocked: {blocked}")
    applied = slot.get("applied") if "applied" in slot else _LAST.get("applied")
    if applied:
        lines.append(f"applied: {applied}")
    lines.append("edition: request-level. A pick on another provider is reported, not sent.")
    lines.append("commands: why, route <text>, revert, budget daily|monthly <usd>, suggest [--write]")
    return "\n".join(lines)


def remember(decision: Decision | None, mode: str) -> None:
    _LAST.clear()
    _LAST["mode"] = mode
    if decision is not None:
        _LAST["decision"] = decision


def classify_for_tests(analysis: Analysis, config, models, mode: str, **kwargs) -> Decision | None:
    decision = decide(analysis, config, models, **kwargs)
    remember(decision, mode)
    return decision


def on_session_delete(**kwargs) -> None:
    """A deleted session takes its overrides and its last turn with it."""
    ids = {str(kwargs.get("session_id") or "")}
    ids.update(str(item) for item in (kwargs.get("deleted_ids") or []))
    ids.discard("")
    for sid in ids:
        _SESSIONS.pop(sid, None)


def register(ctx):
    global _CTX
    _CTX = ctx
    _LAST["mode"] = _mode(ctx)
    _LAST["config_path"] = _config_path(ctx)
    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_api_request", on_post_api_request)
    ctx.register_hook("on_session_delete", on_session_delete)
    ctx.register_middleware("llm_request", on_llm_request)
    ctx.register_command("jev-routing", _command, description="Status, why, route, revert, budget, or suggest")
    ctx.register_tool(
        name="jev_route",
        toolset="hermes-jev-routing",
        schema={
            "name": "jev_route",
            "description": "Ask which model tier a request deserves. Does not switch the session.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The request to classify."}},
                "required": ["text"],
            },
        },
        handler=lambda args, **kwargs: _dry_route(str((args or {}).get("text") or "")),
        description="Classify a request without switching.",
    )
    return None
