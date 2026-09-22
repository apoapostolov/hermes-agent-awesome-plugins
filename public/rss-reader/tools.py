"""RSS Reader Hermes tools. Gated by Settings → Register Hermes Tools."""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

_ACTIONS = (
    "list_feeds",
    "list_articles",
    "find",
    "get_article",
    "capture_article",
    "add_feed",
    "remove_feed",
    "move_feed",
    "list_folders",
    "add_folder",
    "refresh",
    "health",
    "tag_article",
    "untag_article",
    "reclassify",
    "list_filters",
    "add_filter",
    "remove_filter",
    "mark_read",
    "star",
)

RSS_SCHEMA = {
    "name": "rss",
    "description": (
        "When the user refers to RSS, RSS Reader, feeds, or an article they saw there, use this tool as library context. "
        "find searches titles, summaries, and full captured text; put distinctive topic words in query (example: paizo), not filler like 'that article'. "
        "get_article loads one post by id. list_articles lists recent rows. Hermes desktop must be running; the RSS Reader page does not need to be open."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": list(_ACTIONS),
                "description": "Library action to run.",
            },
            "query": {"type": "string", "description": "Search phrase for find. Matches titles, summaries, and full article text. Use topic words, not 'rss article'."},
            "view": {
                "type": "string",
                "enum": ["all", "unread", "saved"],
                "description": "Article list view. Default all.",
            },
            "feed": {"type": "string", "description": "Feed title or id."},
            "folder": {"type": "string", "description": "Folder name."},
            "url": {"type": "string", "description": "Feed or website URL for add_feed."},
            "id": {"type": "string", "description": "Article or feed id."},
            "title": {"type": "string", "description": "Article or feed title when id is unknown."},
            "limit": {"type": "integer", "description": "Max articles to return (1-80)."},
            "phrase": {"type": "string", "description": "Mute keyword, or the filter to remove."},
            "tag": {"type": "string", "description": "Grading tag key or label (important, interesting, spam, ...)."},
            "kind": {"type": "string", "enum": ["keyword", "tag"], "description": "Filter type for add_filter. Default keyword."},
            "saved": {"type": "boolean", "description": "Star (true) or unstar (false). Default true."},
        },
        "required": ["action"],
    },
}


def _hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME")
    if configured:
        return Path(configured)
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "hermes"
    return Path.home() / ".hermes"


def tools_enabled() -> bool:
    path = _hermes_home() / "rss-reader" / "tools-enabled.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return False
    return bool(isinstance(data, dict) and data.get("enabled") is True)


def _enqueue(action: str, payload: dict[str, Any]) -> str:
    path = _hermes_home() / "rss-reader" / "commands.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "id": str(uuid.uuid4()),
        "action": action,
        "payload": payload,
        "reply": True,
        "created_at": time.time(),
    }
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, separators=(",", ":")) + "\n")
    return record["id"]


def _wait_result(command_id: str, timeout: float = 90.0) -> str:
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
            result = data.get("result")
            if result is None:
                return "RSS Reader finished."
            if isinstance(result, str):
                return result[:50000]
            return json.dumps(result, ensure_ascii=True, indent=2)[:50000]
        time.sleep(0.35)
    return "RSS Reader did not answer. Keep Hermes desktop running and try again."


def _run(action: str, payload: dict[str, Any], timeout: float = 90.0) -> str:
    if not tools_enabled():
        return "RSS tools are off. Turn on Register Hermes Tools in RSS Reader settings."
    return _wait_result(_enqueue(action, payload), timeout)


def handle_rss(args: dict[str, Any], **_extra: Any) -> str:
    action = str(args.get("action") or "").strip()
    if action not in _ACTIONS:
        return f"Unknown RSS action '{action}'."
    feed = str(args.get("feed") or "").strip()
    folder = str(args.get("folder") or "").strip()
    ident = str(args.get("id") or "").strip()
    title = str(args.get("title") or "").strip()
    url = str(args.get("url") or "").strip()
    query = str(args.get("query") or "").strip()
    view = str(args.get("view") or "all").strip() or "all"
    phrase = str(args.get("phrase") or "").strip()
    limit = args.get("limit")
    saved = args.get("saved")
    if action == "list_feeds":
        return _run("list-feeds", {})
    if action == "list_folders":
        return _run("list-folders", {})
    if action == "list_articles":
        return _run("list-articles", {
            "query": query,
            "view": view,
            "feed": feed,
            "folder": folder,
            "limit": limit,
        })
    if action == "find":
        if not query:
            return "Give a search phrase."
        return _run("find", {"query": query, "limit": limit, "feed": feed, "folder": folder})
    if action == "get_article":
        return _run("get-article", {"id": ident, "title": title, "url": url})
    if action == "capture_article":
        return _run("capture", {"id": ident, "title": title, "url": url}, timeout=120.0)
    if action == "add_feed":
        source = url or title or feed
        if not source:
            return "Give a feed URL or website to add."
        return _run("add", {"source": source, "folder": folder}, timeout=120.0)
    if action == "remove_feed":
        return _run("remove", {"target": ident or title or feed})
    if action == "move_feed":
        return _run("move-feed", {"target": ident or title or feed, "folder": folder})
    if action == "add_folder":
        if not folder:
            return "Give a folder name."
        return _run("add-folder", {"name": folder})
    if action == "refresh":
        payload: dict[str, Any] = {}
        if ident or title or feed:
            payload["target"] = ident or title or feed
        return _run("refresh", payload, timeout=180.0)
    if action == "health":
        return _run("health", {})
    if action == "tag_article":
        tag = str(args.get("tag") or "").strip()
        if not tag:
            return "Give a tag key."
        return _run("tag", {"tag": tag, "id": ident, "title": title, "url": url})
    if action == "untag_article":
        return _run("untag", {"id": ident, "title": title, "url": url})
    if action == "reclassify":
        return _run("reclassify", {}, timeout=600.0)
    if action == "list_filters":
        return _run("list-filters", {})
    if action == "add_filter":
        kind = str(args.get("kind") or "").strip().lower()
        tag = str(args.get("tag") or "").strip()
        if kind == "tag" or (tag and not phrase):
            if not tag and not phrase:
                return "Give a tag key."
            return _run("add-filter", {"kind": "tag", "tag": tag or phrase})
        if not phrase and not query:
            return "Give a keyword."
        return _run("add-filter", {"kind": "keyword", "phrase": phrase or query})
    if action == "remove_filter":
        return _run("remove-filter", {
            "id": ident,
            "phrase": phrase or query,
            "tag": str(args.get("tag") or "").strip(),
        })
    if action == "mark_read":
        if folder:
            return _run("mark-read", {"scope": "folder", "target": folder})
        if ident or title or feed:
            return _run("mark-read", {"scope": "feed", "target": ident or title or feed})
        return _run("mark-read", {"scope": "all"})
    if action == "star":
        return _run("star", {
            "id": ident,
            "title": title,
            "url": url,
            "saved": False if saved is False else True,
        })
    return f"Unknown RSS action '{action}'."
