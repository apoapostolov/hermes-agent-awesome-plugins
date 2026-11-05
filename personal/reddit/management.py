"""Dedicated Reddit workflows with validated paths and explicit writes."""
import json
import re
from . import client


def name(value, label="name"):
    value = (value or "").strip().removeprefix("r/").removeprefix("u/")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", value):
        raise client.RedditError(f"Invalid {label}")
    return value


def paging(args):
    return {"limit": max(1, min(int(args.get("limit") or 25), 100)), "after": args.get("after") or ""}


def moderation(session, args):
    session.require_account()
    action = args.get("action") or "queue"
    if action in {"queue", "log"}:
        sr, where = name(args.get("subreddit"), "subreddit"), args.get("where") or "modqueue"
        if where not in {"modqueue", "reports", "spam", "unmoderated", "edited"}:
            raise client.RedditError("Unknown moderator queue")
        path = f"/r/{sr}/about/" + ("log" if action == "log" else where)
        payload = session.request("GET", path, params=paging(args))
        return payload if action == "log" else client.compact_listing(payload, body_chars=2000)
    target = client.normalize_fullname(args.get("target") or "")
    routes = {"approve": "approve", "remove": "remove", "lock": "lock", "unlock": "unlock", "distinguish": "distinguish", "undistinguish": "distinguish", "sticky": "set_subreddit_sticky", "unsticky": "set_subreddit_sticky"}
    if action not in routes:
        raise client.RedditError("Unknown moderation action")
    data = {"id": target}
    if action == "remove":
        data["spam"] = str(bool(args.get("spam"))).lower()
    if action in {"distinguish", "undistinguish"}:
        data["how"] = "yes" if action == "distinguish" else "no"
    if action in {"sticky", "unsticky"}:
        if not target.startswith("t3_"):
            raise client.RedditError("Only posts can be stickied")
        data["state"] = str(action == "sticky").lower()
    return session.request("POST", "/api/" + routes[action], data=data)


def messages(session, args):
    session.require_account()
    action = args.get("action") or "list"
    if action == "list":
        where = args.get("where") or "unread"
        if where not in {"inbox", "unread", "sent", "mentions", "comments", "selfreply", "messages"}:
            raise client.RedditError("Unknown message listing")
        return client.compact_listing(session.request("GET", f"/message/{where}", params=dict(paging(args), mark="false")), body_chars=2000)
    routes = {"read": "read_message", "unread": "unread_message", "read_all": "read_all_messages", "delete": "del_msg"}
    if action not in routes:
        raise client.RedditError("Unknown message action")
    targets = args.get("targets") or []
    if action != "read_all" and (not targets or len(targets) > 100 or any(not re.fullmatch(r"t[14]_[a-z0-9]+", target) for target in targets)):
        raise client.RedditError("Supply 1-100 message/comment reply fullnames")
    if action == "delete" and (len(targets) != 1 or not targets[0].startswith("t4_")):
        raise client.RedditError("Message deletion requires one t4_ message fullname")
    return session.request("POST", "/api/" + routes[action], data={"id": ",".join(targets)} if targets else {})


def wiki(session, args):
    sr = name(args.get("subreddit"), "subreddit")
    action, page = args.get("action") or "read", args.get("page") or "index"
    if not re.fullmatch(r"[A-Za-z0-9_/-]+", page) or "//" in page or page.startswith("/"):
        raise client.RedditError("Invalid wiki page path")
    base = f"/r/{sr}"
    if action == "pages":
        return session.request("GET", base + "/wiki/pages")
    if action == "revisions":
        return session.request("GET", base + "/wiki/revisions/" + page, params=paging(args))
    if action == "read":
        return session.request("GET", base + "/wiki/page/" + page, params={"v": args["revision"]} if args.get("revision") else None)
    if action not in {"edit", "revert"}:
        raise client.RedditError("Unknown wiki action")
    session.require_account()
    if action == "revert":
        if not args.get("revision"):
            raise client.RedditError("A revision ID is required")
        return session.request("POST", base + "/api/wiki/revert", data={"page": page, "revision": args["revision"]})
    if "content" not in args:
        raise client.RedditError("Replacement wiki content is required")
    return session.request("POST", base + "/api/wiki/edit", data={"page": page, "content": args["content"], "reason": args.get("reason") or ""})


def multis(session, args):
    action = args.get("action") or "list"
    owner = name(args.get("owner") or session.require_account(), "owner")
    if action == "list":
        return session.request("GET", f"/api/multi/user/{owner}" if args.get("owner") else "/api/multi/mine")
    multi = name(args.get("name"), "custom feed name")
    path = f"/api/multi/user/{owner}/m/{multi}"
    if action == "read":
        return session.request("GET", path)
    if owner.casefold() != session.require_account().casefold():
        raise client.RedditError("Custom-feed writes must target the authorized account")
    if action in {"add", "remove"}:
        sr = name(args.get("subreddit"), "subreddit")
        return session.request("PUT" if action == "add" else "DELETE", path + "/r/" + sr, data={"model": json.dumps({"name": sr})} if action == "add" else None)
    if action == "delete":
        return session.request("DELETE", path)
    if action not in {"create", "update"}:
        raise client.RedditError("Unknown custom-feed action")
    model = {}
    if "description" in args:
        model["description_md"] = str(args["description"])
    if "visibility" in args:
        if args["visibility"] not in {"private", "public", "hidden"}:
            raise client.RedditError("Invalid custom-feed visibility")
        model["visibility"] = args["visibility"]
    if "subreddits" in args:
        values = args["subreddits"]
        if not isinstance(values, list) or len(values) > 100:
            raise client.RedditError("Supply at most 100 subreddit names")
        model["subreddits"] = [{"name": name(sr, "subreddit")} for sr in values]
    return session.request("POST" if action == "create" else "PUT", path, data={"model": json.dumps(model)})
