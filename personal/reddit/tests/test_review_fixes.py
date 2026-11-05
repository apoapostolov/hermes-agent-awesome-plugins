"""Regressions for the review findings left open on the 1.1.0 release."""
import json
from contextlib import contextmanager

import pytest

from reddit import client, coordination, library, redaction, tools


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    client.reset_session()
    yield tmp_path
    client.reset_session()


def source(name="t3_abc", text="Query planner and indexes"):
    return {"kind": "t3", "data": {"name": name, "title": "SQLite", "selftext": text, "author": "writer", "subreddit": "test"}}


def test_unreadable_credentials_count_as_absent(home):
    client.save_config({"client_id": "abc", "client_secret": "shh"})
    client.save_token({"refresh_token": "tok"})
    client.config_path().write_text(json.dumps({"client_secret": {"$fernet": "not-a-real-token"}}), encoding="utf-8")
    client.token_path().write_text(json.dumps({"refresh_token": {"$fernet": "not-a-real-token"}}), encoding="utf-8")
    assert client.load_config() == {}
    assert client.load_token() == {}
    client.save_config({"client_id": "replacement", "client_secret": "new"})
    client.save_token({"refresh_token": "replacement"})
    assert client.load_config()["client_id"] == "replacement"
    assert client.load_token()["refresh_token"] == "replacement"


def test_protect_credentials_reads_the_token_under_the_lock(monkeypatch):
    depth = {"n": 0}
    real = coordination.file_lock

    @contextmanager
    def recorder(path, timeout=20):
        with real(path, timeout):
            depth["n"] += 1
            try:
                yield
            finally:
                depth["n"] -= 1

    seen = []
    monkeypatch.setattr(client.coordination, "file_lock", recorder)
    monkeypatch.setattr(client, "load_token", lambda home=None: (seen.append(depth["n"]), {})[1])
    monkeypatch.setattr(client, "save_token", lambda token, home=None: None)
    client.protect_credentials(True)
    assert seen and seen[0] > 0


def test_request_slot_releases_the_lock_before_the_body(monkeypatch):
    depth = {"n": 0}
    real = coordination.file_lock

    @contextmanager
    def recorder(path, timeout=20):
        with real(path, timeout):
            depth["n"] += 1
            try:
                yield
            finally:
                depth["n"] -= 1

    monkeypatch.setattr(coordination, "file_lock", recorder)
    with coordination.request_slot("client"):
        assert depth["n"] == 0


def test_recorded_429_still_blocks_the_next_slot():
    with coordination.request_slot("client") as budget:
        budget.capture({"Retry-After": "120"}, status=429)
    with pytest.raises(RuntimeError, match="Shared Reddit"):
        with coordination.request_slot("client"):
            pytest.fail("early retry")


def test_redaction_leaves_prose_after_basic_alone():
    assert redaction.safe("SQLite basic tutorial") == "SQLite basic tutorial"
    assert "[redacted]" in redaction.safe("Authorization: Basic dXNlcjpwYXNzd29yZA==")
    assert "[redacted]" in redaction.safe("Bearer secret-canary")
    assert "secret-canary" not in redaction.safe("Bearer secret-canary")


class Offline:
    has_refresh_token = False

    def __init__(self, payload):
        self.payload = payload

    def info(self, names):
        return self.payload


def test_capture_keeps_the_cache_when_reddit_returns_no_listing(monkeypatch):
    store = library.Library("owner")
    store.upsert(source())
    monkeypatch.setattr(client, "session", lambda: Offline({}))
    result = json.loads(tools.reddit_library({"action": "capture", "target": "t3_abc", "account": "owner"}))
    assert result["ok"] is False
    assert store.get("t3_abc") is not None


def test_capture_annotates_with_the_hash_it_stored(monkeypatch):
    store = library.Library("owner")
    store.upsert(source())
    payload = {"data": {"children": [source()]}}
    monkeypatch.setattr(client, "session", lambda: Offline(payload))
    seen = {}
    original = library.Library.annotate

    def spy(self, target, **kwargs):
        seen.update(kwargs)
        return original(self, target, **kwargs)

    monkeypatch.setattr(library.Library, "annotate", spy)
    result = json.loads(tools.reddit_library({"action": "capture", "target": "t3_abc", "account": "owner", "summary": "kept"}))
    assert result["ok"] is True
    assert seen.get("expected_hash") and len(seen["expected_hash"]) == 64


def test_upsert_reports_the_stored_hash():
    store = library.Library("owner")
    result = store.upsert(source())
    assert len(result["content_hash"]) == 64
    assert result["content_hash"] == store.get("t3_abc")["content_hash"]
