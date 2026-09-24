"""RSS Reader desktop UI and slash-command bridge."""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any


_REFRESH_RE = re.compile(r"^(?P<minutes>[1-9]\d{0,3})m$", re.IGNORECASE)
_REFINE_RE = re.compile(r"^(?P<days>[1-9]\d{0,2})d$", re.IGNORECASE)
_ALLOWED_MINUTES = {5, 10, 15, 30, 60, 120, 180}
_MAX_DAYS = 365
_MAX_TEXT = 200

#: Last frame handed to ``broadcast_plugin_event``. Test seam: the bridge is a
#: fire-and-forget transport with no delivery receipt in a bare process.
_LAST_EVENT: dict[str, Any] = {}


def _hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes"
    return Path.home() / ".hermes"


def _usage() -> str:
    return (
        "Usage: /rss refresh [5m|10m|15m|30m|60m|120m|180m] | /rss mute <keyword|tag <key>> | "
        "/rss unmute <keyword or tag> | /rss tag <key> <article> | /rss untag <article> | "
        "/rss refine [starred|XXd] | /rss add <url or website>[, name] [to <folder>] | "
        "/rss remove <feed> | /rss find <text> | /rss mark-read {all|feed <name>|folder <name>} | "
        "/rss digest {unread [XXd]|saved} | /rss health"
    )


def _parse(raw_args: str) -> tuple[str, dict[str, Any]] | None:
    raw = str(raw_args or "").strip()
    if not raw or raw.lower() in {"help", "--help", "-h"}:
        return None

    parts = raw.split(None, 1)
    action = parts[0].lower()
    rest = parts[1].strip() if len(parts) == 2 else ""

    if action == "refresh":
        if not rest:
            return "refresh", {}
        match = _REFRESH_RE.fullmatch(rest)
        if not match or int(match.group("minutes")) not in _ALLOWED_MINUTES:
            raise ValueError("Refresh period must be 5m, 10m, 15m, 30m, 60m, 120m, or 180m.")
        return "refresh-period", {"minutes": int(match.group("minutes"))}

    if action == "mute":
        lowered = rest.lower()
        if lowered.startswith("tag "):
            key = rest[4:].strip()
            if not key:
                raise ValueError("Usage: /rss mute tag <tag key>")
            return "add-filter", {"kind": "tag", "tag": key}
        phrase = rest[:_MAX_TEXT].strip()
        if not phrase:
            raise ValueError("Usage: /rss mute <keyword or phrase> | /rss mute tag <tag key>")
        return "add-filter", {"kind": "keyword", "phrase": phrase}

    if action == "unmute":
        target = rest[:_MAX_TEXT].strip()
        if not target:
            raise ValueError("Usage: /rss unmute <keyword or tag>")
        return "remove-filter", {"phrase": target}

    if action == "tag":
        bits = rest.split(None, 1)
        if len(bits) != 2:
            raise ValueError("Usage: /rss tag <tag key> <article title or id>")
        return "tag", {"tag": bits[0], "title": bits[1], "id": bits[1]}

    if action == "untag":
        target = rest[:_MAX_TEXT].strip()
        if not target:
            raise ValueError("Usage: /rss untag <article title or id>")
        return "untag", {"title": target, "id": target}

    if action == "refine":
        if rest.lower() in {"starred", "stars"}:
            return "refine-starred", {}
        if not rest:
            return "refine", {"days": 30}
        match = _REFINE_RE.fullmatch(rest)
        if not match or int(match.group("days")) > _MAX_DAYS:
            raise ValueError("Refinement period must be 1d to 365d, for example 30d. Use /rss refine starred for starred articles.")
        return "refine", {"days": int(match.group("days"))}

    if action == "mark-read":
        parts = rest.split(None, 1)
        scope = parts[0].lower() if parts else ""
        if scope == "all" and len(parts) == 1:
            return "mark-read", {"scope": "all"}
        if scope not in {"feed", "folder"} or len(parts) != 2 or not parts[1].strip():
            raise ValueError("Usage: /rss mark-read all | feed <name> | folder <name>")
        return "mark-read", {"scope": scope, "target": parts[1].strip()[:100]}

    if action == "digest":
        parts = rest.split(None, 1)
        scope = parts[0].lower() if parts else ""
        if scope == "saved" and len(parts) == 1:
            return "digest", {"scope": "saved"}
        if scope != "unread":
            raise ValueError("Usage: /rss digest unread [XXd] | saved")
        if len(parts) == 1:
            return "digest", {"scope": "unread", "days": None}
        match = _REFINE_RE.fullmatch(parts[1].strip())
        if not match or int(match.group("days")) > _MAX_DAYS:
            raise ValueError("Digest period must be 1d to 365d, for example 7d.")
        return "digest", {"scope": "unread", "days": int(match.group("days"))}

    if action == "health":
        if rest:
            raise ValueError("Usage: /rss health")
        return "health", {}

    if action == "add":
        match = re.fullmatch(r"(.+?)\s+to\s+(.+)", rest, re.IGNORECASE)
        source = (match.group(1) if match else rest).strip()[:_MAX_TEXT]
        folder = (match.group(2) if match else "").strip()[:100]
        if not source:
            raise ValueError("Give a feed URL or website name to add.")
        return "add", {"source": source, "folder": folder}

    if action in {"remove", "unsubscribe"}:
        target = rest[:100].strip()
        if not target:
            raise ValueError("Usage: /rss remove <feed name or url>")
        return "remove", {"target": target}

    if action in {"find", "search"}:
        phrase = rest[:_MAX_TEXT].strip()
        if not phrase:
            raise ValueError("Usage: /rss find <text in titles or article bodies>")
        return "find", {"query": phrase}

    raise ValueError(f"Unknown RSS action '{action}'. {_usage()}")


def _enqueue(action: str, payload: dict[str, Any], reply: bool = False) -> str:
    """Push a command to the desktop half over the public plugin event bridge.

    Replaces the legacy ``rss-reader/commands.jsonl`` file queue: the frame
    lands in every connected desktop window, where ``host.onEvent`` runs the
    command handler. ``reply=True`` commands still write result files that
    ``_wait_result`` consumes.
    """
    try:
        from hermes_cli.plugin_events import broadcast_plugin_event
    except ImportError:
        raise RuntimeError("RSS Reader command bridge is unavailable; no command was sent.") from None
    command_id = str(uuid.uuid4())
    record = {
        "id": command_id,
        "action": action,
        "payload": payload,
        "reply": bool(reply),
        "created_at": time.time(),
    }
    _LAST_EVENT.clear()
    _LAST_EVENT.update({"event": "plugin.rss-reader.command", "payload": record})
    broadcast_plugin_event("rss-reader", "command", record)
    return command_id


def _wait_result(command_id: str, timeout: float = 45.0) -> str:
    path = _hermes_home() / "rss-reader" / "results" / f"{command_id}.json"
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                time.sleep(0.25)
                continue
            try:
                path.unlink()
            except OSError:
                pass
            if not isinstance(data, dict):
                return "RSS Reader returned an unreadable result."
            if not data.get("ok"):
                return f"RSS Reader: {str(data.get('error') or 'command failed')[:400]}"
            result = data.get("result") or {}
            articles = result.get("articles") if isinstance(result, dict) else None
            if not isinstance(articles, list):
                return json.dumps(result, ensure_ascii=True)[:50000]
            query = result.get("query") or ""
            if not articles:
                return f"No article titles match {query}." if query else "No matching article titles."
            lines = [f"{result.get('count', len(articles))} title match{'es' if result.get('count', len(articles)) != 1 else ''} for {query}. Reading {len(articles)} post{'s' if len(articles) != 1 else ''}:"]
            for article in articles:
                title = str(article.get("title") or "Untitled")
                feed = str(article.get("feed") or "")
                url = str(article.get("url") or "")
                body = str(article.get("body") or article.get("excerpt") or "").strip()
                lines.append("")
                lines.append(f"## {title}" + (f" ({feed})" if feed else ""))
                if url:
                    lines.append(url)
                if body:
                    lines.append(body[:8000])
            extra = result.get("more_titles") if isinstance(result, dict) else None
            if isinstance(extra, list) and extra:
                lines.append("")
                lines.append(f"{len(extra)} more title matches:")
                for article in extra[:40]:
                    title = str(article.get("title") or "Untitled")
                    feed = str(article.get("feed") or "")
                    lines.append(f"- {title}" + (f" ({feed})" if feed else ""))
            return "\n".join(lines)[:50000]
        time.sleep(0.35)
    return "RSS Reader did not answer. Keep Hermes desktop running and try again."


def _handle(raw_args: str) -> str:
    try:
        parsed = _parse(raw_args)
        if parsed is None:
            return _usage()
        action, payload = parsed
        if action == "find":
            return _wait_result(_enqueue(action, payload, reply=True))
        _enqueue(action, payload)
    except RuntimeError as exc:
        return f"RSS Reader could not send the command: {exc}"
    except ValueError as exc:
        return f"RSS Reader: {exc}"
    except OSError as exc:
        return f"RSS Reader could not queue the command: {exc}"

    if action == "refresh":
        return "RSS Reader refresh queued."
    if action == "refresh-period":
        return f"RSS Reader refresh period change queued: every {payload['minutes']} minutes."
    if action == "refine":
        return f"RSS Reader refinement queued for the last {payload['days']} days."
    if action == "refine-starred":
        return "RSS Reader starred-interest refinement queued."
    if action == "mark-read":
        scope = payload["scope"] if payload["scope"] == "all" else f"{payload['scope']} {payload['target']}"
        return f"RSS Reader mark-read queued for {scope}."
    if action == "digest":
        period = f" from the last {payload['days']} days" if payload.get("days") else ""
        return f"RSS Reader {payload['scope']} digest queued{period}."
    if action == "health":
        return "RSS Reader health check queued."
    if action == "remove":
        return f"RSS Reader unsubscribe queued for {payload['target']}."
    if action == "tag":
        return f"RSS Reader tag queued: {payload.get('tag')} on {payload.get('title') or payload.get('id')}."
    if action == "untag":
        return f"RSS Reader untag queued for {payload.get('title') or payload.get('id')}."
    if action == "add-filter":
        if payload.get("kind") == "tag":
            return f"RSS Reader tag filter queued for {payload.get('tag')}."
        return f"RSS Reader keyword filter queued for {payload.get('phrase')}."
    if action == "remove-filter":
        return f"RSS Reader filter removal queued for {payload.get('phrase') or payload.get('tag') or payload.get('id')}."
    return f"RSS Reader subscription queued for {payload['source']}."


def register(ctx=None):
    if ctx is not None:
        ctx.register_command(
            "rss",
            handler=_handle,
            description="Control RSS Reader feeds, refresh, mutes, grading, triage, and health.",
            args_hint="refresh [5m|10m|15m|30m|60m|120m|180m] | mute <keyword|tag <key>> | unmute <keyword or tag> | tag <key> <article> | untag <article> | refine [starred|XXd] | add <website> [to <folder>] | remove <feed> | find <text> | mark-read {all|feed <name>|folder <name>} | digest {unread [XXd]|saved} | health",
            argument_mode="mixed",
        )
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "rss_reader_tools",
            Path(__file__).with_name("tools.py"),
        )
        tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tools)
        ctx.register_tool(
            name="rss",
            toolset="rss-reader",
            schema=tools.RSS_SCHEMA,
            handler=tools.handle_rss,
            check_fn=tools.tools_enabled,
            description=tools.RSS_SCHEMA["description"],
            emoji="📰",
        )
    return None


__all__ = ["register", "_handle", "_parse"]
