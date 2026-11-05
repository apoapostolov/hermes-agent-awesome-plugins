"""Reddit API client: OAuth token store, refresh, and request helpers.

Zero third-party dependencies. Stdlib only so the plugin runs in any Hermes
profile without extra installs.
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import re
import threading
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from contextlib import contextmanager
from . import coordination, secrets_store

OAUTH_HOST = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
AUTHORIZE_URL = "https://www.reddit.com/api/v1/authorize"
DEFAULT_REDIRECT_URI = "http://localhost:8080"
DEFAULT_USER_AGENT = "desktop:hermes-reddit:v1.1.0"

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


def token_path(home=None) -> pathlib.Path:
    override = os.environ.get("REDDIT_TOKEN_FILE") if home is None else None
    if override:
        return pathlib.Path(override)
    return pathlib.Path(home or hermes_home()) / "reddit-oauth.json"


def config_path(home=None) -> pathlib.Path:
    override = os.environ.get("REDDIT_CONFIG_FILE") if home is None else None
    if override:
        return pathlib.Path(override)
    return pathlib.Path(home or hermes_home()) / "reddit-config.json"


def _decode_credentials(data, home=None) -> dict:
    """Decode a credential file, treating an unreadable one as absent.

    A protected file carried to another Windows user or machine cannot be
    decrypted, and raising from here blocked recovery: setup could not store
    replacement credentials until the file was moved aside by hand.
    """
    try:
        return secrets_store.decode(data, home)
    except (RuntimeError, ValueError, TypeError):
        pass
    recovered = {}
    for key, value in data.items():
        try:
            recovered.update(secrets_store.decode({key: value}, home))
        except (RuntimeError, ValueError, TypeError):
            continue
    return recovered


def load_config(home=None) -> dict:
    path = config_path(home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return _decode_credentials(data, home)


def save_config(values: dict, home=None) -> pathlib.Path:
    """Merge values into the plugin config file and return its path."""
    path = config_path(home)
    with _WRITE_LOCK, coordination.file_lock(path.with_suffix(".lock")):
        # Merge over the raw file: a field that cannot be decrypted right now
        # must keep its ciphertext instead of vanishing from a partial save.
        try:
            current = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        merged = dict(current) if isinstance(current, dict) else {}
        for key, value in values.items():
            if value is None:
                continue
            merged[key] = value
        merged["updated_at"] = int(time.time())
        _atomic_write(path, json.dumps(secrets_store.encode(merged, home=home), indent=2, sort_keys=True))
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
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    tmp = pathlib.Path(temporary)
    try:
        # Credential fields are authenticated ciphertext before this sink.
        # Other callers write metadata, bookmark IDs or temporary OAuth state.
        # mkstemp creates a mode-600 file before any bytes are written.
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)  # lgtm[py/clear-text-storage-sensitive-data]
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


def load_credentials(home=None) -> dict[str, str]:
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

    config = load_config(home)
    if config.get("client_id"):
        creds.update(
            client_id=str(config.get("client_id", "")).strip(),
            client_secret=str(config.get("client_secret", "")).strip(),
            user_agent=str(config.get("user_agent", "")).strip(),
            redirect_uri=str(config.get("redirect_uri", "")).strip(),
            source="config",
        )

    stored = load_token(home)
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
    # The app token can be granted and the read still fail (a rate limit, a
    # network drop, an HTML error page). Those used to escape as a raw
    # urllib/JSON exception, so the settings page showed a type name instead of
    # what Reddit said.
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise RedditError(
            f"Credentials were accepted, but the read-only check failed "
            f"({exc.code}): {detail}"
        ) from exc
    except OSError as exc:
        raise RedditError(
            f"Credentials were accepted, but the read-only check could not reach "
            f"Reddit: {exc}"
        ) from exc
    try:
        listing = json.loads(body)
    except ValueError as exc:
        raise RedditError(
            f"Credentials were accepted, but Reddit answered with something other "
            f"than JSON: {body[:160]}"
        ) from exc
    children = (listing.get("data") or {}).get("children") or []
    return {
        "app_token": "ok",
        "scopes": payload.get("scope"),
        "sample_title": (children[0]["data"].get("title") if children else None),
    }



def load_token(home=None) -> dict:
    path = token_path(home)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return _decode_credentials(data, home)


def save_token(token: dict, home=None) -> pathlib.Path:
    path = token_path(home)
    auth_lock = pathlib.Path(home or hermes_home()) / "plugin-data/reddit/token-refresh.lock"
    with coordination.file_lock(auth_lock), _WRITE_LOCK, coordination.file_lock(path.with_suffix(".lock")):
        _atomic_write(path, json.dumps(secrets_store.encode(token, home=home), indent=2, sort_keys=True))
    return path


def clear_token() -> bool:
    root = hermes_home() / "plugin-data/reddit"
    with coordination.file_lock(root / "token-refresh.lock"):
        return _clear_token_locked()


def _clear_token_locked() -> bool:
    path = token_path()
    (hermes_home() / "plugin-data/reddit/access-cache.json").unlink(missing_ok=True)
    if path.exists():
        path.unlink()
        return True
    return False


def reset_credentials():
    root = hermes_home() / "plugin-data/reddit"
    with coordination.file_lock(root / "token-refresh.lock"):
        for path in (config_path(), token_path(), root / "access-cache.json", hermes_home() / "reddit-login-pending.json", root / "storage-key.json"):
            path.unlink(missing_ok=True)
    reset_session()
    return {"reset": True, "library_preserved": True}


def protect_credentials(enabled=True, home=None):
    if not enabled:
        raise RedditError("At-rest credential encryption cannot be disabled")
    root = pathlib.Path(home or hermes_home()) / "plugin-data/reddit"
    # One lock across the token read, the rewrite and the cache migration: a
    # logout that lands between them used to be undone by the token write, and a
    # concurrent refresh could rewrite the cache in plaintext after the rewrite.
    with coordination.file_lock(root / "token-refresh.lock"):
        cache = root / "access-cache.json"
        if cache.exists():
            try:
                value = secrets_store.decode(json.loads(cache.read_text(encoding="utf-8")), home)
            except (OSError, ValueError, RuntimeError):
                value = {}
            if value:
                _atomic_write(cache, json.dumps(secrets_store.encode(value, home=home)))
            else:
                cache.unlink(missing_ok=True)
        token = load_token(home)
        if token:
            save_token(token, home)
    save_config({"protect_secrets": True}, home)
    return {"protected": True, "backend": "Fernet with Windows DPAPI key protection" if os.name == "nt" else "Fernet with a private profile key file"}


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


def rate_limit_wait(headers, cap: int = 30) -> int:
    """Use the same rounded deadline as the shared client budget."""
    return coordination.retry_delay(headers)


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


def flatten_comments(
    children: list,
    depth: int = 0,
    body_chars: int = 500,
    out: list | None = None,
    more: list | None = None,
) -> tuple[list, list]:
    """Flatten a comment tree into compact items that keep their reply depth.

    ``more`` nodes are Reddit's "load more comments" placeholders; they are
    collected separately because each one carries the number of hidden
    comments and the ids needed to fetch them from ``/api/morechildren``.
    Without that step a thread read silently stops at whatever the first page
    returned.
    """
    out = [] if out is None else out
    more = [] if more is None else more
    for child in children or []:
        kind = child.get("kind")
        data = child.get("data") or {}
        if kind == "t1":
            item = compact_item(child, body_chars=body_chars)
            item["depth"] = depth
            out.append(item)
            replies = data.get("replies")
            if isinstance(replies, dict):
                flatten_comments(
                    (replies.get("data") or {}).get("children") or [],
                    depth + 1,
                    body_chars,
                    out,
                    more,
                )
        elif kind == "more":
            ids = data.get("children") or []
            more.append(
                {
                    "count": data.get("count") or len(ids),
                    "depth": depth,
                    "parent": data.get("parent_id"),
                    "ids": ids,
                }
            )
    return out, more


class Reddit:
    """Authenticated Reddit API session backed by a stored refresh token."""

    def __init__(self, creds: dict | None = None, token: dict | None = None, home=None):
        self.home = pathlib.Path(home) if home is not None else None
        self.creds = creds or load_credentials(home)
        self.token = token if token is not None else load_token(home)
        self._managed_token = token is None
        self._auth_lock = threading.RLock()
        self._access = ""
        self._expires_at = 0.0
        # App-only tokens are a different grant; keeping them in their own
        # slots stops a read-only call from being reused as the account token.
        self._app_access = ""
        self._app_expires_at = 0.0
        self.last_rate: dict[str, str] = {}
        # Which grant served the last call: "account" or "app" (read-only).
        self.last_backend: str = ""
        self._blocked_until = 0.0

    # ---- auth -------------------------------------------------------
    @property
    def has_refresh_token(self) -> bool:
        return bool(self.token.get("refresh_token"))

    def _needs_refresh(self) -> bool:
        return not self._access or time.time() > self._expires_at - 90

    def refresh(self, force: bool = False) -> str:
        root = pathlib.Path(self.home or hermes_home()) / "plugin-data/reddit"
        with self._auth_lock, coordination.file_lock(root / "token-refresh.lock"):
            if self._managed_token and load_token(self.home).get("refresh_token") != self.token.get("refresh_token"):
                self._access = ""
                self.token = {}
                raise RedditError("Reddit account changed or logged out in another process; sign in again")
            if not force and not self._needs_refresh():
                return self._access
            import hashlib
            key = hashlib.sha256((self.creds.get("client_id", "") + self.creds.get("client_secret", "") + self.token.get("refresh_token", "")).encode()).hexdigest()
            cache = root / "access-cache.json"
            cached = secrets_store.decode(coordination.read_state(cache), self.home) if not force else {}
            if cached.get("key") == key and cached.get("expires_at", 0) > time.time() + 90:
                self._access, self._expires_at = cached["access_token"], cached["expires_at"]
                return self._access
            access = self._refresh_locked(force)
            cached = {"key": key, "access_token": access, "expires_at": self._expires_at}
            _atomic_write(cache, json.dumps(secrets_store.encode(cached, home=self.home)))
            return access

    def _refresh_locked(self, force: bool = False) -> str:
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
            save_token(self.token, self.home)
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

    def _token_for(self, method: str, app_only: bool) -> tuple[str, str]:
        """Pick the token for this call and name the grant it came from.

        A GET falls back to the app-only ``client_credentials`` token when no
        account is linked, so a configured app can read public subreddits,
        searches and threads without a login. Writes still need the account.
        """
        if app_only:
            if method != "GET":
                raise RedditError("app_only is read-only; account authorization is required for writes")
            return self.app_only_token(), "app"
        if self.has_refresh_token:
            return self.refresh(), "account"
        if method == "GET" and self.creds.get("client_id") and self.creds.get("client_secret"):
            return self.app_only_token(), "app"
        if method == "GET":
            raise RedditError(
                "Neither a Reddit login nor an app credential is stored. Run "
                "reddit_setup with the client id and secret from "
                "reddit.com/prefs/apps to read public Reddit, or reddit_login to "
                "act as your account."
            )
        raise RedditError(
            f"{method} needs a Reddit login: run reddit_login. Reading with the "
            "app-only token can see public subreddits but cannot post, vote, save "
            "or touch your account."
        )

    # ---- transport --------------------------------------------------
    @contextmanager
    def _response(self, request):
        client_id = self.creds.get("client_id", "")
        try:
            with coordination.request_slot(client_id) as budget:
                try:
                    with urllib.request.urlopen(request, timeout=45) as response:
                        budget.capture(response.headers)
                        # Record before the caller reads the body, or an exhausted
                        # budget stays invisible to other processes meanwhile.
                        coordination.record_slot(client_id, budget)
                        yield response
                except urllib.error.HTTPError as exc:
                    budget.capture(exc.headers, exc.code)
                    coordination.record_slot(client_id, budget)
                    raise
        except RuntimeError as exc:
            if isinstance(exc, RedditError):
                raise
            raise RedditError(str(exc)) from exc

    def request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        data: dict | None = None,
        app_only: bool = False,
    ) -> dict:
        method = (method or "GET").upper()
        remaining_wait = self._blocked_until - time.time()
        if remaining_wait > 0:
            raise RedditError(f"Reddit rate budget is exhausted; retry after {int(remaining_wait) + 1} seconds")
        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise RedditError("Unsupported HTTP method")
        raw_path = (path or "").strip()
        if "://" in raw_path or raw_path.lower().startswith("http"):
            raise RedditError(
                f"Pass an API path such as /r/hermesagent/new, not a URL ({raw_path[:80]})"
            )
        path = raw_path if raw_path.startswith("/") else "/" + raw_path
        if path.startswith("/api/v1/authorize"):
            raise RedditError("Pass an API path such as /r/hermesagent/new")

        token, backend = self._token_for(method, app_only)
        self.last_backend = backend
        query = dict(params or {})
        body = None
        if method == "GET":
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

        for attempt in range(3):
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
                with self._response(request) as response:
                    self._capture_rate(response.headers)
                    raw = response.read().decode("utf-8", "replace")
                    payload = json.loads(raw) if raw else {}
                    errors = (payload.get("json") or {}).get("errors") if isinstance(payload, dict) else None
                    if errors:
                        raise RedditError("Reddit rejected the operation: " + json.dumps(errors))
                    return payload
            except urllib.error.HTTPError as exc:
                self._capture_rate(exc.headers)
                detail = exc.read().decode("utf-8", "replace")
                if exc.code == 401 and attempt == 0:
                    token = (
                        self.app_only_token(force=True)
                        if backend == "app"
                        else self.refresh(force=True)
                    )
                    continue
                if exc.code == 429 and attempt < 2:
                    wait = rate_limit_wait(exc.headers)
                    self._blocked_until = time.time() + wait
                    if wait > 30:
                        raise RedditError(f"Reddit rate limit: retry after {wait} seconds; no early retry was sent") from None
                    if wait:
                        self.last_rate["waited"] = str(wait)
                        time.sleep(wait)
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
            except (OSError, ValueError) as exc:
                # Retrying a write after a lost response can create duplicate content.
                raise RedditError(f"Reddit response failed: {exc}. Writes were not automatically replayed.") from exc
        raise RedditError("Reddit API request failed after retries")

    def _capture_rate(self, headers) -> None:
        if headers is None:
            return
        for key in ("X-Ratelimit-Used", "X-Ratelimit-Remaining", "X-Ratelimit-Reset"):
            value = headers.get(key)
            if value is not None:
                self.last_rate[key] = value
        try:
            if float(headers.get("X-Ratelimit-Remaining", 1)) <= 0:
                self._blocked_until = time.time() + float(headers.get("X-Ratelimit-Reset", 0)) + 1
        except (TypeError, ValueError):
            pass

    # ---- convenience ------------------------------------------------
    def me(self) -> dict:
        return self.request("GET", "/api/v1/me")

    def identity(self) -> dict:
        if not self.has_refresh_token:
            has_app = bool(
                self.creds.get("client_id") and self.creds.get("client_secret")
            )
            return {
                "logged_in": False,
                "read_only": has_app,
                "backend": "app" if has_app else "none",
                "token_file": str(token_path()),
                "rate": self.last_rate,
            }
        try:
            profile = self.me()
        except RedditError as exc:
            return {"logged_in": False, "error": str(exc)}
        return {
            "logged_in": True,
            "read_only": False,
            "backend": "account",
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
        after: str = "",
    ) -> dict:
        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": max(1, min(int(limit or 25), 100)),
        }
        if kind == "comment":
            raise RedditError("The documented Data API search does not support comment search. Use reddit_library_search for locally saved comments.")
        if kind in ("link", "sr", "user"):
            params["type"] = kind
        if after:
            params["after"] = after
        path = f"/r/{subreddit}/search" if subreddit else "/search"
        if subreddit:
            params["restrict_sr"] = "1"
        payload = self.request("GET", path, params=params)
        return compact_listing(payload, body_chars=body_chars, limit=limit)

    def thread(
        self,
        id_or_url: str,
        sort: str = "best",
        comment_limit: int = 50,
        depth: int = 4,
        expand_more: bool = True,
        body_chars: int = 500,
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
        comments, more = flatten_comments(
            payload[1]["data"]["children"], body_chars=body_chars
        )
        comments = comments[:comment_limit]
        hidden = sum(int(entry["count"] or 0) for entry in more)
        expanded = 0
        if expand_more and more and len(comments) < comment_limit:
            known = {c["name"]: c["depth"] for c in comments if c.get("name")}
            extra, more = self.more_children(
                article, more, comment_limit - len(comments), body_chars, known
            )
            expanded = len(extra)
            comments = (comments + extra)[:comment_limit]
        return {
            "post": post,
            "backend": self.last_backend,
            "count": len(comments),
            "depth_reached": max((c.get("depth") or 0) for c in comments) if comments else 0,
            "hidden_comments": hidden,
            "expanded": expanded,
            "more": [{k: v for k, v in entry.items() if k != "ids"} for entry in more],
            "comments": comments,
        }

    def more_children(
        self,
        article: str,
        more: list,
        budget: int,
        body_chars: int = 500,
        known: dict | None = None,
    ) -> tuple[list, list]:
        """Fetch the comments behind ``more`` placeholders and rebuild their depth.

        One request covers up to 100 ids; anything left over stays in the
        returned ``more`` list so the caller can see what is still hidden.
        """
        wanted = []
        for entry in more:
            for comment_id in entry.get("ids") or []:
                if comment_id not in wanted:
                    wanted.append(comment_id)
        take = wanted[: max(0, min(int(budget or 0), 100))]
        leftover = []
        if not take:
            return [], [dict(entry, ids=[]) for entry in more]
        article = normalize_thread_id(article)
        payload = self.request(
            "GET",
            "/api/morechildren",
            params={
                "api_type": "json",
                "link_id": f"t3_{article}",
                "children": ",".join(take),
                "limit_children": "false",
            },
        )
        things = ((payload.get("json") or {}).get("data") or {}).get("things") or []
        parent_depth = {f"t3_{article}": -1}
        for name, depth in (known or {}).items():
            parent_depth.setdefault(name, depth)
        items: list = []
        for entry in more:
            for comment_id in entry.get("ids") or []:
                if comment_id in take:
                    parent_depth.setdefault(comment_id, 0)
        for thing in things:
            data = thing.get("data") or {}
            kind = thing.get("kind")
            if kind == "more":
                leftover.append(
                    {
                        "count": data.get("count") or 0,
                        "depth": 0,
                        "parent": data.get("parent_id"),
                        "ids": data.get("children") or [],
                    }
                )
                continue
            if kind != "t1":
                continue
            item = compact_item(thing, body_chars=body_chars)
            parent = data.get("parent_id") or ""
            item["depth"] = parent_depth.get(parent, 0) + 1
            parent_depth[item.get("name") or ""] = item["depth"]
            items.append(item)
        remaining = [cid for cid in wanted if cid not in take]
        if remaining:
            leftover.append({"count": len(remaining), "depth": 0, "parent": None, "ids": remaining})
        return items, leftover

    def user(
        self,
        username: str,
        kind: str = "overview",
        limit: int = 25,
        sort: str = "new",
        time_filter: str = "all",
        body_chars: int = 300,
        after: str = "",
    ) -> dict:
        name = (username or "").strip()
        if name.lower().startswith("u/"):
            name = name[2:]
        if not name:
            raise RedditError("username required")
        where = kind if kind in ("overview", "submitted", "comments") else "overview"
        payload = self.request(
            "GET",
            f"/user/{name}/{where}",
            params={
                "limit": max(1, min(int(limit or 25), 100)),
                "sort": sort,
                "t": time_filter,
                **({"after": after} if after else {}),
            },
        )
        listing = compact_listing(payload, body_chars=body_chars, limit=limit)
        listing["username"] = name
        listing["kind"] = where
        listing["backend"] = self.last_backend
        return listing

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
        value = subreddit.strip().removeprefix("r/")
        return self.request(
            "POST",
            "/api/subscribe",
            data={
                ("sr" if value.startswith("t5_") else "sr_name"): value,
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

    def require_account(self) -> str:
        if not self.has_refresh_token:
            raise RedditError("This operation needs reddit_login with an account token")
        name = self.token.get("username") or self.me().get("name")
        if not name:
            raise RedditError("Reddit did not return the account name")
        return str(name)

    def account_listing(self, where="saved", limit=100, after="", raw=False):
        name = self.require_account()
        if where not in {"saved", "hidden", "upvoted", "downvoted", "submitted", "comments", "overview"}:
            raise RedditError("Unknown account listing")
        params = {"limit": max(1, min(int(limit), 100))}
        if after:
            params["after"] = after
        payload = self.request("GET", f"/user/{name}/{where}", params=params)
        return payload if raw else compact_listing(payload, body_chars=2000)

    def info(self, names):
        names = [normalize_fullname(name) for name in names]
        if not names or len(names) > 100:
            raise RedditError("Supply between 1 and 100 post/comment fullnames")
        return self.request("GET", "/api/info", params={"id": ",".join(names)})

    def content_action(self, action, target, text="", reason=""):
        name = normalize_fullname(target)
        self.require_account()
        if action == "edit":
            if not text.strip():
                raise RedditError("Editing requires nonempty Markdown text")
            return self.request("POST", "/api/editusertext", data={"thing_id": name, "text": text})
        if action == "delete":
            return self.request("POST", "/api/del", data={"id": name})
        if action == "report":
            if not reason.strip():
                raise RedditError("Reporting requires a reason")
            return self.request("POST", "/api/report", data={"thing_id": name, "reason": reason})
        routes = {"nsfw": "marknsfw", "un-nsfw": "unmarknsfw", "spoiler": "spoiler", "unspoiler": "unspoiler"}
        if action not in routes:
            raise RedditError("Unknown content action")
        if not name.startswith("t3_"):
            raise RedditError("This action requires a post")
        return self.request("POST", "/api/" + routes[action], data={"id": name})


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


def normalize_fullname(value: str) -> str:
    """Resolve fullnames and canonical Reddit URLs without guessing comment IDs."""
    raw = (value or "").strip()
    if re.fullmatch(r"t[13]_[a-z0-9]+", raw):
        return raw
    parsed = urllib.parse.urlparse(raw)
    if parsed.scheme in {"http", "https"} and parsed.hostname in {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "redd.it"}:
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.hostname == "redd.it" and len(parts) == 1:
            result = "t3_" + parts[0]
        elif "comments" in parts:
            index = parts.index("comments")
            if len(parts) <= index + 1:
                raise RedditError("Invalid Reddit URL")
            result = ("t1_" + parts[index + 3]) if len(parts) > index + 3 else ("t3_" + parts[index + 1])
        else:
            raise RedditError("Use a canonical post/comment URL, not a share link")
        if re.fullmatch(r"t[13]_[a-z0-9]+", result):
            return result
    raise RedditError("Supply a t3_ post fullname, t1_ comment fullname, or canonical Reddit URL")
