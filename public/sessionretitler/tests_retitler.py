"""Local checks for sessionretitler: counting, digest, titles, claim ladder."""
from __future__ import annotations

import importlib.util
import os
import re
import sys
import types

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")
spec = importlib.util.spec_from_file_location("session_retitler_plugin", PLUGIN)
mod = importlib.util.module_from_spec(spec)
sys.modules["session_retitler_plugin"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_count_user_messages():
    history = [
        {"role": "user", "content": "first real prompt"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "second real prompt"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "[SYSTEM ignore me]"},
    ]
    assert mod._count_user_messages(history) == 2
    assert mod._count_user_messages(history, "second real prompt") == 2
    assert mod._count_user_messages(history, "third real prompt") == 3
    assert mod._count_user_messages([], "hello there") == 1
    assert mod._count_user_messages([], "[SYSTEM x]") == 0


def test_clean_title_truncates_instead_of_dropping():
    long = "one two three four five six seven eight nine ten"
    assert mod._clean_title(long) == "one two three four five six seven eight"
    assert mod._clean_title("Title: Fresh Name Here") == "Fresh Name Here"
    assert mod._clean_title("  'Quoted Name'  ") == "Quoted Name"
    assert mod._clean_title("trailing dots...") == "trailing dots"
    assert mod._clean_title("hi") == "hi"
    assert mod._clean_title(None) is None
    assert mod._clean_title("") is None
    assert mod._clean_title("   ") is None


def test_digest_sees_boundary_message():
    history = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "reply one"},
    ]
    snap = mod.build_snapshot(history, "second question here")
    digest = mod.build_digest(snap, 20)
    assert digest.count("USER: ") == 2
    assert "second question here" in digest
    # machine extras and repeats never leak into the snapshot
    assert mod.build_snapshot(history, "[SYSTEM ignore me]") == history
    assert mod.build_snapshot(history, "first") == history
    # input history is never mutated
    assert len(history) == 2


def test_digest_tail_cut_keeps_whole_blocks():
    history = []
    for i in range(30):
        history.append({"role": "user", "content": f"question number {i} " + "x" * 400})
        history.append({"role": "assistant", "content": f"answer number {i} " + "y" * 400})
    digest = mod.build_digest(history, 30)
    assert len(digest) <= mod._DIGEST_CHARS
    assert digest.startswith("USER: ")
    assert all(chunk.startswith("USER: ") for chunk in digest.split("\n\n"))


def test_pairs_gate_counts_line_anchors():
    # A user message that mentions the marker mid-line is one exchange, not two.
    history = [
        {"role": "user", "content": "why does USER: appear in my transcript?"},
        {"role": "assistant", "content": "because the digest prints it"},
    ]
    digest = mod.build_digest(history, 20)
    assert digest.count("USER: ") == 2  # the inline mention plus the prefix
    assert len(re.findall(r"(?m)^USER: ", digest)) == 1


class _FakeState:
    def __init__(self):
        self.store = {}

    def get(self, key, default=None):
        return self.store.get(key, default)

    def set(self, key, value):
        self.store[key] = value


class _FakeCtx:
    def __init__(self):
        self.state = _FakeState()

    def get_config(self, key):
        return None


def test_record_claim_ladder():
    ctx = _FakeCtx()
    sid = "s-claim"
    try:
        assert mod._record_count(ctx, sid, 19, interval=20) == (None, False)
        entry = ctx.state.store["turn_counts"][sid]
        assert entry["n"] == 19 and entry["last_retitle_n"] == 0
        assert mod._record_count(ctx, sid, 20, claim=True, interval=20) == (0, True)
        assert ctx.state.store["turn_counts"][sid]["last_retitle_n"] == 20
        # the same count never claims twice, and one message past it is not due
        assert mod._record_count(ctx, sid, 20, claim=True, interval=20) == (None, False)
        mod._inflight.discard(sid)
        assert mod._record_count(ctx, sid, 21, claim=True, interval=20) == (None, False)
        entry = ctx.state.store["turn_counts"][sid]
        assert entry["n"] == 21 and entry["last_retitle_n"] == 20
        # a jump past the boundary still fires, where a modulo check would skip it
        assert mod._record_count(ctx, sid, 41, claim=True, interval=20) == (20, True)
    finally:
        mod._inflight.discard(sid)


def test_record_count_rebases_after_compaction():
    ctx = _FakeCtx()
    sid = "s-compact"
    try:
        assert mod._record_count(ctx, sid, 20, claim=True, interval=20) == (0, True)
        mod._inflight.discard(sid)
        # core compaction shrinks the retained history back to 6 messages
        mod._record_count(ctx, sid, 6, interval=20)
        assert ctx.state.store["turn_counts"][sid]["last_retitle_n"] == 6
        # the next interval fires from the rebased mark, not from a stale 20
        assert mod._record_count(ctx, sid, 26, claim=True, interval=20) == (6, True)
    finally:
        mod._inflight.discard(sid)


def test_release_claim_gives_the_boundary_back():
    ctx = _FakeCtx()
    sid = "s-release"
    try:
        mod._record_count(ctx, sid, 20, claim=True, interval=20)
        mod._release_claim(ctx, sid, 0)
        assert ctx.state.store["turn_counts"][sid]["last_retitle_n"] == 0
        assert ctx.state.store["turn_counts"][sid]["n"] == 20
        # a released boundary is claimable again on the next turn
        mod._inflight.discard(sid)
        assert mod._record_count(ctx, sid, 20, claim=True, interval=20) == (0, True)
    finally:
        mod._inflight.discard(sid)


class _FakeDB:
    def __init__(self, source, title=None):
        self.source = source
        self.title = title
        self.calls = []

    def get_session_title_source(self, sid):
        return self.source

    def get_session_title(self, sid):
        return self.title

    def set_session_title(self, sid, title):
        self.calls.append(("clear", title))
        self.title = title or None

    def set_auto_title(self, sid, title, source=None):
        self.calls.append(("auto", title, source))
        self.title = title
        return True


def test_write_llm_title_rank_ladder():
    # user titles are untouchable: no writes at all
    db = _FakeDB("user")
    assert mod._write_llm_title(db, "s", "New Name") is False
    assert db.calls == []
    # derived upgrades straight through
    db = _FakeDB("derived")
    assert mod._write_llm_title(db, "s", "New Name") is True
    assert db.calls == [("auto", "New Name", "llm")]
    # llm -> llm clears first so the rank-gated write does not no-op
    db = _FakeDB("llm", "Old Name")
    assert mod._write_llm_title(db, "s", "New Name") is True
    assert db.calls == [("clear", ""), ("auto", "New Name", "llm")]
    # a named row with no provenance ranks as user in core, so leave it alone
    db = _FakeDB(None, "Legacy Name")
    assert mod._write_llm_title(db, "s", "New Name") is False
    assert db.calls == []


class _FailingDB(_FakeDB):
    """Store that keeps the old name and refuses the new one."""

    def set_auto_title(self, sid, title, source=None):
        self.calls.append(("auto", title, source))
        if title == "New Name":
            return False
        self.title = title
        return True


def test_failed_rewrite_restores_the_previous_title():
    db = _FailingDB("llm", "Old Name")
    assert mod._write_llm_title(db, "s", "New Name") is False
    assert db.calls == [("clear", ""), ("auto", "New Name", "llm"), ("auto", "Old Name", "llm")]
    assert db.title == "Old Name"  # the session is never left untitled


def _install_host_stubs(captured, write_ok=True):
    """Stub the host-only imports so _retitle runs standalone."""
    agent_pkg = types.ModuleType("agent")
    title_gen = types.ModuleType("agent.title_generator")
    title_gen.is_titleable_user_message = lambda text: True
    plugin_llm = types.ModuleType("agent.plugin_llm")

    class PluginLlmTextInput:
        def __init__(self, text):
            self.text = text

    plugin_llm.PluginLlmTextInput = PluginLlmTextInput
    agent_pkg.title_generator = title_gen
    agent_pkg.plugin_llm = plugin_llm
    hermes_state = types.ModuleType("hermes_state")

    class SessionDB:
        def get_session_title_source(self, sid):
            return "derived"

        def get_session_title(self, sid):
            return None

        def set_auto_title(self, sid, title, source=None):
            if write_ok:
                captured.append((sid, title, source))
            return write_ok

        def close(self):
            pass

    hermes_state.SessionDB = SessionDB
    stubs = {
        "agent": agent_pkg,
        "agent.title_generator": title_gen,
        "agent.plugin_llm": plugin_llm,
        "hermes_state": hermes_state,
    }
    old = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    return old


def _restore_modules(old):
    for k, v in old.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


class _FakeLlm:
    def complete_structured(self, **kwargs):
        assert "USER:" in kwargs["input"][0].text
        assert kwargs["task"] == mod.AUX_TASK
        return types.SimpleNamespace(parsed={"title": "Topic: Fresh Session Name"})


class _RetitleCtx(_FakeCtx):
    def __init__(self, parsed=None):
        super().__init__()
        self.llm = _FakeLlm() if parsed is None else _EmptyLlm()


class _EmptyLlm:
    def complete_structured(self, **kwargs):
        return types.SimpleNamespace(parsed={})


def test_retitle_persists_cleaned_title():
    captured = []
    old = _install_host_stubs(captured)
    try:
        status = mod._retitle(_RetitleCtx(), "s-e2e", "USER: something\n\nASSISTANT: else")
        assert status == "ok"
        assert captured == [("s-e2e", "Fresh Session Name", "llm")]
    finally:
        _restore_modules(old)


def test_retitle_reports_write_failure_and_empty_model():
    captured = []
    old = _install_host_stubs(captured, write_ok=False)
    try:
        assert mod._retitle(_RetitleCtx(), "s-fail", "USER: q\n\nASSISTANT: a") == "write_failed"
    finally:
        _restore_modules(old)
    old = _install_host_stubs(captured)
    try:
        assert mod._retitle(_RetitleCtx(parsed={}), "s-empty", "USER: q") == "no_title"
    finally:
        _restore_modules(old)


def test_register_owns_auxiliary_task():
    captured = {}

    class Ctx(_FakeCtx):
        def register_hook(self, name, cb):
            captured.setdefault("hooks", []).append(name)

        def register_auxiliary_task(self, key, **kwargs):
            captured["aux"] = (key, kwargs)

    mod.register(Ctx())
    assert captured["hooks"] == ["pre_llm_call", "post_llm_call", "on_session_reset"]
    key, kwargs = captured["aux"]
    assert key == "sessionretitler_title"
    assert kwargs["inherit_from"] == "title_generation"
    assert kwargs["display_name"] == "Session title"


if __name__ == "__main__":
    test_count_user_messages()
    test_clean_title_truncates_instead_of_dropping()
    test_digest_sees_boundary_message()
    test_digest_tail_cut_keeps_whole_blocks()
    test_pairs_gate_counts_line_anchors()
    test_record_claim_ladder()
    test_record_count_rebases_after_compaction()
    test_release_claim_gives_the_boundary_back()
    test_write_llm_title_rank_ladder()
    test_failed_rewrite_restores_the_previous_title()
    test_retitle_persists_cleaned_title()
    test_retitle_reports_write_failure_and_empty_model()
    test_register_owns_auxiliary_task()
    print("ok")
