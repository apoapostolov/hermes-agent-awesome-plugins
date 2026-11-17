"""Delegation nudge: a live reminder when a turn keeps working inline.

Design note: ``pre_llm_call`` fires once per turn, before the tool loop, so it is
useless for this. The only seam that runs after tool results exist and can still
shape what the model reads is the ``llm_request`` middleware. It receives the
outbound provider request and may return a replacement.

So each provider request is scanned: count tool results since the turn's user
message, note whether ``delegate_task`` appears in the turn, and past the threshold
append one short note to that user message. Nothing edits tool output, the system
prompt is untouched, and the runtime skips a middleware that raises.

Limits that matter: once per turn by default, silent inside a subagent, silent for
the rest of the turn after a dispatch, and the note tells the model when to ignore
it, so a turn that genuinely needs this thread's context is never nagged.
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_TURNS: dict[tuple[str, str], dict] = {}
_SUBAGENTS: set[str] = set()
_MAX_TURNS = 64

_ROUTES = (
    "scan (free, file sweeps and lookups), research (free, many pages), "
    "deep (cheap, judgment and debugging), code (cheap, edits and tests)"
)

_NOTE = (
    "[delegation check] {calls} steps into this turn, none of them delegate_task. "
    "If what is left is reading, sweeping, or independent items, dispatch now and route it: "
    + _ROUTES
    + ". If the work genuinely needs this thread's context, or the caller needs an answer "
    "mid-task, ignore this note and continue."
)


def _key(kwargs) -> tuple[str, str]:
    return str(kwargs.get("session_id") or ""), str(kwargs.get("turn_id") or "")


def _bucket(key) -> dict:
    row = _TURNS.get(key)
    if row is None:
        if len(_TURNS) >= _MAX_TURNS:
            _TURNS.pop(next(iter(_TURNS)))
        row = {"nudges": 0, "delegated": False, "last_calls": 0}
        _TURNS[key] = row
    return row


def _is_subagent(kwargs) -> bool:
    if any(kwargs.get(name) for name in ("parent_session_id", "parent_subagent_id", "parent_turn_id")):
        return True
    return str(kwargs.get("session_id") or "") in _SUBAGENTS


def _scan(request: dict):
    """Return (tool_results, delegated, user_index, container) for the CURRENT turn.

    Counters reset at every user message, so a long session's older tool results
    never inflate this turn's count.
    """
    messages = request.get("messages")
    if isinstance(messages, list):
        tools, delegated, user_index = 0, False, -1
        for i, item in enumerate(messages):
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            if role == "user":
                user_index, tools, delegated = i, 0, False
            elif role == "tool":
                tools += 1
            elif role == "assistant":
                for call in item.get("tool_calls") or []:
                    if isinstance(call, dict) and ((call.get("function") or {}).get("name") == "delegate_task"):
                        delegated = True
        return tools, delegated, user_index, "messages"

    items = request.get("input")
    if isinstance(items, list):
        tools, delegated, user_index = 0, False, -1
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if item.get("role") == "user":
                user_index, tools, delegated = i, 0, False
            if kind in ("function_call_output", "local_shell_call_output"):
                tools += 1
            if kind == "function_call" and item.get("name") == "delegate_task":
                delegated = True
        return tools, delegated, user_index, "input"

    return 0, False, -1, None


def _inject(request: dict, container: str, index: int, note: str):
    seq = request.get(container)
    if not isinstance(seq, list) or not (0 <= index < len(seq)):
        return None
    item = seq[index]
    if not isinstance(item, dict):
        return None
    content = item.get("content")
    if isinstance(content, str):
        if note in content:
            return None
        replacement = dict(item, content=content + "\n\n" + note)
    elif isinstance(content, list):
        replacement = dict(item, content=list(content) + [{"type": "text", "text": note}])
    else:
        return None
    new_seq = list(seq)
    new_seq[index] = replacement
    return dict(request, **{container: new_seq})


def register(ctx):
    def _cfg(name, default):
        try:
            value = ctx.get_config(name, default)
        except Exception:
            return default
        return default if value is None else value

    def on_llm_request(request=None, original_request=None, **kwargs):
        try:
            if not isinstance(request, dict) or not _cfg("enabled", True):
                return None
            if _is_subagent(kwargs):
                return None
            tools, delegated, user_index, container = _scan(request)
            if not container or user_index < 0:
                return None
            # api_call_count is the turn's own loop counter, so it counts this turn's
            # rounds even when history holds hundreds of older tool results.
            try:
                calls = int(kwargs.get("api_call_count") or 0)
            except (TypeError, ValueError):
                calls = 0
            if calls <= 0:
                calls = tools
            key = _key(kwargs)
            with _LOCK:
                row = _bucket(key)
                row["last_calls"] = calls
                if row["delegated"]:
                    return None
                if delegated:
                    row["delegated"] = True
                    return None
                threshold = max(1, int(_cfg("threshold", 15) or 15))
                repeat = max(0, int(_cfg("repeat_after", 0) or 0))
                if repeat:
                    due = calls >= threshold + row["nudges"] * repeat
                else:
                    due = calls >= threshold and row["nudges"] == 0
                if not due:
                    return None
                new_request = _inject(request, container, user_index, _NOTE.format(calls=calls))
                if new_request is None:
                    return None
                row["nudges"] += 1
            logger.info(
                "delegation-nudge: reminder after %s turns of the loop (session=%s turn=%s)",
                calls, key[0], key[1],
            )
            return {"request": new_request, "reason": "delegation-nudge", "name": "delegation-nudge"}
        except Exception:
            logger.debug("delegation-nudge: llm_request middleware failed", exc_info=True)
            return None

    def on_subagent_start(**kwargs):
        try:
            for name in ("session_id", "child_session_id", "subagent_session_id"):
                value = kwargs.get(name)
                if value:
                    with _LOCK:
                        _SUBAGENTS.add(str(value))
        except Exception:
            logger.debug("delegation-nudge: subagent_start failed", exc_info=True)

    def on_subagent_stop(**kwargs):
        try:
            for name in ("session_id", "child_session_id", "subagent_session_id"):
                value = kwargs.get(name)
                if value:
                    with _LOCK:
                        _SUBAGENTS.discard(str(value))
        except Exception:
            logger.debug("delegation-nudge: subagent_stop failed", exc_info=True)

    def on_session_delete(**kwargs):
        try:
            gone = {str(kwargs.get("session_id") or "")}
            gone |= {str(x) for x in (kwargs.get("deleted_ids") or [])}
            with _LOCK:
                for key in [k for k in _TURNS if k[0] in gone]:
                    _TURNS.pop(key, None)
                _SUBAGENTS.difference_update(gone)
        except Exception:
            logger.debug("delegation-nudge: session cleanup failed", exc_info=True)

    ctx.register_middleware("llm_request", on_llm_request)
    ctx.register_hook("subagent_start", on_subagent_start)
    ctx.register_hook("subagent_stop", on_subagent_stop)
    ctx.register_hook("on_session_delete", on_session_delete)


def deregister():
    with _LOCK:
        _TURNS.clear()
        _SUBAGENTS.clear()
