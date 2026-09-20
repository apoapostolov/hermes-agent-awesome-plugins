"""Session Retitler — dynamic thread renaming every N user messages.

Counts titleable user messages in the live history (not completed,
non-interrupted turns). ``pre_llm_call`` fires at the start of a turn
even if the user later breaks or steers, so interrupt-heavy chats still
advance the counter. Every ``interval`` user messages, the plugin builds
a digest and asks the host's ``title_generation`` auxiliary tier for a
fresh 3-6 word title.

Title authority is ``llm`` rank, never ``user``:

- If the user renamed the session manually (title_source == "user"), the
  plugin never touches the name again.
- ``derived``/untitled sessions upgrade straight to the new ``llm`` title.
- ``llm`` -> ``llm`` rewrites clear the row first, because the core's
  ``set_auto_title`` only writes on a strictly-higher rank and would
  otherwise no-op every rename after the first.

State (per-session counters) lives in ``ctx.state`` — the host's
file-locked, cross-process JSON store — so a session that hops between
the TUI, CLI, and gateway keeps one counter.
"""

from __future__ import annotations

import logging
import re
import threading
import time

from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PLUGIN_ID = "session-retitler"

DEFAULTS = {
    "interval": 20,       # user messages between retitles
    "max_pairs": 20,      # exchanges fed into the digest
    "min_pairs": 4,       # give up below this even at the interval boundary
    "timeout": 45.0,      # LLM call budget, seconds
    "max_sessions": 60,   # counter cache bound
}

_MAX_TITLE_WORDS = 8  # headroom above the 3-6 word prompt target; longer output is truncated, not dropped
_MAX_TITLE_CHARS = 60
_SNIPPET_CHARS = 500
_DIGEST_CHARS = 7000

_counter_lock = threading.Lock()
_inflight: set = set()

_TITLE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Short session title, 3-6 words, same language as the chat.",
        }
    },
    "required": ["title"],
    "additionalProperties": False,
}

_INSTRUCTIONS = (
    "You name chat sessions. You get the last few user/assistant exchanges "
    "from one ongoing conversation. Write a short title (3 to 6 words) that "
    "names what the conversation is about NOW, so the session list stays "
    "readable as the topic drifts. Use the same language as the exchanges. "
    "No quotes, no trailing punctuation, no prefix like 'Title:'."
)


# ---------------------------------------------------------------------------
# Config + state helpers
# ---------------------------------------------------------------------------

def _cfg(ctx: Any, key: str) -> Any:
    try:
        val = ctx.get_config(key)
    except Exception:
        val = None
    if val is None or val == "":
        return DEFAULTS[key]
    if key in ("interval", "max_pairs", "min_pairs", "max_sessions"):
        try:
            return max(1, int(val))
        except (TypeError, ValueError):
            return DEFAULTS[key]
    if key == "timeout":
        try:
            return max(5.0, float(val))
        except (TypeError, ValueError):
            return DEFAULTS[key]
    return val


def _load_counts(ctx: Any) -> Dict[str, Dict[str, float]]:
    try:
        data = ctx.state.get("turn_counts", {})
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.debug("session-retitler: counter read failed", exc_info=True)
        return {}


def _save_counts(ctx: Any, counts: Dict[str, Dict[str, float]]) -> None:
    if len(counts) > _cfg(ctx, "max_sessions"):
        keep = sorted(
            counts.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True
        )[: _cfg(ctx, "max_sessions")]
        counts = dict(keep)
    try:
        ctx.state.set("turn_counts", counts)
    except Exception:
        logger.debug("session-retitler: counter write failed", exc_info=True)


def _extra_counts(history: List[Any], extra_text: Optional[str]) -> bool:
    """True when the incoming prompt adds one titleable user message."""
    extra = (extra_text or "").strip()
    if not extra or _is_machine_user_message(extra):
        return False
    last = ""
    for msg in history or []:
        if _is_real_user_message(msg):
            last = _text_of(msg).strip()
    if extra == last:
        return False
    try:
        from agent.title_generator import is_titleable_user_message

        return bool(is_titleable_user_message(extra))
    except Exception:
        return True


def _count_user_messages(history: List[Any], extra_text: Optional[str] = None) -> int:
    """Titleable user messages in history, plus the incoming prompt if new."""
    n = 0
    for msg in history or []:
        if _is_real_user_message(msg):
            n += 1
    if _extra_counts(history, extra_text):
        n += 1
    return n


def _record_count(ctx: Any, session_id: str, n: int, claim: bool = False) -> bool:
    """Persist count n in one state round trip; claim the boundary when asked.

    Returns True only when a fresh boundary was claimed (and the session
    marked in flight). Plain syncs never touch last_retitle_n.
    """
    with _counter_lock:
        if claim and session_id in _inflight:
            return False
        counts = _load_counts(ctx)
        entry = counts.get(session_id) or {}
        last = int(entry.get("last_retitle_n", 0))
        if claim:
            if n == last:
                return False
            counts[session_id] = {"n": n, "ts": time.time(), "last_retitle_n": n}
            _save_counts(ctx, counts)
            _inflight.add(session_id)
            return True
        counts[session_id] = {"n": n, "ts": time.time(), "last_retitle_n": last}
        _save_counts(ctx, counts)
        return False


def _reset(ctx: Any, session_id: str) -> None:
    with _counter_lock:
        counts = _load_counts(ctx)
        if session_id in counts:
            del counts[session_id]
            _save_counts(ctx, counts)


# ---------------------------------------------------------------------------
# Digest building
# ---------------------------------------------------------------------------

def _text_of(message: Any) -> str:
    """Flatten a message's content to plain text (str or multimodal parts)."""
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: List[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "\n".join(parts)
    return ""


def _is_machine_user_message(text: str) -> bool:
    """Best-effort machinery detector when the core helper is unavailable."""
    stripped = text.lstrip()
    return bool(
        stripped.startswith(("[SYSTEM", "<system", "[OUT-OF-BAND", "[Tool result"))
    )


def _is_real_user_message(message: Any) -> bool:
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    text = _text_of(message).strip()
    if not text or _is_machine_user_message(text):
        return False
    try:
        from agent.title_generator import is_titleable_user_message

        return bool(is_titleable_user_message(text))
    except Exception:
        return True


def _assistant_text(message: Any) -> str:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return ""
    # Tool-call steps carry tool_calls and empty content; only real prose counts.
    if message.get("tool_calls"):
        return ""
    return _text_of(message).strip()


def build_digest(history: List[Any], max_pairs: int) -> str:
    """Render the last ``max_pairs`` user/assistant exchanges as one text blob."""
    turns: List[Tuple[str, str]] = []
    pending_user: Optional[str] = None
    for msg in history or []:
        if _is_real_user_message(msg):
            pending_user = _text_of(msg).strip()[:_SNIPPET_CHARS]
        elif pending_user is not None:
            reply = _assistant_text(msg)
            if reply:
                turns.append((pending_user, reply[:_SNIPPET_CHARS]))
                pending_user = None
    if pending_user is not None:
        turns.append((pending_user, ""))
    turns = turns[-max_pairs:]

    chunks: List[str] = []
    for user, reply in turns:
        block = f"USER: {user}"
        if reply:
            block += f"\nASSISTANT: {reply}"
        chunks.append(block)
    digest = "\n\n".join(chunks)
    if len(digest) > _DIGEST_CHARS:
        cut = digest[-_DIGEST_CHARS:]
        sep = cut.find("\n\n")
        digest = cut[sep + 2 :] if sep != -1 else cut
    return digest


def build_snapshot(history: List[Any], extra_user: Optional[str] = None) -> List[Any]:
    """History plus the triggering prompt, so the digest sees the boundary message."""
    snapshot = list(history or [])
    if _extra_counts(snapshot, extra_user):
        snapshot.append({"role": "user", "content": (extra_user or "").strip()})
    return snapshot


# ---------------------------------------------------------------------------
# Title write (llm rank, user rank is a hard stop)
# ---------------------------------------------------------------------------

def _clean_title(raw: Any) -> Optional[str]:
    if not isinstance(raw, str):
        return None
    title = raw.strip().strip('"').strip("'").strip()
    title = re.sub(r"^(title|session|topic)\s*[:\-]\s*", "", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        return None
    words = title.split()
    if len(words) > _MAX_TITLE_WORDS:
        title = " ".join(words[:_MAX_TITLE_WORDS])
    return title[:_MAX_TITLE_CHARS].rstrip(" .,-")


def _write_llm_title(db: Any, session_id: str, title: str) -> bool:
    """Persist *title* at llm rank, honoring the precedence ladder.

    user > llm > derived. A user-set name is untouchable. llm->llm needs a
    clear first because set_auto_title requires a strictly higher rank.
    """
    try:
        source = db.get_session_title_source(session_id)
    except Exception:
        source = None
    if source == "user":
        logger.debug("session-retitler: %s holds a user title; not rewriting", session_id)
        return False

    if source == "llm":
        try:
            db.set_session_title(session_id, "")  # normalize to None/untitled
        except Exception:
            logger.debug("session-retitler: pre-rewrite clear failed", exc_info=True)
            return False

    try:
        # Reuses the core's proven write: set_auto_title + "#N" collision recovery.
        from agent.title_generator import _persist_session_title

        persisted = _persist_session_title(db, session_id, title, source="llm")
        return persisted is not None
    except Exception:
        logger.debug("session-retitler: core persist helper unavailable", exc_info=True)
    try:
        return bool(db.set_auto_title(session_id, title, source="llm"))
    except ValueError:
        logger.debug("session-retitler: title collision on %r", title)
        return False
    except Exception:
        logger.debug("session-retitler: title write failed", exc_info=True)
        return False


# ---------------------------------------------------------------------------
# The retitle job
# ---------------------------------------------------------------------------

def _retitle(ctx: Any, session_id: str, digest: str) -> None:
    """Ask the aux tier for a title from a prebuilt digest; persist at llm rank."""
    try:
        from agent.plugin_llm import PluginLlmTextInput

        result = ctx.llm.complete_structured(
            instructions=_INSTRUCTIONS,
            input=[PluginLlmTextInput(text=digest)],
            json_schema=_TITLE_JSON_SCHEMA,
            schema_name="session_title",
            temperature=0.3,
            max_tokens=64,
            timeout=_cfg(ctx, "timeout"),
            task="title_generation",
            purpose="session-retitle",
        )
        parsed = getattr(result, "parsed", None)
        title = _clean_title((parsed or {}).get("title") if isinstance(parsed, dict) else None)
        if not title:
            logger.debug("session-retitler: model gave no usable title")
            return

        from hermes_state import SessionDB

        db = SessionDB()
        try:
            ok = _write_llm_title(db, session_id, title)
            if ok:
                logger.info("session-retitler: renamed %s -> %r", session_id, title)
        finally:
            close = getattr(db, "close", None)
            if callable(close):
                close()
    except Exception:
        # Never let a background rename disturb the host process.
        logger.debug("session-retitler: retitle failed", exc_info=True)


# ---------------------------------------------------------------------------
# Hook callbacks
# ---------------------------------------------------------------------------

def _maybe_retitle(
    ctx: Any,
    session_id: str,
    conversation_history: List[Any],
    extra_user: Optional[str] = None,
) -> None:
    if not session_id:
        return
    interval = _cfg(ctx, "interval")
    history = conversation_history or []
    n = _count_user_messages(history, extra_user)
    if n < interval or n % interval != 0:
        _record_count(ctx, session_id, n)
        return
    # Boundary reached: snapshot first (the triggering prompt counts, so the
    # digest must see it), then gate on usable pairs BEFORE claiming, so a
    # thin digest never burns the boundary.
    snapshot = build_snapshot(history, extra_user)
    digest = build_digest(snapshot, _cfg(ctx, "max_pairs"))
    pairs = digest.count("USER: ")
    if pairs < _cfg(ctx, "min_pairs"):
        logger.debug("session-retitler: only %d pairs; skipping", pairs)
        _record_count(ctx, session_id, n)
        return
    if not _record_count(ctx, session_id, n, claim=True):
        return
    try:
        # Off-thread by design: hook callbacks must not block a turn. A
        # failure here only logs; the turn is never disturbed.
        thread = threading.Thread(
            target=_retitle_and_release,
            args=(ctx, session_id, digest),
            daemon=True,
            name=f"session-retitle-{session_id[:12]}",
        )
        thread.start()
    except Exception:
        with _counter_lock:
            _inflight.discard(session_id)
        raise


def _on_pre_llm_call(
    ctx: Any,
    session_id: str,
    conversation_history: List[Any],
    user_message: Optional[str],
) -> None:
    _maybe_retitle(ctx, session_id, conversation_history, user_message)


def _on_post_llm_call(ctx: Any, session_id: str, conversation_history: List[Any]) -> None:
    _maybe_retitle(ctx, session_id, conversation_history)


def _retitle_and_release(ctx: Any, session_id: str, digest: str) -> None:
    try:
        _retitle(ctx, session_id, digest)
    finally:
        with _counter_lock:
            _inflight.discard(session_id)


def _on_session_reset(ctx: Any, session_id: str) -> None:
    if session_id:
        _reset(ctx, session_id)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def register(ctx):  # noqa: ANN001 — host-defined PluginContext
    """Register user-message counter + retitle trigger.

    Hook callbacks receive only the fire-site kwargs (no ctx), so the real
    handlers are closures capturing the register-time PluginContext.
    """
    state = ctx.state  # touch early: fail load loudly on a broken state store
    logger.info(
        "session-retitler: loading (state at %s, interval=%s, count=user_messages)",
        getattr(state, "path", "?"),
        _cfg(ctx, "interval"),
    )

    def on_pre_llm_call(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        history = kwargs.get("conversation_history") or []
        user_message = kwargs.get("user_message")
        try:
            _on_pre_llm_call(ctx, session_id, history, user_message if isinstance(user_message, str) else None)
        except Exception:
            logger.debug("session-retitler: pre_llm_call handler failed", exc_info=True)

    def on_post_llm_call(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        history = kwargs.get("conversation_history") or []
        try:
            _on_post_llm_call(ctx, session_id, history)
        except Exception:
            logger.debug("session-retitler: post_llm_call handler failed", exc_info=True)

    def on_session_reset(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        try:
            _on_session_reset(ctx, session_id)
        except Exception:
            logger.debug("session-retitler: reset handler failed", exc_info=True)

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("on_session_reset", on_session_reset)
