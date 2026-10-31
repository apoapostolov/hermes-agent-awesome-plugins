"""Regression tests for defects found in the audit.

Each test drives the real code path with a fake transport and fails on the
pre-fix source:

- one shared token file temp name crashed two concurrent tool calls
  (``os.replace`` -> WinError 32),
- an app-only call left its token in the account slot, so the next user call
  authenticated as the app,
- a failed code exchange kept the dead code in ``PENDING`` and raised on every
  poll, which the settings page swallowed into a permanent "waiting" state,
- the absolute-URL guard tested the path *after* prefixing it with "/", so it
  could never fire,
- every tool call rewrote the token file on refresh, which is what made the
  concurrent save collision reachable in normal use.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reddit import client, login  # noqa: E402


def _reset_session():
    """Pre-fix builds have no process-wide session; keep the control run honest."""
    reset = getattr(client, "reset_session", None)
    if reset is not None:
        reset()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    _reset_session()
    client.save_config(
        {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "user_agent": "hermes-reddit-test/0.1",
            "redirect_uri": client.DEFAULT_REDIRECT_URI,
        }
    )
    client.save_token(
        {
            "refresh_token": "refresh-token",
            "scope": "identity read",
            "username": "someone",
        }
    )
    yield
    login._shutdown()
    _reset_session()


class _Response:
    status = 200
    headers: dict = {}

    def __init__(self, body: bytes = b"{}"):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def fake_transport(monkeypatch):
    """Record every request and answer token grants locally."""

    class Transport:
        def __init__(self):
            self.requests: list[str] = []
            self.grants: list[str] = []
            self.body = b'{"name": "someone", "id": "abc"}'

        def post(self, url, data, headers, timeout=30.0):
            self.grants.append(data.get("grant_type", ""))
            if data.get("grant_type") == "client_credentials":
                return 200, {"access_token": "APP-TOKEN", "expires_in": 3600, "scope": "read"}
            return 200, {
                "access_token": "USER-TOKEN",
                "expires_in": 3600,
                "scope": "identity read",
            }

        def open(self, request, timeout=None):
            self.requests.append(request.get_header("Authorization") or "")
            return _Response(self.body)

    transport = Transport()
    monkeypatch.setattr(client, "_post_form", transport.post)
    monkeypatch.setattr(urllib.request, "urlopen", transport.open)
    return transport


# --------------------------------------------------------------- atomic writes
def test_concurrent_token_saves_never_collide(isolated_home):
    """Two tool calls can run at once; a shared .tmp name lost that race."""
    errors: list[BaseException] = []
    stop = time.time() + 1.5

    def writer(tag: str) -> None:
        try:
            while time.time() < stop:
                client.save_token({"refresh_token": "refresh-token", "writer": tag})
        except BaseException as exc:  # noqa: BLE001 - the assertion is the point
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(f"w{n}",)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert json.loads(client.token_path().read_text(encoding="utf-8"))["refresh_token"] == "refresh-token"
    assert [p.name for p in client.token_path().parent.glob("*.tmp")] == []


def test_save_config_keeps_the_whole_merged_record(isolated_home):
    client.save_config({"user_agent": "ua/1"})
    client.save_config({"redirect_uri": "http://localhost:9999"})
    stored = json.loads(client.config_path().read_text(encoding="utf-8"))
    assert stored["client_id"] == "test-client"
    assert stored["user_agent"] == "ua/1"
    assert stored["redirect_uri"] == "http://localhost:9999"


# ------------------------------------------------------------- app-only tokens
def test_app_only_call_does_not_become_the_account_token(isolated_home, fake_transport):
    session = client.Reddit()
    session.request("GET", "/r/hermesagent/new", app_only=True)
    fake_transport.requests.clear()

    session.request("GET", "/api/v1/me")

    assert fake_transport.requests == ["bearer USER-TOKEN"]


def test_app_only_token_is_reused_until_it_expires(isolated_home, fake_transport):
    session = client.Reddit()
    session.request("GET", "/r/hermesagent/new", app_only=True)
    session.request("GET", "/r/hermesagent/top", app_only=True)
    assert fake_transport.grants.count("client_credentials") == 1


# ------------------------------------------------------------------ url guard
def test_request_refuses_absolute_urls(isolated_home, fake_transport):
    session = client.Reddit()
    with pytest.raises(client.RedditError, match="not a URL"):
        session.request("GET", "http://169.254.169.254/latest/meta-data/")
    assert fake_transport.requests == []


def test_request_still_accepts_a_path_without_a_leading_slash(isolated_home, fake_transport):
    session = client.Reddit()
    session.request("GET", "api/v1/me")
    assert fake_transport.requests == ["bearer USER-TOKEN"]


# ---------------------------------------------------------------- failed login
def test_failed_exchange_reports_failed_and_drops_the_dead_code(isolated_home, monkeypatch):
    def boom(*args, **kwargs):
        raise client.RedditError("code exchange failed (400): {'error': 'invalid_grant'}")

    monkeypatch.setattr(client, "exchange_code", boom)
    with login._LOCK:
        login.PENDING.update(
            {
                "state": "expected-state",
                "redirect_uri": client.DEFAULT_REDIRECT_URI,
                "result": {"code": "used-code", "state": "expected-state"},
                "error": "",
                "started_at": time.time(),
            }
        )

    first = login.result()
    second = login.result()  # a real poll runs again a second later

    assert first["status"] == "failed"
    assert "invalid_grant" in first["error"]
    assert second["status"] == "failed"
    assert login.PENDING["result"] is None
    assert login.PENDING["error"] == first["error"]


def test_busy_port_clears_the_pending_state(isolated_home):
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        port = blocker.getsockname()[1]
        with login._LOCK:
            login.PENDING.update({"result": {"code": "stale", "state": "s"}, "error": ""})
        with pytest.raises(client.RedditError, match="Cannot listen"):
            login.start(port=port)
        assert login.PENDING["result"] is None
        assert login.PENDING["error"]


# ------------------------------------------------------------------ write churn
def test_refresh_does_not_rewrite_the_token_file(isolated_home, fake_transport):
    stamps = []
    for _ in range(3):
        session = client.Reddit()
        session.refresh()
        stamps.append(client.token_path().stat().st_mtime_ns)
    assert len(set(stamps)) == 1


def test_refresh_persists_a_new_scope(isolated_home, monkeypatch):
    monkeypatch.setattr(
        client,
        "_post_form",
        lambda *a, **k: (200, {"access_token": "USER-TOKEN", "expires_in": 3600, "scope": "identity read submit"}),
    )
    client.Reddit().refresh()
    stored = json.loads(client.token_path().read_text(encoding="utf-8"))
    assert stored["scope"] == "identity read submit"


# ---------------------------------------------------------------- session cache
def test_session_is_reused_across_calls(isolated_home):
    assert client.session() is client.session()


def test_session_rebuilds_after_login_or_logout(isolated_home):
    before = client.session()
    client.save_token({"refresh_token": "new-token", "scope": "identity"})
    after = client.session()
    assert after is not before
    assert after.token["refresh_token"] == "new-token"

    client.clear_token()
    assert client.session().has_refresh_token is False


def test_one_refresh_serves_many_tool_calls(isolated_home, fake_transport):
    from reddit import tools

    for _ in range(3):
        tools.reddit_api({"path": "/api/v1/me"})
    assert fake_transport.grants.count("refresh_token") == 1
