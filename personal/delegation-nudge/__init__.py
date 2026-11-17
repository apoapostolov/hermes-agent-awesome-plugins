"""Delegation nudge: a live reminder when a turn keeps working inline.

Design note: ``pre_llm_call`` fires once per turn, before the tool loop, so it is
useless for this. The only seam that runs after tool results exist and can still
shape what the model reads is the ``llm_request`` middleware. It receives the
outbound provider request and may return a replacement.

Four decisions this file encodes, each learned from watching it run:

1. Count tool results, not loop iterations. ``api_call_count`` counts API rounds,
   so a turn batching three tools per round reached "10" with 30 results, and a
   careful turn reached 10 with almost none. Context is spent per result.
2. Name the routes from ``config.yaml``. The note used to hardcode route names, so
   a change to the model map would have left it lying. Free models are labelled
   free, because "this costs nothing" is the argument that travels.
3. Ask for a sentence when the turn declines. A refusal that goes unrecorded is a
   silence, and sixteen silences produced no data. One sentence makes the decline
   auditable and gives the weekly audit something to classify.
4. Escalate once. A single note is easy to skim past; the second names the bill in
   results carried. Two per turn, never more, and a dispatch silences both.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

try:  # PyYAML ships with the host; the plugin degrades to a static label without it
    import yaml
except Exception:  # pragma: no cover
    yaml = None

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_TURNS: dict[tuple[str, str], dict] = {}
_SUBAGENTS: set[str] = set()
_MAX_TURNS = 64

_FALLBACK_ROUTES = (
    "scan (free, file sweeps and lookups), research (free, many pages), "
    "deep (cheap, judgment and debugging), code (cheap, edits and tests)"
)

_ROUTE_CACHE: dict = {"at": 0.0, "text": None}
_ROUTE_CACHE_TTL = 60.0

_STAGE_ONE = (
    "[delegation check] {calls} tool results this turn, none of them delegate_task. "
    "If what is left is reading, sweeping or independent items, dispatch now: {routes}. "
    "Children run on those routes, so a dispatch costs this thread no context and almost no model budget. "
    "If the work genuinely needs this thread's context, or the caller needs an answer mid-task, stay inline "
    'and say so in one sentence ("staying inline because ...") so the decline is a decision, not a silence.'
)

_STAGE_TWO = (
    "[delegation check, second call] {calls} tool results in this single turn and still no delegate_task: "
    "all {calls} are carried in this thread's context. What is already finished stays finished; what remains "
    "can go out as {routes}. Dispatch the remainder, or write one sentence saying why it cannot leave this thread."
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


def _config_path():
    home = os.environ.get("HERMES_HOME")
    if home:
        return Path(home) / "config.yaml"
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "hermes" / "config.yaml"
    return Path.home() / ".hermes" / "config.yaml"


def _short(description: str) -> str:
    """First clause of a route description, without the price prefix it repeats.

    Route descriptions in config.yaml read "Free and quick: file sweeps and
    lookups". The price is already labelled from the model name, so the colon
    prefix is dropped and the reader gets the purpose alone.
    """
    text = str(description or "").strip()
    if not text:
        return ""
    sentence = text.split(". ")[0].rstrip(".")
    if ":" in sentence:
        head, tail = sentence.split(":", 1)
        if len(head.split()) <= 6 and tail.strip():
            sentence = tail.strip()
    return sentence if len(sentence) <= 60 else sentence[:57].rstrip() + "..."


def routes_text() -> str:
    """Describe the configured subagent routes so the note cannot go stale."""
    cached = _ROUTE_CACHE.get("text")
    if cached and time.monotonic() - float(_ROUTE_CACHE.get("at") or 0.0) < _ROUTE_CACHE_TTL:
        return cached
    text = _FALLBACK_ROUTES
    if yaml is not None:
        try:
            path = _config_path()
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                backends = ((data.get("delegation") or {}).get("backends") or {})
                options = ((backends.get("model_map") or {}).get("options")) or []
                parts = []
                for option in options:
                    if not isinstance(option, dict):
                        continue
                    name = str(option.get("name") or "").strip()
                    model = str(option.get("model") or "").strip()
                    provider = str(option.get("provider") or "").strip()
                    if not name or not model:
                        continue
                    price = "free" if "free" in model.lower() else "cheap"
                    target = f"{provider}/{model}" if provider else model
                    purpose = _short(option.get("description"))
                    label = f"{name} ({price}) {target}"
                    parts.append(f"{label} for {purpose}" if purpose else label)
                if parts:
                    text = "; ".join(parts)
        except Exception:
            logger.debug("delegation-nudge: route lookup failed", exc_info=True)
    _ROUTE_CACHE.update({"at": time.monotonic(), "text": text})
    return text


def _scan(request: dict):
    """Return (tool_results, delegated, user_index, container) for the CURRENT turn."""
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
            # Tool results are the currency: each one is a message carried in this
            # thread. The loop counter only stands in when no results are visible.
            try:
                iterations = int(kwargs.get("api_call_count") or 0)
            except (TypeError, ValueError):
                iterations = 0
            calls = tools if tools > 0 else iterations
            key = _key(kwargs)
            with _LOCK:
                row = _bucket(key)
                row["last_calls"] = calls
                if row["delegated"]:
                    return None
                if delegated:
                    row["delegated"] = True
                    return None
                threshold = max(1, int(_cfg("threshold", 10) or 10))
                escalate_at = int(_cfg("escalate_at", 25) or 25)
                repeat = max(0, int(_cfg("repeat_after", 0) or 0))
                stage = row["nudges"]
                if repeat:
                    due = calls >= threshold + stage * repeat
                elif stage == 0:
                    due = calls >= threshold
                elif stage == 1:
                    due = escalate_at > threshold and calls >= escalate_at
                else:
                    due = False
                if not due:
                    return None
                template = _STAGE_TWO if stage >= 1 else _STAGE_ONE
                note = template.format(calls=calls, routes=routes_text())
                new_request = _inject(request, container, user_index, note)
                if new_request is None:
                    return None
                row["nudges"] += 1
            logger.info(
                "delegation-nudge: stage %s reminder after %s tool results (session=%s turn=%s)",
                stage + 1, calls, key[0], key[1],
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
