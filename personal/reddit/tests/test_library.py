"""Local-library regressions, account boundaries and API error handling."""
import argparse
import io
import json
import sys
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from reddit import cli, client, library, login, tools


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    client.reset_session()
    yield
    login._shutdown()
    login.PENDING.update(state="", started_at=0, result=None, error="", redirect_uri="")
    client.reset_session()


def item(name="t3_abc", body="SQLite query planner with indexes", author="writer", **extra):
    data = dict(name=name, id=name[3:], author=author, subreddit="Programming",
                title="Database tuning" if name.startswith("t3_") else "",
                score=12, permalink="/r/Programming/comments/abc/title/",
                **({"selftext": body} if name.startswith("t3_") else {"body": body, "link_id": "t3_abc", "parent_id": "t3_abc"}))
    data.update(extra)
    return {"kind": name[:2], "data": data}


def test_capture_summary_search_notes_tags_and_full_body():
    store = library.Library("owner")
    store.upsert(item())
    store.annotate("t3_abc", summary="Indexed queries", context="Useful for the migration", notes="Review this Friday", tags=["Backend", "backend"])
    result = store.search('"the migration" Friday -mysql', tag="BACKEND", subreddit="r/programming")
    assert result["total"] == 1
    assert result["items"][0]["summary_source"] == "agent_or_user"
    assert store.get("t3_abc")["body"] == "SQLite query planner with indexes"
    assert store.get("t3_abc")["tags"] == ["backend"]


def test_expiry_purges_all_source_and_derived_text_from_disk(monkeypatch):
    store = library.Library("owner")
    store.upsert(item(body="unique_source_content_to_purge"))
    store.annotate("t3_abc", summary="unique_summary_to_purge", notes="unique_note_to_purge", tags=["unique_tag_to_purge"])
    before = library.time.time()
    monkeypatch.setattr(library.time, "time", lambda: before + library.TTL + 1)
    assert store.search("unique")["total"] == 0
    expired = store.get("t3_abc")
    assert expired["stale"] is True
    assert "author" not in expired
    assert "body" not in expired
    raw = store.path.read_bytes()
    for word in (b"unique_source_content_to_purge", b"unique_summary_to_purge", b"unique_note_to_purge", b"unique_tag_to_purge"):
        assert word not in raw
    with pytest.raises(client.RedditError, match="refresh"):
        store.annotate("t3_abc", notes="cannot revive by annotation")


def test_annotation_does_not_extend_retention(monkeypatch):
    store = library.Library("owner")
    store.upsert(item())
    checked = store.get("t3_abc")["checked_at"]
    monkeypatch.setattr(library.time, "time", lambda: checked + 1000)
    store.annotate("t3_abc", notes="later")
    assert store.get("t3_abc")["checked_at"] == checked


def test_changed_source_invalidates_derived_context_but_scores_do_not():
    store = library.Library("owner")
    store.upsert(item())
    store.annotate("t3_abc", summary="custom summary", notes="custom notes")
    store.upsert(item(score=13))
    assert store.get("t3_abc")["summary"] == "custom summary"
    store.upsert(item(body="Edited replacement"))
    record = store.get("t3_abc")
    assert record["summary_source"] == "extractive"
    assert record["notes"] == ""


def test_accounts_and_profiles_are_separate(monkeypatch, tmp_path):
    one = library.Library("one")
    one.upsert(item(body="private material"))
    assert library.Library("two").search("private")["total"] == 0
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "other-profile"))
    assert library.Library("one").search("private")["total"] == 0


@pytest.mark.parametrize("query", ["%", "_", "' OR 1=1 --", '"unterminated'])
def test_search_is_literal_and_parameters_are_not_sql(query):
    store = library.Library("owner")
    store.upsert(item())
    if query.startswith('"'):
        with pytest.raises(client.RedditError):
            store.search(query)
    else:
        assert store.search(query)["total"] == 0


def test_unicode_comment_search_rank_and_pagination():
    store = library.Library("owner")
    store.upsert(item("t1_def", body="БЪЛГАРСКИ Straße SQLite", link_id="t3_abc"))
    store.upsert(item("t3_abc", body="sqlite body", title="SQLite title"))
    assert store.search("български strasse", kind="t1")["total"] == 1
    result = store.search("sqlite", limit=1)
    assert result["items"][0]["name"] == "t3_abc"
    assert result["next_offset"] == 1
    assert store.search("sqlite", limit=1, offset=1)["items"][0]["name"] == "t1_def"


def test_parallel_writes_preserve_items():
    store = library.Library("owner")
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: store.upsert(item(f"t3_a{n}")), range(12)))
    assert store.search()["total"] == 12


def test_deletion_removes_derived_content_in_every_account():
    one, two = library.Library("one"), library.Library("two")
    one.upsert(item())
    two.upsert(item())
    one.upsert(item(body="[deleted]"))
    assert one.search()["total"] == two.search()["total"] == 0


def test_redacted_author_does_not_prove_other_sources_are_deleted():
    store = library.Library("owner")
    store.upsert(item("t3_abc"))
    store.upsert(item("t3_def"))
    store.upsert(item("t3_abc", author="[deleted]"))
    assert store.search()["total"] == 1


class Session:
    def __init__(self):
        self.calls = []
        self.pages = [{"data": {"children": [item()], "after": "t3_next"}},
                      {"data": {"children": [item("t1_def")], "after": None}}]

    def require_account(self):
        return "owner"

    def account_listing(self, where, limit, after, raw):
        self.calls.append((where, after))
        return self.pages.pop(0)

    def info(self, names):
        return {"data": {"children": []}}


def test_sync_resumes_without_assuming_a_complete_export():
    store, session = library.Library("owner"), Session()
    result = library.sync_saved(session, store)
    assert result["stored"] == 1 and result["has_more"]
    result = library.sync_saved(session, store, after=result["after"])
    assert not result["has_more"]
    assert session.calls == [("saved", ""), ("saved", "t3_next")]
    assert store.get("t1_def")["remote_saved"] is True
    assert store.search()["total"] == 2


def test_sync_rejects_another_account():
    with pytest.raises(client.RedditError, match="match"):
        library.sync_saved(Session(), library.Library("someone_else"))


def test_refresh_missing_and_malformed_responses():
    store, session = library.Library("owner"), Session()
    store.upsert(item())
    assert library.refresh(session, store, ["t3_abc"])["removed"] == 1
    store.upsert(item())
    session.info = lambda names: {"error": "unavailable"}
    with pytest.raises(client.RedditError, match="no local items"):
        library.refresh(session, store, ["t3_abc"])
    assert store.get("t3_abc")["body"]


@pytest.mark.parametrize("url,expected", [
    ("https://www.reddit.com/r/test/comments/abc/title/def/", "t1_def"),
    ("https://redd.it/abc", "t3_abc"), ("t1_def", "t1_def"),
])
def test_normalize_reddit_urls(url, expected):
    assert client.normalize_fullname(url) == expected


@pytest.mark.parametrize("url", ["https://evil.example/comments/abc/title/def/", "https://reddit.com/r/test/s/shareid", "abc"])
def test_reject_ambiguous_urls(url):
    with pytest.raises(client.RedditError):
        client.normalize_fullname(url)


def test_save_can_succeed_when_local_snapshot_fails(monkeypatch):
    session = Session()
    session.save = lambda *args: {}
    monkeypatch.setattr(client, "session", lambda: session)
    result = json.loads(tools.reddit_manage({"action": "save", "target": "t3_abc"}))
    assert result["ok"] and result["result"]["remote_saved"]
    assert "local_error" in result["result"]


def test_subscribe_uses_the_correct_name_field(monkeypatch):
    session = client.Reddit(creds={"client_id": "x"}, token={})
    calls = []
    monkeypatch.setattr(session, "request", lambda *a, **kw: calls.append(kw["data"]))
    session.subscribe("r/test")
    session.subscribe("t5_abc")
    assert calls == [{"sr_name": "test", "action": "sub"}, {"sr": "t5_abc", "action": "sub"}]


class Response:
    headers = {}
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self):
        return self.body


def test_api_http_200_errors_are_failures(monkeypatch):
    session = client.Reddit(token={})
    monkeypatch.setattr(session, "_token_for", lambda *a: ("fake", "account"))
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda *a, **kw: Response(b'{"json":{"errors":[["RATELIMIT","try later",""]]}}'))
    with pytest.raises(client.RedditError, match="RATELIMIT"):
        session.request("POST", "/api/save", data={"id": "t3_abc"})


def test_long_rate_limit_is_not_retried_early(monkeypatch):
    session = client.Reddit(token={})
    monkeypatch.setattr(session, "_token_for", lambda *a: ("fake", "account"))
    count = []
    def reject(*args, **kwargs):
        count.append(1)
        raise urllib.error.HTTPError("https://oauth.reddit.com", 429, "rate", {"Retry-After": "600"}, io.BytesIO(b"{}"))
    monkeypatch.setattr(client.urllib.request, "urlopen", reject)
    with pytest.raises(client.RedditError, match="601 seconds"):
        session.request("GET", "/r/test/new")
    assert len(count) == 1


def test_delete_preserves_form_body_and_app_only_writes_are_rejected(monkeypatch):
    session = client.Reddit(token={})
    with pytest.raises(client.RedditError, match="read-only"):
        session.request("POST", "/api/save", app_only=True)
    monkeypatch.setattr(session, "_token_for", lambda *a: ("fake", "account"))
    seen = []
    monkeypatch.setattr(client.urllib.request, "urlopen", lambda req, **kw: (seen.append(req) or Response(b"{}")))
    session.request("DELETE", "/api/test", data={"model": "value"})
    assert b"model=value" in seen[0].data


def test_cli_local_roundtrip(capsys):
    parser = argparse.ArgumentParser()
    cli.setup_parser(parser)
    assert cli.handle(parser.parse_args(["library", "stats"])) == 0
    assert json.loads(capsys.readouterr().out)["result"]["fresh"] == 0


def test_manual_oauth_completion_requires_matching_persisted_state(monkeypatch):
    client.save_config({"client_id": "c", "client_secret": "s"})
    client._atomic_write(client.hermes_home() / "reddit-login-pending.json", json.dumps({"state": "expected", "redirect_uri": "http://localhost:8099", "started_at": login.time.time()}))
    login.PENDING.update(state="", redirect_uri="", started_at=0)
    monkeypatch.setattr(client, "exchange_code", lambda *a: {"refresh_token": "fake", "scope": "identity read"})
    monkeypatch.setattr(client.Reddit, "me", lambda self: {"name": "owner"})
    with pytest.raises(client.RedditError, match="state mismatch"):
        login.finish("code")
    assert login.finish("code", state="expected")["username"] == "owner"
    assert not (client.hermes_home() / "reddit-login-pending.json").exists()


def test_login_uses_the_configured_port_by_default():
    client.save_config({"client_id": "c", "client_secret": "s", "redirect_uri": "http://localhost:8099"})
    result = login.start()
    assert result["listening_on"].endswith(":8099")


def test_comment_search_is_not_falsely_advertised():
    with pytest.raises(client.RedditError, match="does not support comment"):
        client.Reddit(token={}).search("query", kind="comment")
