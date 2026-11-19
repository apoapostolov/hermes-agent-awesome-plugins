"""Session Retitler — dynamic thread renaming every N user messages.

Counts titleable user messages in the live history (not completed,
non-interrupted turns). ``pre_llm_call`` fires at the start of a turn
even if the user later breaks or steers, so interrupt-heavy chats still
advance the counter. Every ``interval`` user messages, the plugin builds
a digest and asks its own ``sessionretitler_title`` auxiliary slot for a
fresh 3-6 word title. The slot inherits the host ``title_generation``
route until the operator pins a different model under Settings, Models,
Auxiliary.

Title authority is ``llm`` rank, never ``user``:

- If the user renamed the session manually (title_source == "user"), the
  plugin never touches the name again.
- ``derived``/untitled sessions upgrade straight to the new ``llm`` title.
- ``llm`` -> ``llm`` rewrites lower the row to ``derived`` first, because the
  core's ``set_auto_title`` only writes on a strictly-higher rank and would
  otherwise no-op every rename after the first. The previous name goes back
  at its original rank if the rewrite does not land, so a failed write never
  leaves the session untitled.
- A row that carries a name but no ``title_source`` ranks as ``user`` in
  core, so it is left alone like any other name the user owns.

The trigger is a delta (``n - last_retitle_n >= interval``), not a modulo on
the raw count: the count is re-derived from the live history every turn, core
compaction can pull it backwards, and a modulo boundary missed once would
never fire again.

State (per-session counters) lives in ``ctx.state`` — the host's
file-locked, cross-process JSON store — so a session that hops between
the TUI, CLI, and gateway keeps one counter.
"""

from __future__ import annotations

import contextvars
import logging
import re
import threading
import time

from typing import Any, Dict, List, Optional, Tuple

try:
    from persistence.conversation.sessions import TitleSource
except Exception:  # host older than the storage interface
    TitleSource = None

logger = logging.getLogger(__name__)

PLUGIN_ID = "sessionretitler"
AUX_TASK = "sessionretitler_title"

DEFAULTS = {
    "interval": 10,       # user messages between retitles
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
        logger.debug("sessionretitler: counter read failed", exc_info=True)
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
        logger.debug("sessionretitler: counter write failed", exc_info=True)


def _extra_counts(history: List[Any], extra_text: Optional[str]) -> bool:
    """True when the incoming prompt adds one titleable user message."""
    extra = (extra_text or "").strip()
    if not _is_titleable_user_message(extra):
        return False
    last = ""
    for msg in history or []:
        if _is_real_user_message(msg):
            last = _text_of(msg).strip()
    if extra == last:
        return False
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


def _last_retitle_n(entry: Any) -> int:
    """Stored boundary high-water mark, tolerant of a corrupt state entry."""
    try:
        if isinstance(entry, dict):
            return max(0, int(entry.get("last_retitle_n", 0) or 0))
    except (TypeError, ValueError):
        pass
    return 0


def _record_count(
    ctx: Any, session_id: str, n: int, claim: bool = False, interval: int = 1,
) -> Tuple[Optional[int], bool]:
    """Persist count n in one state round trip; claim the boundary when asked.

    Returns ``(previous_last_retitle_n, claimed)``. The claim fires on a delta
    (``n - last_retitle_n >= interval``), not on ``n % interval == 0``: the
    count is re-derived from the live history every turn, core compaction can
    pull it backwards, and one turn can move it by more than one message, so a
    modulo boundary missed once never fires again. A count that fell below the
    last retitle is rebased, so the next interval still triggers instead of
    waiting for the count to climb back over a stale high-water mark. Plain
    syncs never claim and never touch a boundary that is still ahead.
    """
    with _counter_lock:
        if claim and session_id in _inflight:
            return None, False
        counts = _load_counts(ctx)
        entry = counts.get(session_id) or {}
        last = _last_retitle_n(entry)
        if n < last:
            last = n  # history shrank under compaction: rebase, never block forever
        due = bool(claim) and n - last >= max(1, int(interval or 1))
        counts[session_id] = {"n": n, "ts": time.time(), "last_retitle_n": n if due else last}
        _save_counts(ctx, counts)
        if not due:
            return None, False
        _inflight.add(session_id)
        return last, True


def _release_claim(ctx: Any, session_id: str, previous: Optional[int]) -> None:
    """Give a claimed boundary back so the next turn retries the rename.

    Used only when the model produced a title that could not be persisted: the
    name the session would have got is gone, and waiting a whole further
    interval for the next attempt is the worse outcome.
    """
    if previous is None:
        return
    with _counter_lock:
        counts = _load_counts(ctx)
        entry = counts.get(session_id)
        if not isinstance(entry, dict):
            return
        try:
            n = int(entry.get("n", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        entry["last_retitle_n"] = max(0, min(int(previous), n))
        _save_counts(ctx, counts)


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


_MACHINE_TITLE_PREFIXES = (
    "[SYSTEM", "<system", "[OUT-OF-BAND", "[Tool result",
    "[CONTEXT COMPACTION", "[System note:", "[Runtime note:",
    "[System: The active model for this chat has changed to ",
)


def _is_titleable_user_message(text: Any) -> bool:
    """Local stand-in for core's private titleability check."""
    if not isinstance(text, str) or not text.strip():
        return False
    return not text.lstrip().startswith(_MACHINE_TITLE_PREFIXES)


def _is_real_user_message(message: Any) -> bool:
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    text = _text_of(message).strip()
    if not _is_titleable_user_message(text):
        return False
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


def _persist_llm_title(
    sessions: Any, session_id: str, title: str, title_source: Any,
) -> Optional[str]:
    """Write *title* at llm rank through the store's own repository.

    Returns the title actually written, or None when a higher authority held
    the row. A unique-title collision gets a "#N" suffix from the store.
    """
    def _set(candidate: str) -> Optional[str]:
        if sessions.set_auto_title(session_id, candidate, source=title_source.LLM):
            return candidate
        return None

    try:
        return _set(title)
    except ValueError:
        deduped = sessions.next_title_in_lineage(title)
        if not deduped or deduped == title:
            return None
        return _set(deduped)


def _restore_title(
    sessions: Any, session_id: str, previous: Optional[str], was_llm: bool,
) -> None:
    """Undo the rank-lowering step when a rewrite did not land.

    An llm->llm rewrite first lowers the row to derived, so a failed rewrite
    must put the original provenance back or the next rename silently starts
    from the wrong rank.
    """
    if not previous:
        return
    try:
        current = sessions.get_title(session_id)
        if current and current != previous:
            return  # another writer named it; never fight that
        if current == previous:
            if was_llm:
                sessions.set_title_source(session_id, TitleSource.LLM)
            return
        sessions.set_auto_title(session_id, previous, source=TitleSource.LLM)
        logger.warning(
            "sessionretitler: rename failed for %s; restored %r", session_id, previous,
        )
    except Exception:
        logger.warning(
            "sessionretitler: could not restore %r on %s", previous, session_id, exc_info=True,
        )


def _write_llm_title(sessions: Any, session_id: str, title: str) -> bool:
    """Persist *title* at llm rank, honoring the precedence ladder.

    user > llm > derived. If the source cannot be read the write is skipped
    entirely: a failed read must never be mistaken for "no user title".
    """
    if TitleSource is None:
        logger.debug("sessionretitler: storage title API unavailable; not writing")
        return False
    try:
        source = sessions.get_title_source(session_id)
        previous = sessions.get_title(session_id)
    except Exception:
        logger.debug(
            "sessionretitler: cannot read title source for %s; not writing",
            session_id, exc_info=True,
        )
        return False
    if source == TitleSource.USER or (source is None and previous):
        logger.debug("sessionretitler: %s holds a user title; not rewriting", session_id)
        return False

    # set_auto_title only writes over a strictly lower rank. Lower an llm row
    # to derived first, keeping the old title until the rewrite lands.
    was_llm = source == TitleSource.LLM
    if was_llm and not sessions.set_title_source(session_id, TitleSource.DERIVED):
        return False

    if _persist_llm_title(sessions, session_id, title, TitleSource):
        return True
    _restore_title(sessions, session_id, previous, was_llm)
    return False


# ---------------------------------------------------------------------------
# The retitle job
# ---------------------------------------------------------------------------

def _retitle(ctx: Any, session_id: str, digest: str) -> str:
    """Ask the aux tier for a title from a prebuilt digest; persist at llm rank.

    Returns ``"ok"``, ``"no_title"``, ``"write_failed"`` or ``"error"``. Only
    ``write_failed`` gives the claimed boundary back: the title existed and was
    lost, so the next turn should try again, while a model that returns nothing
    must not be hammered every turn.
    """
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
            task=AUX_TASK,
            purpose="session-retitle",
        )
        parsed = getattr(result, "parsed", None)
        title = _clean_title((parsed or {}).get("title") if isinstance(parsed, dict) else None)
        if not title:
            logger.debug("sessionretitler: model gave no usable title")
            return "no_title"

        import persistence_assembly

        with persistence_assembly.open_persistence(
            persistence_assembly.profile_scope()
        ) as store:
            ok = _write_llm_title(store.sessions, session_id, title)
            if ok:
                logger.info("sessionretitler: renamed %s -> %r", session_id, title)
                return "ok"
            return "write_failed"
    except Exception:
        # Never let a background rename disturb the host process.
        logger.debug("sessionretitler: retitle failed", exc_info=True)
        return "error"


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
    entry = (_load_counts(ctx).get(session_id) or {})
    last = _last_retitle_n(entry)
    if n < last:
        last = n  # compaction shrank the history; _record_count rebases the same way
    if n - last < interval:
        _record_count(ctx, session_id, n, interval=interval)
        return
    # Boundary reached: snapshot first (the triggering prompt counts, so the
    # digest must see it), then gate on usable pairs BEFORE claiming, so a
    # thin digest never burns the boundary.
    snapshot = build_snapshot(history, extra_user)
    digest = build_digest(snapshot, _cfg(ctx, "max_pairs"))
    pairs = len(re.findall(r"(?m)^USER: ", digest))
    if pairs < _cfg(ctx, "min_pairs"):
        logger.debug("sessionretitler: only %d pairs; skipping", pairs)
        _record_count(ctx, session_id, n, interval=interval)
        return
    previous, claimed = _record_count(ctx, session_id, n, claim=True, interval=interval)
    if not claimed:
        return
    try:
        # Off-thread by design: hook callbacks must not block a turn. A
        # failure here only logs; the turn is never disturbed.
        ctx_copy = contextvars.copy_context()
        thread = threading.Thread(
            target=ctx_copy.run,
            args=(_retitle_and_release, ctx, session_id, digest, previous),
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


def _retitle_and_release(
    ctx: Any, session_id: str, digest: str, previous: Optional[int] = None,
) -> None:
    try:
        status = _retitle(ctx, session_id, digest)
    finally:
        with _counter_lock:
            _inflight.discard(session_id)
    if status == "write_failed":
        _release_claim(ctx, session_id, previous)


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
    try:
        state_path = getattr(ctx.state, "path", "?")
    except Exception:
        state_path = "?"  # validate probe has no state store; callbacks get the real one
    logger.info(
        "sessionretitler: loading (state at %s, interval=%s, count=user_messages)",
        state_path,
        _cfg(ctx, "interval"),
    )

    def on_pre_llm_call(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        history = kwargs.get("conversation_history") or []
        user_message = kwargs.get("user_message")
        try:
            _on_pre_llm_call(ctx, session_id, history, user_message if isinstance(user_message, str) else None)
        except Exception:
            logger.debug("sessionretitler: pre_llm_call handler failed", exc_info=True)

    def on_post_llm_call(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        history = kwargs.get("conversation_history") or []
        try:
            _on_post_llm_call(ctx, session_id, history)
        except Exception:
            logger.debug("sessionretitler: post_llm_call handler failed", exc_info=True)

    def on_session_reset(**kwargs):
        session_id = str(kwargs.get("session_id") or "")
        try:
            _on_session_reset(ctx, session_id)
        except Exception:
            logger.debug("sessionretitler: reset handler failed", exc_info=True)

    ctx.register_hook("pre_llm_call", on_pre_llm_call)
    ctx.register_hook("post_llm_call", on_post_llm_call)
    ctx.register_hook("on_session_reset", on_session_reset)
    ctx.register_auxiliary_task(
        AUX_TASK,
        display_name="Session title",
        description="Rename a session from the latest exchanges.",
        inherit_from="title_generation",
    )
