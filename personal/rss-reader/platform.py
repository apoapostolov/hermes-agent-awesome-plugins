"""Automation blueprints and gateway platform handlers for RSS Reader.

Two surfaces ride on the public ``register(ctx)`` API:

1. The ``rss-reader:daily-digest`` automation blueprint, a fill-in-the-blanks
   cron automation (``/blueprint``, the dashboard Blueprints tab, the Desktop
   Cron page) whose scheduled prompt builds a digest through the ``rss`` tool.
2. Gateway platform handlers for telegram and discord. The factory captures the
   platform's own client at connect time, so a slash command can post a digest
   message with inline buttons, and pattern-scoped callback handlers act on
   Save / Open / Mute without touching core button flows.

Everything here degrades: no platform connected means the plain digest text is
returned instead of a post, and every SDK import lives inside the function that
needs it so ``register()`` works on hosts without those packages.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
from typing import Any, Callable, Optional

#: Callback data prefix. Scoped so it can never swallow core button flows.
_CALLBACK_PREFIX = "rss:"
#: Hard cap from the platforms themselves (Telegram allows 64 bytes).
_MAX_CALLBACK_DATA = 64
#: Message size caps.
_TG_TEXT_CAP = 4000
_DC_TEXT_CAP = 1900
#: Articles in one posted digest.
_MAX_ARTICLES = 12
#: Seconds the sync slash-command path waits for a post to land.
_SEND_TIMEOUT = 25.0

#: Platform senders captured at connect time: platform -> sender dict with the
#: gateway event loop plus async ``post`` / ``edit`` callables.
_senders: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()

#: Bridge handles wired at registration. ``run`` waits for a desktop result;
#: ``enqueue`` is fire-and-forget for mutations.
_run_bridge: Optional[Callable[..., str]] = None
_enqueue_bridge: Optional[Callable[..., str]] = None


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

_DIGEST_SLOTS: list[dict[str, Any]] = [
    {
        "name": "time",
        "type": "time",
        "label": "What time should the digest arrive?",
        "default": "08:30",
        "help": "24h local time, for example 08:30",
    },
    {
        "name": "recurrence",
        "type": "enum",
        "label": "Which days?",
        "default": "everyday",
        "options": ["everyday", "weekdays", "weekends"],
        "help": "everyday, weekdays, or weekends",
    },
    {
        "name": "scope",
        "type": "enum",
        "label": "Which articles?",
        "default": "unread",
        "options": ["unread", "saved", "all"],
        "help": "unread, saved, or all articles",
    },
    {
        "name": "feed",
        "type": "text",
        "label": "Limit to one feed or folder",
        "default": "all subscriptions",
        "help": "A feed or folder name, or 'all subscriptions' for everything",
    },
    {
        "name": "deliver",
        "type": "enum",
        "label": "Where to deliver?",
        "default": "origin",
        "options": ["origin", "local", "telegram", "discord", "email"],
        "strict": False,
        "help": "origin = the chat you set this up from, or any connected platform",
    },
]

_DIGEST_PROMPT = (
    "Build an RSS digest from the user's RSS Reader subscriptions. "
    "Use the rss tool with action=list_articles, view={scope}, limit 40. "
    "The feed or folder filter is set to \"{feed}\"; when it is anything other "
    "than \"all subscriptions\", pass folder=\"{feed}\" to the tool as well. "
    "Group the top stories by feed, one line per story with its link, then "
    "close with a one-sentence pick of what to read first. Skip muted topics "
    "and keep the whole digest under 500 words. If the rss tool is not "
    "available because Hermes tools are not registered, tell the user to turn "
    "on Register Hermes Tools in RSS Reader settings and stop."
)


def _register_blueprint(ctx: Any) -> None:
    ctx.register_automation_blueprint(
        "daily-digest",
        title="RSS daily digest",
        description=(
            "Summarize new articles from your RSS Reader subscriptions into a "
            "short digest, on the days and at the time you pick."
        ),
        category="reading",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=_DIGEST_PROMPT,
        slots=_DIGEST_SLOTS,
        deliver_default="origin",
        tags=["rss", "digest", "daily"],
    )


# ---------------------------------------------------------------------------
# Platform senders
# ---------------------------------------------------------------------------

def _tg_senders(native: Any) -> dict[str, Any]:
    async def post(chat_id: str, thread_id: str, text: str, buttons: list) -> None:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        await native.bot.send_message(
            chat_id=chat_id,
            text=text[:_TG_TEXT_CAP],
            reply_markup=InlineKeyboardMarkup(_tg_rows(buttons)),
            message_thread_id=int(thread_id) if thread_id else None,
            disable_web_page_preview=True,
        )

    async def edit(chat_id: str, message_id: str, text: str, buttons: Optional[list] = None) -> None:
        kwargs: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": int(message_id),
            "text": text[:_TG_TEXT_CAP],
            "disable_web_page_preview": True,
        }
        if buttons is not None:
            kwargs["reply_markup"] = InlineKeyboardMarkup(_tg_rows(buttons))
        await native.bot.edit_message_text(**kwargs)

    return {"post": post, "edit": edit}


def _tg_rows(buttons: list) -> list:
    from telegram import InlineKeyboardButton

    rows = []
    for row in buttons:
        cells = []
        for label, data, url in row:
            if data:
                cells.append(InlineKeyboardButton(text=label, callback_data=data[:_MAX_CALLBACK_DATA]))
            else:
                cells.append(InlineKeyboardButton(text=label, url=url))
        rows.append(cells)
    return rows


def _dc_senders(native: Any) -> dict[str, Any]:
    async def post(chat_id: str, thread_id: str, text: str, buttons: list) -> None:
        import discord

        channel = native.get_channel(int(chat_id))
        if channel is None:
            channel = await native.fetch_channel(int(chat_id))
        view = discord.ui.View(timeout=None)
        for row in buttons:
            for label, data, url in row:
                if data:
                    view.add_item(discord.ui.Button(
                        label=label,
                        custom_id=data[:_MAX_CALLBACK_DATA],
                        style=discord.ButtonStyle.secondary,
                    ))
                else:
                    view.add_item(discord.ui.Button(label=label, url=url))
        await channel.send(content=text[:_DC_TEXT_CAP], view=view)

    async def edit(chat_id: str, message_id: str, text: str, buttons: Optional[list] = None) -> None:
        import discord

        channel = native.get_channel(int(chat_id))
        if channel is None:
            channel = await native.fetch_channel(int(chat_id))
        message = await channel.fetch_message(int(message_id))
        view = discord.ui.View(timeout=None)
        for row in (buttons or []):
            for label, data, url in row:
                if data:
                    view.add_item(discord.ui.Button(
                        label=label,
                        custom_id=data[:_MAX_CALLBACK_DATA],
                        style=discord.ButtonStyle.secondary,
                    ))
                else:
                    view.add_item(discord.ui.Button(label=label, url=url))
        await message.edit(content=text[:_DC_TEXT_CAP], view=view)

    return {"post": post, "edit": edit}


def _telegram_factory(native: Any, adapter: Any) -> None:
    """Wire a pattern-scoped CallbackQueryHandler into the PTB Application."""
    loop = asyncio.get_running_loop()
    from telegram.ext import CallbackQueryHandler

    async def _on_button(update: Any, context: Any) -> None:
        try:
            query = update.callback_query
            data = str(getattr(query, "data", "") or "")
            if not data.startswith(_CALLBACK_PREFIX):
                return
            message = getattr(query, "message", None)
            await _on_callback(
                data,
                chat_id=str(getattr(message, "chat_id", "") or ""),
                message_id=str(getattr(message, "message_id", "") or ""),
                ack=lambda note: query.answer(note),
            )
        except Exception:
            # A broken button can never take the platform down.
            pass

    # PTB dispatches only the first matching handler per group, and core
    # registers a catch-all CallbackQueryHandler, so the pattern is mandatory.
    native.add_handler(CallbackQueryHandler(_on_button, pattern=f"^{_CALLBACK_PREFIX}"))
    with _lock:
        _senders["telegram"] = {"loop": loop, **_tg_senders(native)}


def _discord_factory(native: Any, adapter: Any) -> None:
    """Listen for interactions whose custom_id carries the rss: prefix."""
    loop = asyncio.get_running_loop()

    async def _on_interaction(interaction: Any) -> None:
        try:
            data = getattr(interaction, "data", None) or {}
            custom_id = str(data.get("custom_id") or "")
            if not custom_id.startswith(_CALLBACK_PREFIX):
                return
            message = getattr(interaction, "message", None)
            await _on_callback(
                custom_id,
                chat_id=str(getattr(interaction, "channel_id", "") or ""),
                message_id=str(getattr(message, "id", "") or ""),
                ack=lambda note: interaction.response.send_message(note, ephemeral=True),
            )
        except Exception:
            pass

    native.add_listener(_on_interaction, "on_interaction")
    with _lock:
        _senders["discord"] = {"loop": loop, **_dc_senders(native)}


def _register_platforms(ctx: Any) -> None:
    ctx.register_platform_handler("telegram", _telegram_factory)
    ctx.register_platform_handler("discord", _discord_factory)


# ---------------------------------------------------------------------------
# Digest rendering and posting
# ---------------------------------------------------------------------------

def _session(name: str) -> str:
    """Read a gateway session variable, falling back to the process env.

    Same read the core's own /blueprint command uses to resolve its delivery
    origin (hermes_cli/blueprint_cmd.py::_resolve_origin): the gateway binds
    ContextVars, so os.environ alone can be empty in gateway mode. Wrapped in
    try/except so a missing module degrades to the process env instead of
    breaking the command.
    """
    try:
        from gateway.session_context import get_session_env

        return str(get_session_env(name) or "")
    except Exception:
        return str(os.environ.get(name, "") or "")


def _parse_articles(raw: str) -> list[dict[str, Any]]:
    """Pull the article list out of a bridge result, tolerating shapes."""
    text = str(raw or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return []
    payload = data
    if isinstance(payload, dict):
        for key in ("result", "data", "payload"):
            if isinstance(payload.get(key), (dict, list)):
                payload = payload[key]
                break
    articles = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(articles, list):
        return []
    return [row for row in articles if isinstance(row, dict)]


def _render_digest(articles: list[dict[str, Any]], scope: str) -> tuple[str, list]:
    """Build the digest text plus one button row per article."""
    lines = [f"RSS digest ({scope}, {len(articles)} article{'s' if len(articles) != 1 else ''})", ""]
    buttons: list[list[tuple[str, str, str]]] = []
    for row in articles[:_MAX_ARTICLES]:
        title = str(row.get("title") or "Untitled").strip() or "Untitled"
        feed = str(row.get("feed") or "").strip()
        article_id = str(row.get("id") or "").strip()
        url = str(row.get("url") or "").strip()
        grade = str(row.get("grade") or "").strip()
        head = f"- {title}" + (f" [{grade}]" if grade else "") + (f" ({feed})" if feed else "")
        lines.append(head)
        if url:
            lines.append(f"  {url}")
        if article_id and url:
            buttons.append([
                ("Save", f"{_CALLBACK_PREFIX}s:{article_id}", ""),
                ("Open", "", url),
                ("Mute feed", f"{_CALLBACK_PREFIX}m:{article_id}", ""),
            ])
    hidden = len(articles) - _MAX_ARTICLES
    if hidden > 0:
        lines.append("")
        lines.append(f"...and {hidden} more in RSS Reader.")
    return "\n".join(lines), buttons


def post_digest(scope: str = "unread", feed: str = "", limit: int = _MAX_ARTICLES) -> str:
    """Post an interactive digest to the current gateway chat.

    CLI and no-sender cases return the rendered digest text instead.
    """
    if _run_bridge is None:
        return "RSS Reader bridge is unavailable; restart the plugin."
    payload: dict[str, Any] = {"view": scope if scope in {"unread", "saved", "all"} else "unread", "limit": max(1, min(limit, _MAX_ARTICLES))}
    if feed and feed.lower() != "all subscriptions":
        payload["folder"] = feed
    raw = _run_bridge("list-articles", payload)
    articles = _parse_articles(raw)
    if not articles:
        if "did not answer" in str(raw):
            return str(raw)
        return f"No {scope} articles in RSS Reader."

    platform = _session("HERMES_SESSION_PLATFORM")
    chat_id = _session("HERMES_SESSION_CHAT_ID")
    thread_id = _session("HERMES_SESSION_THREAD_ID")
    sender = _senders.get(platform)
    if not platform or not chat_id or sender is None:
        text, _buttons = _render_digest(articles, scope)
        return text

    text, buttons = _render_digest(articles, scope)
    try:
        future = asyncio.run_coroutine_threadsafe(
            sender["post"](chat_id, thread_id, text, buttons), sender["loop"]
        )
        future.result(timeout=_SEND_TIMEOUT)
    except Exception as exc:
        return f"RSS digest could not post to {platform}: {exc.__class__.__name__}."
    return f"RSS digest posted to {platform} ({len(articles[:_MAX_ARTICLES])} articles)."


# ---------------------------------------------------------------------------
# Callback handling
# ---------------------------------------------------------------------------

_VERBS = {"s": "save", "m": "mute"}


async def _on_callback(data: str, chat_id: str, message_id: str, ack) -> None:
    """Act on one inline button press and refresh the message."""
    parts = data.split(":", 2)
    if len(parts) != 3 or not parts[2]:
        return
    verb, article_id = parts[1], parts[2]
    label = _VERBS.get(verb)
    if label is None or _enqueue_bridge is None:
        return
    note = ""
    if label == "save":
        _enqueue_bridge("star", {"id": article_id, "saved": True})
        note = "Saved to starred."
    elif label == "mute":
        feed = _lookup_feed_title(article_id)
        if feed:
            _enqueue_bridge("add-filter", {"kind": "keyword", "phrase": feed})
            note = f"Muted {feed}."
        else:
            note = "Could not find that feed."
    try:
        if note:
            await ack(note)
    except Exception:
        pass
    if chat_id and message_id:
        try:
            sender = _senders.get("telegram") or _senders.get("discord")
            platform = "telegram" if "telegram" in _senders and sender is _senders.get("telegram") else "discord"
            sender = _senders.get(platform)
            if sender is not None:
                await sender["edit"](chat_id, message_id, note or "Done.", buttons=[])
        except Exception:
            pass


def _lookup_feed_title(article_id: str) -> str:
    """Resolve an article's feed title through the reply-wired bridge."""
    if _run_bridge is None:
        return ""
    try:
        articles = _parse_articles(_run_bridge("get-article", {"id": article_id}))
    except Exception:
        return ""
    if not articles:
        return ""
    return str(articles[0].get("feed") or "").strip()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def register_extras(ctx: Any, run: Callable[..., str], enqueue: Callable[..., str]) -> None:
    """Register the blueprint and the platform handlers for this plugin."""
    global _run_bridge, _enqueue_bridge
    _run_bridge = run
    _enqueue_bridge = enqueue
    _register_blueprint(ctx)
    _register_platforms(ctx)
