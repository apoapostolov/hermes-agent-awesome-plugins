"""Release regressions for maintenance, portability, credentials and management."""
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import pytest
from reddit import client, coordination, library, login, maintenance, management, tools


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    client.reset_session()
    yield tmp_path
    login._shutdown()
    client.reset_session()


def source(name="t3_abc", text="Query planner and indexes"):
    return {"kind": "t3", "data": {"name": name, "title": "SQLite", "selftext": text, "author": "writer", "subreddit": "test"}}


def test_summary_queue_read_status_and_bookmark_transfer():
    store = library.Library("owner")
    store.upsert(source())
    store.mark_read("t3_abc")
    store.upsert(source())
    assert store.search(read=True)["total"] == 1
    assert store.search(summary_source="extractive")["total"] == 1
    store.annotate("t3_abc", summary="Database guide", notes="private")
    assert store.search(summary_source="extractive")["total"] == 0
    exported = store.export_bookmarks()
    assert exported == {"format": "hermes-reddit-bookmarks", "version": 1, "items": [{"name": "t3_abc"}]}
    other = library.Library("other")
    assert other.import_bookmarks(exported)["imported"] == 1
    assert other.import_bookmarks(exported)["imported"] == 0
    assert other.get("t3_abc")["stale"]
    assert other.search()["total"] == 0


def test_invalid_import_is_atomic():
    store = library.Library("owner")
    with pytest.raises(client.RedditError):
        store.import_bookmarks({"format": "hermes-reddit-bookmarks", "version": 1, "items": [{"name": "t3_abc"}, {"name": "../invalid"}]})
    assert store.export_bookmarks()["items"] == []


def test_summary_hash_rejects_changed_source():
    store = library.Library("owner")
    store.upsert(source())
    old = store.get("t3_abc")["content_hash"]
    store.upsert(source(text="Replacement source"))
    with pytest.raises(client.RedditError, match="Source changed"):
        store.annotate("t3_abc", summary="Old summary", expected_hash=old)


def test_maintenance_uses_captured_profile(home, monkeypatch):
    store = library.Library("owner", home)
    store.upsert(source())
    now = library.time.time()
    monkeypatch.setattr(library.time, "time", lambda: now + library.TTL + 2)
    other = home / "another"
    monkeypatch.setenv("HERMES_HOME", str(other))
    assert maintenance.run_once(home)["purge"] == "complete"
    assert store.get("t3_abc")["stale"]
    assert not (other / "plugin-data/reddit/library.sqlite3").exists()


def test_background_revalidation_is_opt_in_and_bounded(home, monkeypatch):
    calls = []
    class Fake:
        has_refresh_token = True
        def __init__(self, home):
            calls.append(home)
        def require_account(self):
            return "owner"
        def info(self, names):
            assert len(names) <= 100
            return {"data": {"children": [source(n) for n in names]}}
    monkeypatch.setattr(client, "Reddit", Fake)
    maintenance.run_once(home)
    assert not calls
    library.Library("owner", home).upsert(source())
    client.save_config({"background_refresh": True}, home)
    assert maintenance.run_once(home)["refresh"]["checked"] == 1
    assert maintenance.run_once(home)["refresh"] == "not_due"
    assert len(calls) == 1


def test_shared_budget_prevents_another_client_instance_sending():
    with coordination.request_slot("client") as budget:
        budget.capture({"Retry-After": "120"}, status=429)
    with pytest.raises(RuntimeError, match="Shared Reddit"):
        with coordination.request_slot("client"):
            pytest.fail("early retry")
    with coordination.request_slot("other-client"):
        pass


def test_lock_excludes_another_process(home):
    code = "from reddit.coordination import file_lock; from pathlib import Path; import sys;\nwith file_lock(Path(sys.argv[1]),timeout=.2): print('acquired')"
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    path = home / "lock"
    with coordination.file_lock(path):
        result = subprocess.run([sys.executable, "-c", code, str(path)], capture_output=True, text=True, env=env, timeout=5)
    assert result.returncode != 0 and "busy in another process" in result.stderr


def test_shared_access_cache_reuses_refresh(home, monkeypatch):
    client.save_config({"client_id": "client", "client_secret": "secret"})
    client.save_token({"refresh_token": "refresh", "scope": "read"})
    grants = []
    def post(*args, **kwargs):
        grants.append(1)
        return 200, {"access_token": "access", "scope": "read", "expires_in": 3600}
    monkeypatch.setattr(client, "_post_form", post)
    results = []
    threads = [threading.Thread(target=lambda s=s: results.append(s.refresh())) for s in (client.Reddit(), client.Reddit())]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert results == ["access", "access"] and len(grants) == 1
    client.clear_token()
    assert not (home / "plugin-data/reddit/access-cache.json").exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_windows_secret_protection_roundtrip():
    client.save_config({"client_id": "client", "client_secret": "secret-canary"})
    client.save_token({"refresh_token": "refresh-canary"})
    assert client.protect_credentials()["protected"]
    assert "secret-canary" not in client.config_path().read_text()
    assert "refresh-canary" not in client.token_path().read_text()
    assert client.load_credentials()["client_secret"] == "secret-canary"
    assert client.load_token()["refresh_token"] == "refresh-canary"
    client.save_config({"user_agent": "updated"})
    assert "secret-canary" not in client.config_path().read_text()


def test_profile_cannot_clear_another_login(home, monkeypatch):
    client.save_config({"client_id": "c", "client_secret": "s"})
    flow = login.start(port=0)
    monkeypatch.setenv("HERMES_HOME", str(home / "other"))
    assert not login.result()["listening"]
    login.logout()
    assert login.PENDING["state"] == flow["state"]
    with pytest.raises(client.RedditError, match="No active login"):
        login.finish("code", state=flow["state"])


class Session:
    def __init__(self):
        self.calls = []
    def require_account(self):
        return "owner"
    def request(self, method, path, **kwargs):
        self.calls.append((method, path, kwargs))
        return {"data": {"children": []}}


def test_management_operations():
    session = Session()
    management.messages(session, {"action": "read", "targets": ["t4_abc"]})
    assert session.calls[-1][1] == "/api/read_message"
    management.moderation(session, {"action": "remove", "target": "t3_abc", "spam": True})
    assert session.calls[-1][2]["data"]["spam"] == "true"
    management.wiki(session, {"action": "edit", "subreddit": "test", "page": "guide/start", "content": "Markdown"})
    assert session.calls[-1][1] == "/r/test/api/wiki/edit"
    management.multis(session, {"action": "create", "name": "reading", "subreddits": ["test"]})
    assert json.loads(session.calls[-1][2]["data"]["model"])["subreddits"] == [{"name": "test"}]
    with pytest.raises(client.RedditError, match="authorized account"):
        management.multis(session, {"action": "delete", "name": "reading", "owner": "someone_else"})


@pytest.mark.parametrize("operation,args", [
    (management.messages, {"action": "read", "targets": ["bad"]}),
    (management.messages, {"action": "delete", "targets": ["t1_abc"]}),
    (management.wiki, {"subreddit": "test", "page": "../secret"}),
    (management.moderation, {"action": "queue", "subreddit": "test/../api"}),
    (management.moderation, {"action": "sticky", "target": "t1_abc"}),
])
def test_invalid_management_targets_never_reach_transport(operation, args):
    session = Session()
    with pytest.raises(client.RedditError):
        operation(session, args)
    assert not session.calls


def test_local_queue_and_export_do_not_make_network_client(monkeypatch):
    library.Library().upsert(source())
    monkeypatch.setattr(client, "session", lambda: pytest.fail("local action made network client"))
    assert json.loads(tools.reddit_library({"action": "queue"}))["result"]["total"] == 1
    assert json.loads(tools.reddit_library({"action": "read", "target": "t3_abc"}))["result"]["read"]
    assert json.loads(tools.reddit_library({"action": "export"}))["result"]["items"]


def test_credentials_are_encrypted_by_default_and_output_is_redacted(capsys):
    from reddit import cli, redaction
    client.save_config({"client_id": "id", "client_secret": "client-secret-canary"})
    client.save_token({"refresh_token": "refresh-secret-canary"})
    assert "client-secret-canary" not in client.config_path().read_text()
    assert "refresh-secret-canary" not in client.token_path().read_text()
    cli._print({"error": "echoed client-secret-canary and refresh-secret-canary", "access_token": "other-secret"})
    output = capsys.readouterr().out
    assert "client-secret-canary" not in output
    assert "refresh-secret-canary" not in output
    assert "other-secret" not in output
    assert "[redacted]" in output
    assert redaction.safe("Bearer unknown-token") == "Bearer [redacted]"


def test_tampered_ciphertext_is_treated_as_absent_and_recoverable():
    client.save_config({"client_id": "id", "client_secret": "client-secret-canary"})
    payload = json.loads(client.config_path().read_text())
    payload["client_secret"]["$fernet"] = "invalid"
    client.config_path().write_text(json.dumps(payload))
    # An unreadable protected file must read as absent rather than raise: a
    # credential file carried to another user or machine would otherwise block
    # recovery until it was moved aside by hand.
    assert client.load_config() == {}
    client.save_config({"client_id": "id", "client_secret": "replacement-secret"})
    assert client.load_config()["client_secret"] == "replacement-secret"


def test_lost_access_does_not_remove_another_account_copy():
    first, second = library.Library("first"), library.Library("second")
    first.upsert(source())
    second.upsert(source())
    class Missing:
        def info(self, names):
            return {"data": {"children": []}}
    library.refresh(Missing(), second, ["t3_abc"])
    assert first.get("t3_abc")["body"]
    assert second.search()["total"] == 0


def test_mod_log_preserves_action_and_target():
    expected = {"data": {"children": [{"data": {"action": "removecomment", "mod": "moderator", "target_fullname": "t1_abc", "details": "spam"}}]}}
    class LogSession(Session):
        def request(self, *args, **kwargs):
            return expected
    assert management.moderation(LogSession(), {"action": "log", "subreddit": "test"}) == expected


@pytest.mark.parametrize("headers,delay", [({"retry-after": "5.5"}, 7), ({}, 6)])
def test_shared_and_local_retry_deadlines_match(headers, delay):
    assert coordination.retry_delay(headers) == client.rate_limit_wait(headers) == delay


def test_annotation_race_cannot_restore_an_older_snapshot(monkeypatch):
    import time
    store = library.Library("owner")
    store.upsert(source())
    old_hash = store.get("t3_abc")["content_hash"]
    row_read, release = threading.Event(), threading.Event()
    original = store._row
    errors = []
    def paused_row(db, name):
        result = original(db, name)
        if threading.current_thread().name == "annotate":
            row_read.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(store, "_row", paused_row)
    def annotate():
        try:
            store.annotate("t3_abc", summary="Old summary", expected_hash=old_hash)
        except Exception as exc:
            errors.append(exc)
    first = threading.Thread(target=annotate, name="annotate")
    first.start()
    assert row_read.wait(3)
    second = threading.Thread(target=lambda: store.upsert(source(text="Replacement source")))
    second.start()
    time.sleep(.1)
    release.set()
    first.join(3)
    second.join(3)
    assert not first.is_alive() and not second.is_alive() and not errors
    result = store.get("t3_abc")
    assert result["body"] == "Replacement source"
    assert result["summary"] != "Old summary"


def test_inflight_refresh_cannot_restore_removed_or_edited_content():
    store = library.Library("owner")
    store.upsert(source())
    class Delayed:
        def info(self, names):
            store.remove("t3_abc")
            return {"data": {"children": [source()]}}
    assert library.refresh(Delayed(), store, ["t3_abc"])["skipped"] == 1
    assert store.search()["total"] == 0
    store.upsert(source())
    class Edited:
        def info(self, names):
            store.annotate("t3_abc", notes="new note")
            return {"data": {"children": [source(text="older response")]}}
    assert library.refresh(Edited(), store, ["t3_abc"])["skipped"] == 1
    assert store.get("t3_abc")["notes"] == "new note"


def test_logged_out_session_cannot_reuse_its_memory_token(monkeypatch):
    import time
    client.save_config({"client_id": "client", "client_secret": "secret"})
    client.save_token({"refresh_token": "refresh"})
    session = client.Reddit()
    session._access, session._expires_at = "old-access", time.time() + 3600
    client.clear_token()
    monkeypatch.setattr(client, "_post_form", lambda *a, **k: pytest.fail("logged-out session refreshed"))
    with pytest.raises(client.RedditError, match="logged out"):
        session.refresh()


def test_reset_auth_recovers_a_lost_key_and_preserves_bookmarks(home):
    client.save_config({"client_id": "client", "client_secret": "secret"})
    client.save_token({"refresh_token": "refresh"})
    library.Library("owner").upsert(source())
    (home / "plugin-data/reddit/storage-key.json").write_text("broken")
    assert client.reset_credentials()["library_preserved"]
    client.save_config({"client_id": "new", "client_secret": "new-secret"})
    assert client.load_config()["client_secret"] == "new-secret"
    assert library.Library("owner").search()["total"] == 1


def test_credential_patterns_in_errors_are_redacted():
    from reddit import redaction
    assert "secret-canary" not in redaction.safe("Basic secret-canary")
    assert "secret-canary" not in redaction.safe("access_token=secret-canary")


def test_settings_only_tool_call_works_offline_without_credentials(monkeypatch):
    monkeypatch.setattr(client, "validate_app", lambda *a: pytest.fail("settings requested network access"))
    assert json.loads(tools.reddit_setup({"background_refresh": True}))["ok"]
    assert client.load_config()["background_refresh"]


def test_maintenance_keeps_attempt_and_result_while_disabled(home):
    client.save_config({"background_refresh": True})
    initial = maintenance.run_once(home)
    assert initial["last_refresh_result"] == "login_required"
    client.save_config({"background_refresh": False})
    assert maintenance.run_once(home)["last_refresh_attempt"] == initial["last_refresh_attempt"]
    client.save_config({"background_refresh": True})
    state = maintenance.run_once(home)
    assert state["refresh"] == "not_due" and state["last_refresh_result"] == "login_required"


def test_literal_backslash_search_and_missing_rate_headers():
    store = library.Library("owner")
    store.upsert(source(text=r"A path C:\Users\foo"))
    assert store.search(r"C:\Users\foo")["total"] == 1
    session = client.Reddit(creds={"client_id": "x"}, token={})
    session.last_rate = {"X-Ratelimit-Remaining": "0", "X-Ratelimit-Reset": "120"}
    session._blocked_until = 0
    session._capture_rate({})
    assert session._blocked_until == 0
