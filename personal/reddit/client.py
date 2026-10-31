"""Reddit API client: OAuth token store, refresh, and request helpers.

Zero third-party dependencies. Stdlib only so the plugin runs in any Hermes
profile without extra installs.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OAUTH_HOST = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
DEFAULT_REDIRECT_URI = "http://localhost:8080"
DEFAULT_USER_AGENT = "hermes-reddit-plugin/0.3 (by /u/hermes-reddit)"

ALL_SCOPES = " ".join(
    [
        "account",
        "announcements",
        "creddits",
        "edit",
        "flair",
        "history",
        "identity",
        "livemanage",
        "modconfig",
        "modcontributors",
        "modflair",
        "modlog",
        "modmail",
        "modnote",
        "modothers",
        "modposts",
        "modself",
        "modtraffic",
        "modwiki",
        "mysubreddits",
        "privatemessages",
        "read",
        "report",
        "save",
        "structuredstyles",
        "submit",
        "subscribe",
        "vote",
        "wikiedit",
        "wikiread",
    ]
)


class RedditError(RuntimeError):
    """Raised for configuration and transport problems the agent should see."""


def hermes_home() -> pathlib.Path:
    raw = os.environ.get("HERMES_HOME") or os.path.join(
        os.path.expanduser("~"), ".hermes"
    )
    return pathlib.Path(raw)


def token_path() -> pathlib.Path:
    override = os.environ.get("REDDIT_TOKEN_FILE")
    if override:
        return pathlib.Path(override)
    return hermes_home() / "reddit-oauth.json"


def config_path() -> pathlib.Path:
    override = os.environ.get("REDDIT_CONFIG_FILE")
    if override:
        return pathlib.Path(override)
    return hermes_home() / "reddit-config.json"


def load_config() -> dict:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_config(values: dict) -> pathlib.Path:
    """Merge values into the plugin config file and return its path."""
    path = config_path()
    with _WRITE_LOCK:
        merged = load_config()
        for key, value in values.items():
            if value is None:
                continue
            merged[key] = value
        merged["updated_at"] = int(time.time())
        _atomic_write(path, json.dumps(merged, indent=2, sort_keys=True))
    return path


SETUP_HINT = (
    "No Reddit app configured. Create one at https://www.reddit.com/prefs/apps "
    "(web app, redirect uri http://localhost:8080), then run "
    "`hermes reddit setup` or call the reddit_setup tool with your client id "
    f"and secret. They are stored in {config_path()}."
)

_WRITE_LOCK = threading.RLock()


def _atomic_write(path: pathlib.Path, text: str) -> None:
    """Write one file atomically, with a per-writer temp name.

    Two tool calls can run at once in one gateway process, and a shared
    ``<name>.tmp`` made the second writer fail on ``os.replace`` (WinError 32)
    or hand the reader a half-written token file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        last: OSError | None = None
        for attempt in range(4):
            try:
                os.replace(tmp, path)
                last = None
                break
            except OSError as exc:  # a reader holding the file open on Windows
                last = exc
                time.sleep(0.05 * (attempt + 1))
        if last is not None:
            raise last
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    try:  # best effort on POSIX; Windows inherits the user-profile ACL
        os.chmod(path, 0o600)
    except OSError:
        pass


def load_credentials() -> dict[str, str]:
    """Resolve client id, secret, user agent and redirect URI.

    The plugin's own config file (written by ``hermes reddit setup`` or the
    Desktop settings page) is the only source; a token file saved by an earlier
    login can supply a redirect URI that already worked. Environment variables
    and ``.env`` files are never read: Hermes may run several profiles in one
    process, so an environment read can pick up another profile's values.
    """
    creds = {
        "client_id": "",
        "client_secret": "",
        "user_agent": "",
        "redirect_uri": "",
        "source": "",
    }

    config = load_config()
    if config.get("client_id"):
        creds.update(
            client_id=str(config.get("client_id", "")).strip(),
            client_secret=str(config.get("client_secret", "")).strip(),
            user_agent=str(config.get("user_agent", "")).strip(),
            redirect_uri=str(config.get("redirect_uri", "")).strip(),
            source="config",
        )

    stored = load_token()
    if not creds["client_id"] and stored.get("client_id"):
        creds["client_id"] = stored["client_id"]
        creds["client_secret"] = stored.get("client_secret", "")
        creds["source"] = "token"
    if not creds["redirect_uri"] and stored.get("redirect_uri"):
        creds["redirect_uri"] = stored["redirect_uri"]

    creds["user_agent"] = creds["user_agent"] or DEFAULT_USER_AGENT
    creds["redirect_uri"] = creds["redirect_uri"] or DEFAULT_REDIRECT_URI
    return creds


def validate_app(client_id: str, client_secret: str, user_agent: str) -> dict:
    """Check a client id/secret pair by minting an app token and reading a listing."""
    status, payload = _post_form(
        TOKEN_URL,
        {"grant_type": "client_credentials"},
        {
            "Authorization": basic_auth(client_id, client_secret),
            "User-Agent": user_agent,
        },
    )
    if status != 200 or "access_token" not in payload:
        raise RedditError(
            f"Reddit rejected those app credentials ({status}): {payload}"
        )
    request = urllib.request.Request(
        f"{OAUTH_HOST}/r/redditdev/new?limit=1&raw_json=1",
        headers={
            "Authorization": "bearer " + payload["access_token"],
            "User-Agent": user_agent,
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        listing = json.loads(response.read().decode("utf-8", "replace"))
    children = (listing.get("data") or {}).get("children") or []
    return {
        "app_token": "ok",
        "scopes": payload.get("scope"),
        "sample_title": (children[0]["data"].get("title") if children else None),
    }



def load_token() -> dict:
    path = token_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_token(token: dict) -> pathlib.Path:
    path = token_path()
    with _WRITE_LOCK:
        _atomic_write(path, json.dumps(token, indent=2, sort_keys=True))
    return path


def clear_token() -> bool:
    path = token_path()
    if path.exists():
        path.unlink()
        return True
    return False


def basic_auth(client_id: str, client_secret: str) -> str:
    raw = f"{client_id}:{client_secret}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def _post_form(url: str, data: dict, headers: dict, timeout: float = 30.0):
    body = urllib.parse.urlencode(data).encode()
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        try:
            parsed = json.loads(detail)
        except ValueError:
            parsed = {"error": exc.reason, "detail": detail}
        return exc.code, parsed


def exchange_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    user_agent: str,
) -> dict:
    status, payload = _post_form(
        TOKEN_URL,
        {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        {
            "Authorization": basic_auth(client_id, client_secret),
            "User-Agent": user_agent,
        },
    )
    if status != 200 or "access_token" not in payload:
        raise RedditError(f"code exchange failed ({status}): {payload}")
    return payload


def build_authorize_url(
    client_id: str,
    redirect_uri: str,
    state: str,
    scope: str = ALL_SCOPES,
    duration: str = "permanent",
) -> str:
    query = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "state": state,
            "redirect_uri": redirect_uri,
            "duration": duration,
            "scope": scope,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def iso(epoch) -> str:
    try:
        return datetime.fromtimestamp(float(epoch), tz=timezone.utc).isoformat(
            timespec="seconds"
        )
    except (TypeError, ValueError, OSError):
        return ""


def _clip(text: str, size: int) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n")
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


def compact_item(item: dict, body_chars: int = 400) -> dict:
    """Flatten one Reddit listing child into a compact dict."""
    kind = item.get("kind")
    data = item.get("data") or {}
    base = {
        "kind": kind,
        "id": data.get("id"),
        "name": data.get("name"),
        "author": data.get("author"),
        "created": iso(data.get("created_utc")),
        "permalink": (
            "https://www.reddit.com" + data["permalink"]
            if data.get("permalink")
            else None
        ),
    }
    if kind == "t3":
        base.update(
            {
                "subreddit": data.get("subreddit"),
                "title": data.get("title"),
                "score": data.get("score"),
                "upvote_ratio": data.get("upvote_ratio"),
                "comments": data.get("num_comments"),
                "link": data.get("url"),
                "is_self": data.get("is_self"),
                "flair": data.get("link_flair_text"),
                "over_18": data.get("over_18"),
                "selftext": _clip(data.get("selftext") or "", body_chars),
            }
        )
    elif kind == "t1":
        base.update(
            {
                "subreddit": data.get("subreddit"),
                "score": data.get("score"),
                "parent": data.get("parent_id"),
                "stickied": data.get("stickied"),
                "body": _clip(data.get("body") or "", body_chars),
            }
        )
    elif kind == "t5":
        base.update(
            {
                "subreddit": data.get("display_name"),
                "title": data.get("title"),
                "subscribers": data.get("subscribers"),
                "description": _clip(data.get("public_description") or "", body_chars),
            }
        )
    elif kind == "t4" or kind == "t6":
        base.update(
            {
                "subject": data.get("subject"),
                "dest": data.get("dest"),
                "is_new": data.get("new"),
                "body": _clip(data.get("body") or "", body_chars),
            }
        )
    else:
        base.update({k: data.get(k) for k in ("body", "title", "subject") if data.get(k)})
    return {k: v for k, v in base.items() if v is not None}


def compact_listing(payload: dict, body_chars: int = 400, limit: int = 0) -> dict:
    data = payload.get("data", payload) if isinstance(payload, dict) else {}
    children = data.get("children") or []
    items = [compact_item(child, body_chars) for child in children]
    if limit and limit > 0:
        items = items[:limit]
    return {
        "count": len(items),
        "after": data.get("after"),
        "before": data.get("before"),
        "items": items,
    }


class Reddit:
    """Authenticated Reddit API session backed by a stored refresh token."""

    def __init__(self, creds: dict | None = None, token: dict | None = None):
        self.creds = creds or load_credentials()
        self.token = token if token is not None else load_token()
        self._access = ""
        self._expires_at = 0.0
        # App-only tokens are a different grant; keeping them in their own
        # slots stops a read-only call from being reused as the account token.
        self._app_access = ""
        self._app_expires_at = 0.0
        self.last_rate: dict[str, str] = {}

    # ---- auth -------------------------------------------------------
    @property
    def has_refresh_token(self) -> bool:
        return bool(self.token.get("refresh_token"))

    def _needs_refresh(self) -> bool:
        return not self._access or time.time() > self._expires_at - 90

    def refresh(self, force: bool = False) -> str:
        if not self.has_refresh_token:
            raise RedditError(
                "Not logged in: no Reddit refresh token. Run reddit_login first."
            )
        if not force and not self._needs_refresh():
            return self._access
        status, payload = _post_form(
            TOKEN_URL,
            {
                "grant_type": "refresh_token",
                "refresh_token": self.token["refresh_token"],
            },
            {
                "Authorization": basic_auth(
                    self.creds["client_id"], self.creds["client_secret"]
                ),
                "User-Agent": self.creds["user_agent"],
            },
        )
        if status != 200 or "access_token" not in payload:
            raise RedditError(f"token refresh failed ({status}): {payload}")
        self._access = payload["access_token"]
        self._expires_at = time.time() + float(payload.get("expires_in", 3600))
        self.token["access_obtained_at"] = int(time.time())
        # Only touch the token file when the grant itself changed: rewriting it
        # on every refresh meant one disk write per tool call, and that write is
        # what collided when two calls ran at once.
        scope = payload.get("scope")
        if scope and scope != self.token.get("scope"):
            self.token["scope"] = scope
            save_token(self.token)
        return self._access

    def app_only_token(self, force: bool = False) -> str:
        """Read-only application token, used for public smoke checks."""
        if not force and self._app_access and time.time() < self._app_expires_at - 90:
            return self._app_access
        status, payload = _post_form(
            TOKEN_URL,
            {"grant_type": "client_credentials"},
            {
                "Authorization": basic_auth(
                    self.creds["client_id"], self.creds["client_secret"]
                ),
                "User-Agent": self.creds["user_agent"],
            },
        )
        if status != 200 or "access_token" not in payload:
            raise RedditError(f"app token failed ({status}): {payload}")
        self._app_access = payload["access_token"]
        self._app_expires_at = time.time() + float(payload.get("expires_in", 3600))
        return self._app_access

    # ---- transport --------------------------------------------------
    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        data: dict | None = None,
        app_only: bool = False,
    ) -> dict:
        method = (method or "GET").upper()
        raw_path = (path or "").strip()
        if "://" in raw_path or raw_path.lower().startswith("http"):
            raise RedditError(
                f"Pass an API path such as /r/hermesagent/new, not a URL ({raw_path[:80]})"
            )
        path = raw_path if raw_path.startswith("/") else "/" + raw_path
        if path.startswith("/api/v1/authorize"):
            raise RedditError("Pass an API path such as /r/hermesagent/new")

        token = self.app_only_token() if app_only else self.refresh()
        query = dict(params or {})
        body = None
        if method in ("GET", "DELETE"):
            query.setdefault("raw_json", "1")
        else:
            body = dict(data or {})
            body.setdefault("api_type", "json")
            query.setdefault("raw_json", "1")

        url = OAUTH_HOST + path
        if query:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
                query, doseq=True
            )

        for attempt in (0, 1):
            headers = {
                "Authorization": f"bearer {token}",
                "User-Agent": self.creds["user_agent"],
                "Accept": "application/json",
            }
            payload_bytes = None
            if body is not None:
                payload_bytes = urllib.parse.urlencode(body, doseq=True).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            request = urllib.request.Request(
                url, data=payload_bytes, headers=headers, method=method
            )
            try:
                with urllib.request.urlopen(request, timeout=45) as response:
                    self._capture_rate(response.headers)
                    raw = response.read().decode("utf-8", "replace")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                self._capture_rate(exc.headers)
                detail = exc.read().decode("utf-8", "replace")
                if exc.code == 401 and attempt == 0:
                    token = (
                        self.app_only_token(force=True)
                        if app_only
                        else self.refresh(force=True)
                    )
                    continue
                if exc.code == 403:
                    raise RedditError(
                        "403 from Reddit: token lacks the scope for this call, or "
                        "the account is restricted. Check reddit_status scopes. "
                        f"Detail: {detail[:300]}"
                    )
                try:
                    raise RedditError(
                        f"Reddit API {method} {path} -> {exc.code}: "
                        f"{json.dumps(json.loads(detail))[:500]}"
                    )
                except ValueError:
                    raise RedditError(
                        f"Reddit API {method} {path} -> {exc.code}: {detail[:500]}"
                    ) from None
        raise RedditError("Reddit API request failed after refresh retry")

    def _capture_rate(self, headers) -> None:
        if headers is None:
            return
        for key in ("X-Ratelimit-Used", "X-Ratelimit-Remaining", "X-Ratelimit-Reset"):
            value = headers.get(key)
            if value is not None:
                self.last_rate[key] = value

    # ---- convenience ------------------------------------------------
    def me(self) -> dict:
        return self.request("GET", "/api/v1/me")

    def identity(self) -> dict:
        if not self.has_refresh_token:
            return {"logged_in": False, "token_file": str(token_path())}
        try:
            profile = self.me()
        except RedditError as exc:
            return {"logged_in": False, "error": str(exc)}
        return {
            "logged_in": True,
            "username": profile.get("name"),
            "id": profile.get("id"),
            "link_karma": profile.get("link_karma"),
            "comment_karma": profile.get("comment_karma"),
            "created": iso(profile.get("created_utc")),
            "over_18": profile.get("over_18"),
            "is_mod": profile.get("is_mod"),
            "is_gold": profile.get("is_gold"),
            "scopes": self.token.get("scope"),
            "token_file": str(token_path()),
            "rate": self.last_rate,
        }

    def subreddit(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 25,
        time_filter: str = "",
        after: str = "",
        body_chars: int = 300,
    ) -> dict:
        listing = sort.lower()
        params = {"limit": max(1, min(int(limit or 25), 100))}
        if listing in ("top", "controversial"):
            params["t"] = time_filter or "day"
        if after:
            params["after"] = after
        payload = self.request("GET", f"/r/{subreddit}/{listing}", params=params)
        return compact_listing(payload, body_chars=body_chars, limit=limit)

    def search(
        self,
        query: str,
        subreddit: str = "",
        sort: str = "relevance",
        time_filter: str = "all",
        limit: int = 25,
        kind: str = "",
        body_chars: int = 300,
    ) -> dict:
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": max(1, min(int(limit or 25), 100)),
        }
        if kind in ("link", "comment", "sr"):
            params["type"] = kind
        path = f"/r/{subreddit}/search" if subreddit else "/search"
        if subreddit:
            params["restrict_sr"] = "1"
        payload = self.request("GET", path, params=params)
        return compact_listing(payload, body_chars=body_chars, limit=limit)

    def thread(
        self, id_or_url: str, sort: str = "best", comment_limit: int = 50, depth: int = 4
    ) -> dict:
        article = normalize_thread_id(id_or_url)
        payload = self.request(
            "GET",
            f"/comments/{article}",
            params={
                "sort": sort,
                "limit": max(1, min(int(comment_limit or 50), 100)),
                "depth": depth,
                "threaded": "true",
            },
        )
        if not isinstance(payload, list) or len(payload) < 2:
            return {"error": "unexpected thread payload", "payload": payload}
        post = compact_item(payload[0]["data"]["children"][0], body_chars=4000)
        comments = compact_listing(payload[1], body_chars=500, limit=comment_limit)
        return {"post": post, "comments": comments}

    def submit(
        self,
        subreddit: str,
        title: str,
        kind: str = "self",
        text: str = "",
        url: str = "",
        flair_id: str = "",
        nsfw: bool = False,
        spoiler: bool = False,
        send_replies: bool = True,
    ) -> dict:
        data = {
            "sr": subreddit,
            "title": title,
            "kind": "link" if kind == "link" else "self",
            "sendreplies": str(bool(send_replies)).lower(),
            "nsfw": str(bool(nsfw)).lower(),
            "spoiler": str(bool(spoiler)).lower(),
        }
        if data["kind"] == "link":
            data["url"] = url
        else:
            data["text"] = text
        if flair_id:
            data["flair_id"] = flair_id
        return self.request("POST", "/api/submit", data=data)

    def comment(self, parent: str, text: str) -> dict:
        return self.request(
            "POST", "/api/comment", data={"thing_id": parent, "text": text}
        )

    def vote(self, thing: str, direction: int) -> dict:
        value = 1 if int(direction) > 0 else (-1 if int(direction) < 0 else 0)
        return self.request("POST", "/api/vote", data={"id": thing, "dir": value})

    def save(self, thing: str, save: bool = True) -> dict:
        return self.request(
            "POST", "/api/save" if save else "/api/unsave", data={"id": thing}
        )

    def subscribe(self, subreddit: str, subscribe: bool = True) -> dict:
        return self.request(
            "POST",
            "/api/subscribe",
            data={
                "sr": subreddit if subreddit.startswith("t5_") else subreddit,
                "action": "sub" if subscribe else "unsub",
            },
        )

    def inbox(self, where: str = "unread", limit: int = 25, mark: bool = False) -> dict:
        payload = self.request(
            "GET",
            f"/message/{where}",
            params={"limit": max(1, min(int(limit or 25), 100)), "mark": str(mark).lower()},
        )
        return compact_listing(payload, body_chars=500, limit=limit)


_SESSION_LOCK = threading.RLock()
_SESSION: "Reddit | None" = None
_SESSION_KEY: tuple = ()


def _state_key() -> tuple:
    """Fingerprint of the two stored files, so a save or logout rebuilds the session."""
    parts = []
    for path in (config_path(), token_path()):
        try:
            stat = path.stat()
            parts.append((str(path), stat.st_mtime_ns, stat.st_size))
        except OSError:
            parts.append((str(path), 0, 0))
    return tuple(parts)


def session() -> "Reddit":
    """The process-wide authenticated session.

    Tool handlers used to build a ``Reddit()`` per call, so every call paid a
    token refresh plus a token-file write. One cached session keeps the access
    token alive across calls and rebuilds itself when the config or token file
    changes (login, logout, credential save, another process's refresh).
    """
    global _SESSION, _SESSION_KEY
    key = _state_key()
    with _SESSION_LOCK:
        if _SESSION is None or key != _SESSION_KEY:
            _SESSION = Reddit()
            _SESSION_KEY = key
        return _SESSION


def reset_session() -> None:
    global _SESSION, _SESSION_KEY
    with _SESSION_LOCK:
        _SESSION = None
        _SESSION_KEY = ()


def normalize_thread_id(value: str) -> str:
    """Accept a bare 36-char id, a t3_ fullname, or a reddit URL."""
    raw = (value or "").strip()
    if not raw:
        raise RedditError("thread id or URL required")
    if raw.startswith("t3_"):
        raw = raw[3:]
    if "/" in raw:
        parts = [p for p in raw.split("?")[0].split("/") if p]
        for marker in ("comments", "s"):
            if marker in parts:
                index = parts.index(marker)
                if index + 1 < len(parts):
                    return parts[index + 1]
        raw = parts[-1]
    return raw.split("#")[0]
