"""Offline tests for the reddit plugin: no network, no real credentials."""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reddit import client, login, tools  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Fresh Hermes home with one app already configured in the plugin config file."""
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    # Credentials never come from the environment; prove it by setting them.
    monkeypatch.setenv("REDDIT_CLIENT_ID", "env-should-be-ignored")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "env-should-be-ignored")
    monkeypatch.setenv("REDDIT_USER_AGENT", "env-should-be-ignored")
    client.save_config(
        {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "user_agent": "hermes-reddit-test/0.1",
            "redirect_uri": client.DEFAULT_REDIRECT_URI,
        }
    )
    yield
    login._shutdown()


def test_scopes_are_the_live_reddit_scope_set():
    # Mirrors GET /api/v1/scopes; a typo here makes the consent page fail with
    # "invalid scope requested".
    valid = {
        "account", "announcements", "creddits", "edit", "flair", "history",
        "identity", "livemanage", "modconfig", "modcontributors", "modflair",
        "modlog", "modmail", "modnote", "modothers", "modposts", "modself",
        "modtraffic", "modwiki", "mysubreddits", "privatemessages", "read",
        "report", "save", "structuredstyles", "submit", "subscribe", "vote",
        "wikiedit", "wikiread",
    }
    assert set(client.ALL_SCOPES.split()) == valid


def test_credentials_come_from_the_config_file(isolated_home):
    creds = client.load_credentials()
    assert creds["client_id"] == "test-client"
    assert creds["source"] == "config"
    assert creds["redirect_uri"] == client.DEFAULT_REDIRECT_URI


def test_environment_is_never_read_for_credentials(isolated_home):
    """A bare os.environ read can pick up another profile's values (catalog rule 11)."""
    creds = client.load_credentials()
    assert "env-should-be-ignored" not in (creds["client_id"], creds["client_secret"])
    assert creds["user_agent"] == "hermes-reddit-test/0.1"


def test_dot_env_file_is_not_read(tmp_path, monkeypatch):
    client.clear_token()
    (tmp_path / "reddit-config.json").unlink()
    (tmp_path / ".env").write_text(
        "REDDIT_CLIENT_ID=file-client\nREDDIT_CLIENT_SECRET=file-secret\n", encoding="utf-8"
    )
    creds = client.load_credentials()
    assert creds["client_id"] == ""
    assert creds["source"] == ""


def test_token_file_supplies_redirect_uri_when_config_is_gone():
    client.save_config({"client_id": "cfg", "client_secret": "s"})
    client.save_token({"refresh_token": "rt", "redirect_uri": "http://localhost:9099"})
    client.load_config  # noqa: B018 - keep the reference explicit
    path = client.config_path()
    path.unlink()
    creds = client.load_credentials()
    assert creds["redirect_uri"] == "http://localhost:9099"


def test_nothing_configured_returns_empty_client_id():
    client.config_path().unlink()
    client.clear_token()
    creds = client.load_credentials()
    assert creds["client_id"] == ""
    assert creds["redirect_uri"] == client.DEFAULT_REDIRECT_URI
    assert "reddit_setup" in client.SETUP_HINT


def test_save_config_merges_and_keeps_mode(isolated_home):
    path = client.save_config({"client_id": "a", "client_secret": "b"})
    client.save_config({"user_agent": "ua/1.0"})
    data = client.load_config()
    assert data["client_id"] == "a"
    assert data["user_agent"] == "ua/1.0"
    assert path == client.config_path()
    if os.name == "posix":
        assert (path.stat().st_mode & 0o777) == 0o600


def test_setup_tool_reports_unconfigured_state(monkeypatch, tmp_path):
    client.config_path().unlink()
    client.clear_token()
    payload = json.loads(tools.reddit_setup({}))
    assert payload["ok"] is True
    assert payload["result"]["configured"] is False
    assert payload["result"]["config_file"].endswith("reddit-config.json")
    assert "reddit.com/prefs/apps" in payload["result"]["hint"]


def test_setup_tool_saves_and_validates(monkeypatch):
    monkeypatch.setattr(
        client, "validate_app", lambda *a: {"app_token": "ok", "sample_title": "hi"}
    )
    payload = json.loads(
        tools.reddit_setup(
            {
                "client_id": "user-client",
                "client_secret": "user-secret",
                "redirect_uri": "http://localhost:8080",
            }
        )
    )
    assert payload["ok"] is True
    assert payload["result"]["validation"]["app_token"] == "ok"
    saved = client.load_config()
    assert saved["client_id"] == "user-client"
    assert saved["client_secret"] == "user-secret"
    assert "user-secret" not in json.dumps(payload)


def test_setup_tool_requires_both_halves(monkeypatch, isolated_home):
    client.config_path().unlink()
    client.clear_token()
    payload = json.loads(tools.reddit_setup({"client_id": "only-id"}))
    assert payload["ok"] is False
    assert "client_secret" in payload["error"]


def test_login_uses_configured_redirect_uri(monkeypatch):
    client.save_config(
        {
            "client_id": "cfg-client",
            "client_secret": "cfg-secret",
            "redirect_uri": "http://localhost:8099",
        }
    )
    started = login.start()
    assert started["redirect_uri"] == "http://localhost:8099"
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8099" in started["authorize_url"]


def test_token_roundtrip_and_clear(isolated_home):
    client.save_token({"refresh_token": "r", "username": "u"})
    assert client.load_token()["username"] == "u"
    assert client.clear_token() is True
    assert client.load_token() == {}


def test_authorize_url_carries_state_and_scopes(isolated_home):
    url = client.build_authorize_url("cid", "http://localhost:8080", "st4te", scope="read vote")
    assert "client_id=cid" in url
    assert "state=st4te" in url
    assert "scope=read+vote" in url or "scope=read%20vote" in url
    assert "duration=permanent" in url


def test_compact_listing_flattens_links():
    payload = {
        "data": {
            "after": "t3_next",
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc",
                        "name": "t3_abc",
                        "author": "someone",
                        "subreddit": "hermesagent",
                        "title": "A post",
                        "score": 42,
                        "num_comments": 7,
                        "permalink": "/r/hermesagent/comments/abc/a_post/",
                        "created_utc": 1700000000,
                        "selftext": "body",
                    },
                }
            ],
        }
    }
    out = client.compact_listing(payload)
    assert out["count"] == 1
    assert out["after"] == "t3_next"
    item = out["items"][0]
    assert item["title"] == "A post"
    assert item["permalink"].endswith("/a_post/")
    assert item["comments"] == 7


def test_normalize_thread_id_accepts_urls_and_fullnames():
    assert client.normalize_thread_id("t3_abc123") == "abc123"
    assert (
        client.normalize_thread_id(
            "https://www.reddit.com/r/hermesagent/comments/xyz789/some_title/?utm=1"
        )
        == "xyz789"
    )


class _FakeResponse:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()
        self.headers = {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_request_refreshes_and_sets_bearer(monkeypatch, isolated_home):
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request)
        return _FakeResponse({"data": {"children": [], "after": None}})

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    session = client.Reddit(
        creds={
            "client_id": "c",
            "client_secret": "s",
            "user_agent": "ua",
            "redirect_uri": client.DEFAULT_REDIRECT_URI,
        },
        token={"refresh_token": "rt"},
    )
    monkeypatch.setattr(
        session, "refresh", lambda force=False: "access-token"
    )
    session.request("GET", "/r/test/new", params={"limit": 5})
    assert calls[0].full_url.startswith("https://oauth.reddit.com/r/test/new")
    assert "limit=5" in calls[0].full_url
    assert calls[0].get_header("Authorization") == "bearer access-token"


def test_refresh_posts_the_stored_token(monkeypatch, isolated_home):
    seen = {}

    def fake_post_form(url, data, headers, timeout=30.0):
        seen["url"] = url
        seen["data"] = data
        seen["auth"] = headers["Authorization"]
        return 200, {"access_token": "new", "expires_in": 3600, "scope": "read"}

    monkeypatch.setattr(client, "_post_form", fake_post_form)
    session = client.Reddit(
        creds={
            "client_id": "c",
            "client_secret": "s",
            "user_agent": "ua",
            "redirect_uri": client.DEFAULT_REDIRECT_URI,
        },
        token={"refresh_token": "rt"},
    )
    assert session.refresh(force=True) == "new"
    assert seen["data"]["grant_type"] == "refresh_token"
    assert seen["data"]["refresh_token"] == "rt"
    assert seen["auth"].startswith("Basic ")


def test_login_start_and_callback_roundtrip(monkeypatch, isolated_home):
    exchanged = {}

    def fake_exchange(client_id, client_secret, code, redirect_uri, user_agent):
        exchanged.update(code=code, redirect=redirect_uri)
        return {"access_token": "a", "refresh_token": "r", "scope": "read", "expires_in": 3600}

    monkeypatch.setattr(client, "exchange_code", fake_exchange)
    monkeypatch.setattr(
        client.Reddit, "me", lambda self: {"name": "tester", "id": "t2_x"}
    )

    started = login.start(port=0)
    port = started["listening_on"].rsplit(":", 1)[1]
    state = started["state"]
    url = f"http://127.0.0.1:{port}/?code=thecode&state={state}"
    with urllib.request.urlopen(url, timeout=5) as response:
        assert response.status == 200
    done = login.result()
    assert done["status"] == "logged_in"
    assert done["username"] == "tester"
    assert exchanged["code"] == "thecode"
    assert client.load_token()["refresh_token"] == "r"


def test_callback_rejects_wrong_state(monkeypatch, isolated_home):
    started = login.start(port=0)
    port = started["listening_on"].rsplit(":", 1)[1]
    url = f"http://127.0.0.1:{port}/?code=thecode&state=wrong"
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url, timeout=5)
    state = login.result()
    assert state["status"] == "failed"
    assert state["error"] == "state mismatch"


def test_parse_code_accepts_url_and_bare_code():
    code, state = login.parse_code("http://localhost:8080/?code=abc&state=xyz")
    assert (code, state) == ("abc", "xyz")
    assert login.parse_code("bare") == ("bare", "")


def test_tool_errors_return_json(monkeypatch, isolated_home):
    client.config_path().unlink()
    client.clear_token()
    payload = json.loads(tools.reddit_login({"action": "start"}))
    assert payload["ok"] is False
    assert "No Reddit app configured" in payload["error"]


def test_status_reports_logged_out(isolated_home):
    payload = json.loads(tools.reddit_status({}))
    assert payload["ok"] is True
    assert payload["result"]["logged_in"] is False


def test_registration_exposes_every_schema():
    import reddit as plugin

    registered = {}

    class Ctx:
        def register_tool(self, **kwargs):
            registered[kwargs["name"]] = kwargs

        def register_cli_command(self, **kwargs):
            registered["cli"] = kwargs

    plugin.register(Ctx())
    assert registered["cli"]["name"] == "reddit"
    for schema in tools.SCHEMAS:
        entry = registered[schema["name"]]
        assert entry["toolset"] == "reddit"
        assert entry["schema"]["name"] == schema["name"]


def test_login_start_reports_busy_port(monkeypatch, isolated_home):
    import socket

    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    blocker.bind(("127.0.0.1", 0))
    blocker.listen(1)
    busy_port = blocker.getsockname()[1]
    try:
        with pytest.raises(client.RedditError) as exc:
            login.start(port=busy_port)
        assert "Cannot listen" in str(exc.value)
    finally:
        blocker.close()
