"""Interactive Reddit OAuth login: published-app code flow with a loopback catcher.

The authorization code is delivered to ``http://localhost:8080`` (the redirect
URI registered on the Reddit app). A short-lived local HTTP server catches it,
then it is exchanged for a permanent refresh token.
"""

from __future__ import annotations

import http.server
import html
import json
import secrets
import threading
import time
import urllib.parse

from . import client, coordination

PENDING: dict = {
    "state": "",
    "redirect_uri": "",
    "scope": "",
    "port": 0,
    "started_at": 0.0,
    "result": None,
    "error": "",
    "home": "",
}
_LOCK = threading.Lock()
_FLOW_LOCK = threading.RLock()
_SERVER: http.server.HTTPServer | None = None
_THREAD: threading.Thread | None = None

CALLBACK_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Reddit login</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:4rem auto;max-width:34rem;
padding:0 1.5rem;color:#1b1b1b}}code{{background:#f2f2f2;padding:.1rem .3rem;
border-radius:3px}}</style></head>
<body><h1>Reddit login {status}</h1><p>{message}</p>
<p>You can close this tab and return to Hermes.</p></body></html>
"""


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - stdlib naming
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        error = (query.get("error") or [""])[0]

        with _LOCK:
            expected = PENDING["state"]
            if error:
                PENDING["error"] = error
                status, message = "failed", f"Reddit returned <code>{html.escape(error)}</code>."
            elif not code:
                PENDING["error"] = "no code in callback"
                status, message = "failed", "No authorization code in the callback."
            elif expected and state != expected:
                PENDING["error"] = "state mismatch"
                status, message = "failed", "State check failed; the callback was ignored."
            elif PENDING["result"]:
                status, message = "already complete", "This login was already completed."
            else:
                PENDING["result"] = {"code": code, "state": state}
                status, message = "received", "Authorization code captured."

        body = CALLBACK_PAGE.format(status=status, message=message).encode()
        self.send_response(200 if status != "failed" else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):  # silence the default stderr logging
        return


def _shutdown() -> None:
    global _SERVER, _THREAD
    with _LOCK:
        server, thread = _SERVER, _THREAD
        _SERVER = _THREAD = None
    if server is not None:
        threading.Thread(target=server.shutdown, daemon=True).start()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)
    if server is not None:
        server.server_close()


def _expire(deadline: float, state: str) -> None:
    while time.time() < deadline:
        time.sleep(1)
        if PENDING["state"] != state or PENDING["result"] or PENDING["error"]:
            return
    with _FLOW_LOCK:
        if PENDING["state"] == state:
            _shutdown()


def start(
    port: int | None = None,
    redirect_uri: str = "",
    scope: str = "",
    host: str = "127.0.0.1",
) -> dict:
    """Begin a login: bind the loopback catcher and return the consent URL."""
    global _SERVER, _THREAD
    creds = client.load_credentials()
    if not creds["client_id"] or not creds["client_secret"]:
        raise client.RedditError(client.SETUP_HINT)

    profile_home = str(client.hermes_home().resolve())
    if _SERVER is not None and PENDING.get("home") and PENDING["home"] != profile_home:
        raise client.RedditError("Another Hermes profile has an active Reddit callback listener; complete it first")
    _shutdown()
    redirect = (redirect_uri or creds["redirect_uri"] or client.DEFAULT_REDIRECT_URI).strip()
    parsed = urllib.parse.urlparse(redirect)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise client.RedditError("The local callback requires an http localhost or 127.0.0.1 redirect URI")
    bind_port = (parsed.port or 8080) if port is None else int(port)

    try:
        server = http.server.HTTPServer((host, bind_port), _Handler)
    except OSError as exc:
        with _LOCK:
            PENDING.update({"result": None, "error": str(exc), "started_at": 0.0})
        raise client.RedditError(
            f"Cannot listen on {host}:{bind_port} for the OAuth callback ({exc}). "
            "Free the port, or run reddit_login with action='complete' and paste "
            "the redirect URL after approving in the browser."
        ) from exc

    state = secrets.token_urlsafe(24)
    bind_port = server.server_address[1]
    PENDING.update(
        {
            "state": state,
            "redirect_uri": redirect,
            "scope": scope or client.ALL_SCOPES,
            "port": bind_port,
            "started_at": time.time(),
            "result": None,
            "error": "",
            "home": profile_home,
        }
    )
    client._atomic_write(client.hermes_home() / "reddit-login-pending.json", json.dumps({
        key: PENDING[key] for key in ("state", "redirect_uri", "scope", "started_at")
    }))

    _SERVER = server
    _THREAD = threading.Thread(target=server.serve_forever, daemon=True)
    _THREAD.start()
    threading.Thread(target=_expire, args=(time.time() + 900, state), daemon=True).start()

    url = client.build_authorize_url(
        creds["client_id"], redirect, state, scope=PENDING["scope"]
    )
    return {
        "status": "awaiting_approval",
        "authorize_url": url,
        "redirect_uri": redirect,
        "listening_on": f"http://{host}:{bind_port}",
        "state": state,
        "expires_in_seconds": 900,
        "next": "Open authorize_url in a browser, approve, then call "
        "reddit_login with action='status' (the catcher records the code "
        "automatically) or action='complete' with the redirect URL.",
    }


def result() -> dict:
    """Current login state, exchanging the captured code when present."""
    creds = client.load_credentials()
    with _LOCK:
        owned = not PENDING.get("home") or PENDING["home"] == str(client.hermes_home().resolve())
        captured = dict(PENDING["result"]) if owned and PENDING["result"] else None
        error = PENDING["error"] if owned else ""
        redirect = (PENDING["redirect_uri"] if owned else "") or creds["redirect_uri"]
        listening = bool(owned and _SERVER is not None)
        started_at = PENDING["started_at"] if owned else 0

    if captured and not error:
        try:
            return finish(
                code=captured["code"],
                redirect_uri=redirect,
                state=captured.get("state", ""),
            )
        except (client.RedditError, OSError) as exc:
            # Report it once and drop the dead code: leaving it in place made
            # every later poll re-exchange an already-used code and raise, which
            # the settings page swallowed into a permanent "waiting" state.
            message = str(exc) or exc.__class__.__name__
            with _LOCK:
                PENDING.update({"result": None, "error": message})
            _shutdown()
            return {"status": "failed", "error": message, "listening": False}

    if error:
        return {"status": "failed", "error": error, "listening": listening}

    stored = client.load_token()
    return {
        "status": "awaiting_approval" if listening else "idle",
        "listening": listening,
        "waiting_seconds": round(time.time() - started_at, 1) if started_at else None,
        "logged_in": bool(stored.get("refresh_token")),
        "username": stored.get("username"),
        "redirect_uri": redirect,
        "token_file": str(client.token_path()),
    }


def parse_code(value: str) -> tuple[str, str]:
    """Accept a bare code, a redirect URL, or a full query string."""
    raw = (value or "").strip()
    if not raw:
        raise client.RedditError("code or redirect URL required")
    if "code=" in raw:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query or raw)
        codes = query.get("code") or []
        if not codes:
            raise client.RedditError("no code parameter in that URL")
        state = (query.get("state") or [""])[0]
        return codes[0], state
    return raw, ""


def finish(code: str, redirect_uri: str = "", state: str = "") -> dict:
    """Exchange an authorization code and persist the refresh token."""
    creds = client.load_credentials()
    redirect = (redirect_uri or creds["redirect_uri"] or client.DEFAULT_REDIRECT_URI).strip()
    with _LOCK:
        owned = not PENDING.get("home") or PENDING["home"] == str(client.hermes_home().resolve())
        expected = PENDING["state"] if owned else ""
        pending_redirect = PENDING["redirect_uri"] if owned else ""
        started_at = PENDING["started_at"] if owned else 0
    if expected and time.time() - started_at >= 900:
        raise client.RedditError("Login expired. Start reddit_login again")
    if not expected:
        try:
            stored = json.loads((client.hermes_home() / "reddit-login-pending.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            stored = {}
        if time.time() - stored.get("started_at", 0) < 900:
            expected, pending_redirect = stored.get("state", ""), stored.get("redirect_uri", "")
    if not expected:
        raise client.RedditError("No active login. Start reddit_login again and complete within 15 minutes")
    if not state or not secrets.compare_digest(state, expected):
        raise client.RedditError("state mismatch: refusing to exchange that code")
    if pending_redirect and not redirect_uri:
        redirect = pending_redirect

    payload = client.exchange_code(
        creds["client_id"], creds["client_secret"], code, redirect, creds["user_agent"]
    )
    token = {
        "refresh_token": payload.get("refresh_token", ""),
        "scope": payload.get("scope", ""),
        "client_id": creds["client_id"],
        "client_secret": creds["client_secret"],
        "redirect_uri": redirect,
        "user_agent": creds["user_agent"],
        "obtained_at": int(time.time()),
    }
    if not token["refresh_token"]:
        raise client.RedditError(
            "Reddit returned no refresh token. Re-authorize with duration=permanent "
            "(the plugin already requests it); an app-level grant may be missing."
        )

    session = client.Reddit(creds=creds, token=token)
    profile = session.me()
    token["username"] = profile.get("name", "")
    client.save_token(token)
    client.reset_session()
    (client.hermes_home() / "reddit-login-pending.json").unlink(missing_ok=True)

    if owned:
        with _LOCK:
            PENDING.update({"state": "", "result": None, "error": "", "started_at": 0.0, "home": ""})
        _shutdown()

    return {
        "status": "logged_in",
        "username": token["username"],
        "scopes": token["scope"],
        "token_file": str(client.token_path()),
    }


def logout() -> dict:
    owned = not PENDING.get("home") or PENDING["home"] == str(client.hermes_home().resolve())
    if owned:
        _shutdown()
    removed = client.clear_token()
    client.reset_session()
    (client.hermes_home() / "reddit-login-pending.json").unlink(missing_ok=True)
    if owned:
        with _LOCK:
            PENDING.update({"state": "", "result": None, "error": "", "started_at": 0.0, "home": ""})
    return {"status": "logged_out", "token_removed": removed}


def dump_status() -> str:
    return json.dumps(result(), indent=2)


def _serial_flow(handler):
    def call(*args, **kwargs):
        with _FLOW_LOCK, coordination.file_lock(client.hermes_home() / "plugin-data/reddit/oauth-flow.lock", timeout=55):
            return handler(*args, **kwargs)
    return call


start = _serial_flow(start)
result = _serial_flow(result)
finish = _serial_flow(finish)
logout = _serial_flow(logout)
