"""Reddit backend API for the Desktop settings page.

Mounted at ``/api/plugins/reddit/`` and reached from ``desktop/plugin.js`` through
``ctx.rest(...)``. Every route is a thin wrapper over the plugin's own
``client``/``login`` modules, so the CLI, the tools and the settings page share
one token store and one OAuth flow.
"""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# ``<home>/plugins/reddit/dashboard/plugin_api.py`` -> ``<home>/plugins``.
_PLUGINS_ROOT = Path(__file__).resolve().parents[2]


def _mods():
    """Import the plugin package modules (idempotent, path-stable)."""
    root = str(_PLUGINS_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    client = importlib.import_module("reddit.client")
    login = importlib.import_module("reddit.login")
    return client, login


def _reddit_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc) or exc.__class__.__name__)


class ConfigPayload(BaseModel):
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    user_agent: str | None = None
    verify: bool = True
    background_refresh: bool | None = None
    protect_secrets: bool | None = None


class LoginStartPayload(BaseModel):
    port: int | None = None
    redirect_uri: str | None = None
    scope: str | None = None


class LoginCompletePayload(BaseModel):
    value: str


@router.get("/status")
def status() -> dict:
    """Configuration and stored login state. Never returns the secret."""
    client, _login = _mods()
    creds = client.load_credentials()
    token = client.load_token()
    return {
        "configured": bool(creds["client_id"] and creds["client_secret"]),
        "source": creds.get("source") or None,
        "client_id": creds["client_id"] or None,
        "client_secret_set": bool(creds["client_secret"]),
        "redirect_uri": creds["redirect_uri"],
        "user_agent": creds["user_agent"],
        "config_file": str(client.config_path()),
        "token_file": str(client.token_path()),
        "logged_in": bool(token.get("refresh_token")),
        "username": token.get("username") or None,
        "scopes": token.get("scope") or None,
        "setup_url": "https://www.reddit.com/prefs/apps",
        "background_refresh": bool(client.load_config().get("background_refresh")),
        "protect_secrets": bool(client.load_config().get("protect_secrets")),
        "secret_protection_available": os.name == "nt",
    }


@router.post("/config")
def save_config(payload: ConfigPayload) -> dict:
    """Save app credentials, verifying them first unless asked not to."""
    client, _login = _mods()
    if not any(getattr(payload, key) is not None for key in ("client_id", "client_secret", "redirect_uri", "user_agent")):
        try:
            if payload.background_refresh is not None:
                client.save_config({"background_refresh": payload.background_refresh})
            if payload.protect_secrets is not None:
                client.protect_credentials(payload.protect_secrets)
        except Exception as exc:
            raise _reddit_error(exc) from exc
        return {"settings_saved": True}
    creds = client.load_credentials()
    client_id = (payload.client_id or "").strip() or creds["client_id"]
    secret = (payload.client_secret or "").strip() or creds["client_secret"]
    if not client_id or not secret:
        raise HTTPException(
            status_code=400,
            detail="Client id and client secret are both required the first time. "
            "Get them from https://www.reddit.com/prefs/apps.",
        )
    redirect = (payload.redirect_uri or "").strip() or creds["redirect_uri"]
    user_agent = (payload.user_agent or "").strip() or creds["user_agent"]

    validation = None
    if payload.verify:
        try:
            validation = client.validate_app(client_id, secret, user_agent)
        except Exception as exc:  # noqa: BLE001 - surfaced to the settings page
            raise _reddit_error(exc) from exc

    path = client.save_config(
        {
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": redirect,
            "user_agent": user_agent,
        }
    )
    if payload.background_refresh is not None:
        client.save_config({"background_refresh": payload.background_refresh})
    if payload.protect_secrets is not None:
        try:
            client.protect_credentials(payload.protect_secrets)
        except Exception as exc:
            raise _reddit_error(exc) from exc
    return {
        "saved": str(path),
        "client_id": client_id,
        "redirect_uri": redirect,
        "user_agent": user_agent,
        "validation": validation,
    }


@router.post("/login/start")
def login_start(payload: LoginStartPayload | None = None) -> dict:
    """Begin the OAuth flow and return the consent URL."""
    _client, login = _mods()
    payload = payload or LoginStartPayload()
    try:
        return login.start(
            port=payload.port,
            redirect_uri=(payload.redirect_uri or "").strip(),
            scope=(payload.scope or "").strip(),
        )
    except Exception as exc:  # noqa: BLE001
        raise _reddit_error(exc) from exc


@router.get("/login/status")
def login_status() -> dict:
    """Poll the flow; exchanges the code as soon as the catcher has it."""
    _client, login = _mods()
    try:
        return login.result()
    except Exception as exc:  # noqa: BLE001
        raise _reddit_error(exc) from exc


@router.post("/login/complete")
def login_complete(payload: LoginCompletePayload) -> dict:
    """Finish the flow from a full redirect URL including its state."""
    _client, login = _mods()
    try:
        code, state = login.parse_code(payload.value)
        return login.finish(code, state=state)
    except Exception as exc:  # noqa: BLE001
        raise _reddit_error(exc) from exc


@router.post("/logout")
def logout() -> dict:
    _client, login = _mods()
    return login.logout()


@router.get("/identity")
def identity() -> dict:
    """Live account check: one API call against the stored token."""
    client, _login = _mods()
    session = client.session()
    if not session.has_refresh_token:
        return {"logged_in": False, "hint": "Press Log in to authorize an account."}
    try:
        return session.identity()
    except Exception as exc:  # noqa: BLE001
        raise _reddit_error(exc) from exc


class LibraryAction(BaseModel):
    action: str
    target: str = ""
    account: str = ""
    pages: int = 1
    after: str = ""
    summary: str | None = None
    context: str | None = None
    notes: str | None = None
    tags: list[str] | None = None
    bookmarks: dict | None = None
    source_hash: str | None = None


@router.get("/library")
def library_search(query: str = "", account: str = "", offset: int = 0, limit: int = 25,
                   tag: str = "", subreddit: str = "", summary_source: str = "", read: bool | None = None):
    _mods()
    lib, upkeep = importlib.import_module("reddit.library"), importlib.import_module("reddit.maintenance")
    try:
        store = lib.Library(account)
        return {"results": store.search(query, limit, offset, tag=tag, subreddit=subreddit, summary_source=summary_source, read=read),
                "stats": store.stats(), "maintenance": upkeep.status()}
    except Exception as exc:
        raise _reddit_error(exc) from exc


@router.post("/library")
def library_action(payload: LibraryAction):
    _mods()
    import json
    tools = importlib.import_module("reddit.tools")
    result = json.loads(tools.reddit_library(payload.model_dump(exclude_none=True)))
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Library operation failed")
    return result["result"]
