"""Local checks for session-retitler: counting, digest, titles, claim ladder."""
from __future__ import annotations

import importlib.util
import os
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
    try:
        assert mod._record_count(ctx, "s-claim", 19) is False
        entry = ctx.state.store["turn_counts"]["s-claim"]
        assert entry["n"] == 19 and entry["last_retitle_n"] == 0
        assert mod._record_count(ctx, "s-claim", 20, claim=True) is True
        assert mod._record_count(ctx, "s-claim", 20, claim=True) is False
        assert mod._record_count(ctx, "s-claim", 21) is False
        entry = ctx.state.store["turn_counts"]["s-claim"]
        assert entry["n"] == 21 and entry["last_retitle_n"] == 20
    finally:
        mod._inflight.discard("s-claim")


class _FakeDB:
    def __init__(self, source):
        self.source = source
        self.calls = []

    def get_session_title_source(self, sid):
        return self.source

    def set_session_title(self, sid, title):
        self.calls.append(("clear", title))

    def set_auto_title(self, sid, title, source=None):
        self.calls.append(("auto", title, source))
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
    db = _FakeDB("llm")
    assert mod._write_llm_title(db, "s", "New Name") is True
    assert db.calls == [("clear", ""), ("auto", "New Name", "llm")]


def _install_host_stubs(captured):
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

        def set_auto_title(self, sid, title, source=None):
            captured.append((sid, title, source))
            return True

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


def test_retitle_persists_cleaned_title():
    captured = []
    old = _install_host_stubs(captured)

    class FakeLlm:
        def complete_structured(self, **kwargs):
            assert "USER:" in kwargs["input"][0].text
            return types.SimpleNamespace(parsed={"title": "Topic: Fresh Session Name"})

    class Ctx(_FakeCtx):
        def __init__(self):
            super().__init__()
            self.llm = FakeLlm()

    try:
        mod._retitle(Ctx(), "s-e2e", "USER: something\n\nASSISTANT: else")
        assert captured == [("s-e2e", "Fresh Session Name", "llm")]
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


if __name__ == "__main__":
    test_count_user_messages()
    test_clean_title_truncates_instead_of_dropping()
    test_digest_sees_boundary_message()
    test_digest_tail_cut_keeps_whole_blocks()
    test_record_claim_ladder()
    test_write_llm_title_rank_ladder()
    test_retitle_persists_cleaned_title()
    print("ok")
