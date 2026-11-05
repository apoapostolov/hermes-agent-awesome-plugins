"""Tests for the reading paths: app-only fallback, thread depth, more expansion,
user pages and 429 pacing.

Every test drives the real client with a fake transport; no network, no
credentials.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from reddit import client, login, tools  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    client.save_config(
        {
            "client_id": "test-client",
            "client_secret": "test-secret",
            "user_agent": "hermes-reddit-test/0.1",
            "redirect_uri": client.DEFAULT_REDIRECT_URI,
        }
    )
    client.reset_session()
    yield
    login._shutdown()
    client.reset_session()


class _Response:
    def __init__(self, payload):
        self._payload = json.dumps(payload).encode()
        self.headers = {}

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _http_error(code: int, headers: dict | None = None) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://oauth.reddit.com/x",
        code,
        "error",
        headers or {},
        io.BytesIO(b'{"message": "Too Many Requests"}'),
    )


@pytest.fixture
def transport(monkeypatch):
    """Answer token grants locally and hand API URLs to a caller-supplied router."""

    class Transport:
        def __init__(self):
            self.urls: list[str] = []
            self.auth: list[str] = []
            self.grants: list[str] = []
            self.router = lambda url: _Response({"data": {"children": []}})
            self.sleeps: list[float] = []

        def post(self, url, data, headers, timeout=30.0):
            self.grants.append(data.get("grant_type", ""))
            if data.get("grant_type") == "client_credentials":
                return 200, {"access_token": "APP-TOKEN", "expires_in": 3600, "scope": "read"}
            return 200, {"access_token": "USER-TOKEN", "expires_in": 3600, "scope": "identity read"}

        def open(self, request, timeout=None):
            self.urls.append(request.full_url)
            self.auth.append(request.get_header("Authorization") or "")
            return self.router(request.full_url)

    transport = Transport()
    monkeypatch.setattr(client, "_post_form", transport.post)
    monkeypatch.setattr(urllib.request, "urlopen", transport.open)
    now, elapsed = client.time.time, [0]
    monkeypatch.setattr(client.time, "time", lambda: now() + elapsed[0])
    def advance(seconds):
        transport.sleeps.append(seconds)
        elapsed[0] += seconds
    monkeypatch.setattr(client.time, "sleep", advance)
    return transport


def test_a_read_without_a_login_uses_the_app_token(transport):
    session = client.Reddit(token={})
    transport.router = lambda url: _Response(
        {"data": {"children": [{"kind": "t3", "data": {"id": "a", "title": "hi"}}]}}
    )
    listing = session.subreddit("LocalLLaMA", limit=2)
    assert listing["count"] == 1
    assert "client_credentials" in transport.grants
    assert transport.auth[0] == "bearer APP-TOKEN"
    assert session.last_backend == "app"


def test_a_write_without_a_login_names_the_login_step(transport):
    session = client.Reddit(token={})
    with pytest.raises(client.RedditError) as exc:
        session.submit("test", "title")
    assert "reddit_login" in str(exc.value)


def test_a_read_with_no_app_and_no_login_explains_both_paths(transport):
    session = client.Reddit(creds={"client_id": "", "client_secret": ""}, token={})
    with pytest.raises(client.RedditError) as exc:
        session.subreddit("LocalLLaMA")
    assert "reddit_setup" in str(exc.value)


def test_a_429_waits_out_the_window_and_retries(transport):
    attempts = {"count": 0}

    def router(url):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise _http_error(429, {"retry-after": "7"})
        return _Response({"data": {"children": []}})

    transport.router = router
    session = client.Reddit(token={"refresh_token": "rt"})
    payload = session.request("GET", "/r/test/new")
    assert payload["data"]["children"] == []
    assert transport.sleeps == [8]
    assert session.last_rate["waited"] == "8"


def test_thread_keeps_reply_depth_and_expands_more(transport):
    tree = {
        "data": {
            "children": [
                {
                    "kind": "t1",
                    "data": {
                        "id": "c1",
                        "name": "t1_c1",
                        "author": "one",
                        "body": "top",
                        "score": 5,
                        "replies": {
                            "data": {
                                "children": [
                                    {
                                        "kind": "t1",
                                        "data": {
                                            "id": "c2",
                                            "name": "t1_c2",
                                            "author": "two",
                                            "body": "reply",
                                            "score": 2,
                                            "replies": "",
                                        },
                                    }
                                ]
                            }
                        },
                    },
                },
                {"kind": "more", "data": {"count": 3, "children": ["c3", "c4"], "parent_id": "t3_abc"}},
            ]
        }
    }
    post_listing = {
        "data": {
            "children": [
                {
                    "kind": "t3",
                    "data": {
                        "id": "abc",
                        "name": "t3_abc",
                        "title": "a post",
                        "permalink": "/r/test/comments/abc/a_post/",
                    },
                }
            ]
        }
    }
    morechildren = {
        "json": {
            "data": {
                "things": [
                    {
                        "kind": "t1",
                        "data": {
                            "id": "c3",
                            "name": "t1_c3",
                            "author": "three",
                            "body": "was hidden",
                            "parent_id": "t1_c1",
                        },
                    }
                ]
            }
        }
    }

    def router(url):
        if "/api/morechildren" in url:
            return _Response(morechildren)
        return _Response([post_listing, tree])

    transport.router = router
    session = client.Reddit(token={"refresh_token": "rt"})
    result = session.thread("t3_abc", comment_limit=10, expand_more=True)

    depths = {item["author"]: item["depth"] for item in result["comments"]}
    assert depths == {"one": 0, "two": 1, "three": 1}
    assert result["expanded"] == 1
    assert any("/api/morechildren" in url for url in transport.urls)


def test_thread_can_skip_more_expansion(transport):
    tree = {
        "data": {
            "children": [
                {"kind": "more", "data": {"count": 4, "children": ["c9"], "parent_id": "t3_abc"}}
            ]
        }
    }
    post_listing = {"data": {"children": [{"kind": "t3", "data": {"id": "abc"}}]}}
    transport.router = lambda url: _Response([post_listing, tree])
    session = client.Reddit(token={"refresh_token": "rt"})
    result = session.thread("abc", comment_limit=10, expand_more=False)
    assert result["comments"] == []
    assert result["hidden_comments"] == 4
    assert not any("/api/morechildren" in url for url in transport.urls)


def test_user_reads_the_overview_listing(transport):
    transport.router = lambda url: _Response(
        {
            "data": {
                "children": [
                    {"kind": "t1", "data": {"id": "c1", "author": "spez", "body": "hello"}}
                ]
            }
        }
    )
    session = client.Reddit(token={"refresh_token": "rt"})
    listing = session.user("u/spez", kind="comments", limit=5)
    assert listing["username"] == "spez"
    assert listing["kind"] == "comments"
    assert "/user/spez/comments" in transport.urls[0]


def test_user_tool_is_registered(monkeypatch, isolated_home):
    import reddit as plugin

    registered = {}

    class Ctx:
        def register_tool(self, **kwargs):
            registered[kwargs["name"]] = kwargs

        def register_cli_command(self, **kwargs):
            registered["cli"] = kwargs

    plugin.register(Ctx())
    assert "reddit_user" in registered
    assert any(schema["name"] == "reddit_user" for schema in tools.SCHEMAS)


def test_status_says_reads_still_work_without_a_login(isolated_home):
    client.clear_token()
    payload = json.loads(tools.reddit_status({}))
    result = payload["result"]
    assert result["logged_in"] is False
    assert result["read_only"] is True
    assert "Public subreddits" in result["hint"]
