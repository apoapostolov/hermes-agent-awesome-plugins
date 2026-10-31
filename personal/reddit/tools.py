"""Tool schemas and handlers for the reddit plugin."""

from __future__ import annotations

import json

from . import client, login

# ---------------------------------------------------------------- schemas

LOGIN = {
    "name": "reddit_login",
    "description": (
        "Log the Reddit account in or out. action='start' returns a consent URL and "
        "waits on http://localhost:8080 for the callback; action='status' reports "
        "progress and finishes the exchange; action='complete' exchanges a pasted "
        "redirect URL or code when the catcher could not receive it; action='logout' "
        "deletes the stored refresh token."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["start", "status", "complete", "logout"],
                "description": "Login step to run (default: start).",
            },
            "value": {
                "type": "string",
                "description": "For action='complete': the full redirect URL or bare authorization code.",
            },
            "port": {
                "type": "integer",
                "description": "Loopback port for the OAuth callback (default 8080, must match the app's redirect URI).",
            },
            "redirect_uri": {
                "type": "string",
                "description": "Override the redirect URI registered on the Reddit app.",
            },
            "scope": {
                "type": "string",
                "description": "Space-separated scopes; defaults to every scope the account can grant.",
            },
        },
        "required": [],
    },
}

SETUP = {
    "name": "reddit_setup",
    "description": (
        "Configure the user's own Reddit API app. Call with no arguments to show "
        "what is configured; pass client_id and client_secret from "
        "https://www.reddit.com/prefs/apps to save and verify them. The secret is "
        "written to the plugin config file and never echoed back."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "client_id": {"type": "string", "description": "Reddit app client id (the short string under the app name)."},
            "client_secret": {"type": "string", "description": "Reddit app secret. Omit to keep the stored one."},
            "redirect_uri": {
                "type": "string",
                "description": "Redirect URI registered on the app (default http://localhost:8080).",
            },
            "user_agent": {
                "type": "string",
                "description": "User-Agent Reddit requires, e.g. hermes-reddit/0.2 (by /u/yourname).",
            },
            "validate": {
                "type": "boolean",
                "description": "Verify the credentials with a read-only request before saving (default true).",
            },
        },
        "required": [],
    },
}

STATUS = {
    "name": "reddit_status",
    "description": (
        "Show Reddit login state: token file, granted scopes, account identity and "
        "karma when a refresh token exists, plus the last rate-limit headers."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

API = {
    "name": "reddit_api",
    "description": (
        "Call any Reddit API endpoint directly with the logged-in account. Use this "
        "for everything the curated tools do not cover (mod actions, flair, wiki, "
        "multireddits, prefs, messages, awards, structured styles). Examples: "
        "GET /subreddits/mine/subscriber, GET /r/mod/about/moderators, "
        "POST /api/distinguish, GET /api/v1/me/karma, POST /api/mod/notes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "API path on oauth.reddit.com, e.g. /r/hermesagent/new or /api/v1/me.",
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "description": "HTTP method (default GET). Reddit expects POST form data for writes.",
            },
            "params": {
                "type": "object",
                "description": "Query parameters, e.g. {\"limit\": 10, \"sort\": \"new\"}.",
            },
            "data": {
                "type": "object",
                "description": "Form body for POST/PUT/DELETE writes.",
            },
            "app_only": {
                "type": "boolean",
                "description": "Use a read-only application token instead of the account token.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Response budget in characters (default 20000).",
            },
        },
        "required": ["path"],
    },
}

SUBREDDIT = {
    "name": "reddit_subreddit",
    "description": "List a subreddit's posts. sort is hot, best, new, top, rising or controversial.",
    "parameters": {
        "type": "object",
        "properties": {
            "subreddit": {"type": "string", "description": "Subreddit name without the r/ prefix."},
            "sort": {"type": "string", "description": "hot (default), best, new, top, rising, controversial."},
            "time": {"type": "string", "description": "For top/controversial: hour, day, week, month, year, all."},
            "limit": {"type": "integer", "description": "1-100 items (default 25)."},
            "after": {"type": "string", "description": "Fullname cursor from a previous page."},
        },
        "required": ["subreddit"],
    },
}

SEARCH = {
    "name": "reddit_search",
    "description": "Search Reddit posts, comments or subreddits, optionally restricted to one subreddit.",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query (Reddit syntax: site:, author:, flair:, etc.)."},
            "subreddit": {"type": "string", "description": "Restrict the search to this subreddit."},
            "sort": {"type": "string", "description": "relevance (default), hot, top, new, comments."},
            "time": {"type": "string", "description": "hour, day, week, month, year, all (default all)."},
            "type": {"type": "string", "description": "link, comment or sr; omit for all."},
            "limit": {"type": "integer", "description": "1-100 results (default 25)."},
        },
        "required": ["query"],
    },
}

THREAD = {
    "name": "reddit_thread",
    "description": "Fetch one post with its comment tree. Accepts a fullname, bare id or any Reddit URL.",
    "parameters": {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Post fullname (t3_...), id, or URL."},
            "sort": {"type": "string", "description": "best (default), top, new, controversial, old, qa."},
            "comment_limit": {"type": "integer", "description": "1-100 top-level comments (default 50)."},
            "depth": {"type": "integer", "description": "Reply nesting depth (default 4)."},
        },
        "required": ["id"],
    },
}

SUBMIT = {
    "name": "reddit_submit",
    "description": (
        "Create a post in a subreddit. kind='self' uses text, kind='link' uses url. "
        "This publishes publicly: confirm the exact subreddit, title and body first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "subreddit": {"type": "string", "description": "Target subreddit, no r/ prefix."},
            "title": {"type": "string", "description": "Post title."},
            "kind": {"type": "string", "enum": ["self", "link"], "description": "self (default) or link."},
            "text": {"type": "string", "description": "Markdown body for a self post."},
            "url": {"type": "string", "description": "Destination URL for a link post."},
            "flair_id": {"type": "string", "description": "Optional flair template id."},
            "nsfw": {"type": "boolean", "description": "Mark the post NSFW."},
            "spoiler": {"type": "boolean", "description": "Mark the post as a spoiler."},
        },
        "required": ["subreddit", "title"],
    },
}

COMMENT = {
    "name": "reddit_comment",
    "description": (
        "Reply to a post or comment. parent is a fullname: t3_ for a post, t1_ for a "
        "comment, t4_ for a private message. Publishes publicly."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "parent": {"type": "string", "description": "Fullname of the thing being replied to."},
            "text": {"type": "string", "description": "Markdown body of the reply."},
        },
        "required": ["parent", "text"],
    },
}

VOTE = {
    "name": "reddit_vote",
    "description": "Upvote, downvote or clear a vote on a post or comment.",
    "parameters": {
        "type": "object",
        "properties": {
            "thing": {"type": "string", "description": "Fullname such as t3_abc123 or t1_def456."},
            "direction": {
                "type": "integer",
                "description": "1 upvote, -1 downvote, 0 clear.",
            },
        },
        "required": ["thing", "direction"],
    },
}

MANAGE = {
    "name": "reddit_manage",
    "description": (
        "Lightweight account actions that do not post content: save/unsave, "
        "subscribe/unsubscribe, and hide/unhide a post or comment."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["save", "unsave", "subscribe", "unsubscribe", "hide", "unhide"],
                "description": "Action to perform.",
            },
            "target": {
                "type": "string",
                "description": "Fullname for save/hide, or subreddit name for subscribe.",
            },
        },
        "required": ["action", "target"],
    },
}

INBOX = {
    "name": "reddit_inbox",
    "description": "Read the account inbox: unread, inbox, sent, messages, mentions, modmail or mod mentions.",
    "parameters": {
        "type": "object",
        "properties": {
            "where": {
                "type": "string",
                "description": "unread (default), inbox, sent, messages, mentions, modmail, modunread.",
            },
            "limit": {"type": "integer", "description": "1-100 messages (default 25)."},
            "mark": {"type": "boolean", "description": "Mark returned items as read."},
        },
        "required": [],
    },
}

SCHEMAS = [SETUP, LOGIN, STATUS, API, SUBREDDIT, SEARCH, THREAD, SUBMIT, COMMENT, VOTE, MANAGE, INBOX]

# --------------------------------------------------------------- handlers


def _dumps(payload, max_chars: int = 20000) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if max_chars and len(text) > max_chars:
        return json.dumps(
            {
                "truncated": True,
                "budget": max_chars,
                "note": "Response exceeded the budget; narrow params (limit, path) or raise max_chars.",
                "head": text[:max_chars],
            },
            ensure_ascii=False,
        )
    return text


def _ok(payload) -> str:
    return json.dumps({"ok": True, "result": payload}, ensure_ascii=False, default=str)


def _err(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    if isinstance(exc, client.RedditError):
        return json.dumps({"ok": False, "error": message}, ensure_ascii=False)
    return json.dumps(
        {"ok": False, "error": message, "type": exc.__class__.__name__}, ensure_ascii=False
    )


def reddit_setup(args: dict, **kwargs) -> str:
    """Show or save the user's own Reddit app credentials."""
    try:
        creds = client.load_credentials()
        client_id = (args.get("client_id") or "").strip()
        secret = (args.get("client_secret") or "").strip()
        redirect = (args.get("redirect_uri") or "").strip()
        user_agent = (args.get("user_agent") or "").strip()

        if not client_id and not secret:
            config = client.load_config()
            return _ok(
                {
                    "configured": bool(creds["client_id"] and creds["client_secret"]),
                    "source": creds["source"] or None,
                    "client_id": creds["client_id"] or None,
                    "client_id_tail": creds["client_id"][-4:] if creds["client_id"] else None,
                    "client_secret_set": bool(creds["client_secret"]),
                    "redirect_uri": creds["redirect_uri"],
                    "user_agent": creds["user_agent"],
                    "config_file": str(client.config_path()),
                    "config_present": bool(config),
                    "logged_in": bool(client.load_token().get("refresh_token")),
                    "hint": client.SETUP_HINT if not creds["client_id"] else None,
                }
            )

        client_id = client_id or creds["client_id"]
        secret = secret or creds["client_secret"]
        if not client_id or not secret:
            return json.dumps(
                {
                    "ok": False,
                    "error": "Both client_id and client_secret are required the first "
                    "time. Get them from https://www.reddit.com/prefs/apps.",
                }
            )
        redirect = redirect or creds["redirect_uri"] or client.DEFAULT_REDIRECT_URI
        user_agent = user_agent or creds["user_agent"] or client.DEFAULT_USER_AGENT

        validation = None
        if args.get("validate") is not False:
            validation = client.validate_app(client_id, secret, user_agent)

        path = client.save_config(
            {
                "client_id": client_id,
                "client_secret": secret,
                "redirect_uri": redirect,
                "user_agent": user_agent,
            }
        )
        return _ok(
            {
                "saved": str(path),
                "client_id": client_id,
                "redirect_uri": redirect,
                "user_agent": user_agent,
                "validation": validation,
                "next": "Run reddit_login with action='start'. The app's redirect URI "
                f"must match {redirect} exactly.",
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_login(args: dict, **kwargs) -> str:
    action = (args.get("action") or "start").strip().lower()
    try:
        if action == "start":
            return _ok(
                login.start(
                    port=int(args.get("port") or 8080),
                    redirect_uri=(args.get("redirect_uri") or "").strip(),
                    scope=(args.get("scope") or "").strip(),
                )
            )
        if action == "status":
            return _ok(login.result())
        if action == "complete":
            code, state = login.parse_code(args.get("value") or "")
            return _ok(login.finish(code, state=state))
        if action == "logout":
            return _ok(login.logout())
        return json.dumps({"ok": False, "error": f"unknown action {action!r}"})
    except Exception as exc:  # noqa: BLE001 - surfaced to the agent
        return _err(exc)


def reddit_status(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        state = session.identity() if session.has_refresh_token else {
            "logged_in": False,
            "token_file": str(client.token_path()),
            "hint": "Run reddit_login with action='start' to authorize an account.",
        }
        creds = session.creds
        state["credentials"] = {
            "source": creds.get("source") or None,
            "client_id_tail": (creds["client_id"][-4:] if creds["client_id"] else ""),
            "client_secret_set": bool(creds["client_secret"]),
            "redirect_uri": creds["redirect_uri"],
            "user_agent": creds["user_agent"],
            "config_file": str(client.config_path()),
        }
        if not creds["client_id"] or not creds["client_secret"]:
            state["credentials"]["hint"] = client.SETUP_HINT
        return _ok(state)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_api(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        payload = session.request(
            (args.get("method") or "GET").upper(),
            args.get("path") or "",
            params=args.get("params") or None,
            data=args.get("data") or None,
            app_only=bool(args.get("app_only")),
        )
        result = payload
        if isinstance(payload, dict) and isinstance(payload.get("data"), dict):
            children = payload["data"].get("children")
            if isinstance(children, list):
                result = client.compact_listing(payload, limit=0)
        if isinstance(result, dict):
            result.setdefault("_rate", session.last_rate)
        return _dumps({"ok": True, "result": result}, int(args.get("max_chars") or 20000))
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_subreddit(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        return _ok(
            session.subreddit(
                args["subreddit"],
                sort=args.get("sort") or "hot",
                limit=int(args.get("limit") or 25),
                time_filter=args.get("time") or "",
                after=args.get("after") or "",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_search(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        return _ok(
            session.search(
                args["query"],
                subreddit=args.get("subreddit") or "",
                sort=args.get("sort") or "relevance",
                time_filter=args.get("time") or "all",
                limit=int(args.get("limit") or 25),
                kind=args.get("type") or "",
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_thread(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        return _ok(
            session.thread(
                args["id"],
                sort=args.get("sort") or "best",
                comment_limit=int(args.get("comment_limit") or 50),
                depth=int(args.get("depth") or 4),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_submit(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        payload = session.submit(
            args["subreddit"],
            args["title"],
            kind=args.get("kind") or "self",
            text=args.get("text") or "",
            url=args.get("url") or "",
            flair_id=args.get("flair_id") or "",
            nsfw=bool(args.get("nsfw")),
            spoiler=bool(args.get("spoiler")),
        )
        errors = [
            err
            for err in (
                (payload.get("json") or {}).get("errors") or []
                if isinstance(payload, dict)
                else []
            )
        ]
        if errors:
            return json.dumps({"ok": False, "errors": errors, "raw": payload}, default=str)
        data = ((payload.get("json") or {}).get("data") or {}) if isinstance(payload, dict) else {}
        return _ok(
            {
                "submitted": True,
                "id": data.get("id"),
                "fullname": data.get("name"),
                "url": data.get("url"),
                "subreddit": data.get("subreddit"),
                "raw": payload if not data else None,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_comment(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        payload = session.comment(args["parent"], args["text"])
        errors = (
            (payload.get("json") or {}).get("errors") or []
            if isinstance(payload, dict)
            else []
        )
        if errors:
            return json.dumps({"ok": False, "errors": errors, "raw": payload}, default=str)
        things = ((payload.get("json") or {}).get("data") or {}).get("things") or []
        created = things[0].get("data", {}) if things else {}
        return _ok(
            {
                "commented": True,
                "id": created.get("id"),
                "fullname": created.get("name"),
                "permalink": created.get("permalink"),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_vote(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        payload = session.vote(args["thing"], int(args["direction"]))
        return _ok({"voted": args["thing"], "direction": int(args["direction"]), "raw": payload or None})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_manage(args: dict, **kwargs) -> str:
    try:
        action = (args["action"] or "").strip().lower()
        target = args["target"].strip()
        session = client.session()
        if action in ("save", "unsave"):
            return _ok({"action": action, "raw": session.save(target, action == "save")})
        if action in ("subscribe", "unsubscribe"):
            return _ok(
                {"action": action, "raw": session.subscribe(target, action == "subscribe")}
            )
        if action in ("hide", "unhide"):
            payload = session.request(
                "POST",
                "/api/hide" if action == "hide" else "/api/unhide",
                data={"id": target},
            )
            return _ok({"action": action, "raw": payload})
        return json.dumps({"ok": False, "error": f"unknown action {action!r}"})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


def reddit_inbox(args: dict, **kwargs) -> str:
    try:
        session = client.session()
        return _ok(
            session.inbox(
                where=args.get("where") or "unread",
                limit=int(args.get("limit") or 25),
                mark=bool(args.get("mark")),
            )
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
