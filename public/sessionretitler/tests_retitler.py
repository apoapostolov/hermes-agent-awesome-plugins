"""Local checks for sessionretitler: counting, digest, titles, claim ladder."""
from __future__ import annotations

import contextvars
import enum
import importlib.util
import os
import re
import sys
import threading
import types

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")
spec = importlib.util.spec_from_file_location("session_retitler_plugin", PLUGIN)
mod = importlib.util.module_from_spec(spec)
sys.modules["session_retitler_plugin"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


class _TitleSource(enum.Enum):
    """Stub of persistence.conversation.sessions.TitleSource (a plain Enum)."""

    DERIVED = "derived"
    LLM = "llm"
    USER = "user"


# The plugin imports TitleSource at module import time from the host; bind the
# stub when the host package is absent so the write paths are exercised.
if mod.TitleSource is None:
    mod.TitleSource = _TitleSource


def test_default_interval_is_ten():
    assert mod.DEFAULTS["interval"] == 10
    assert mod._cfg(_FakeCtx(), "interval") == 10


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


_RANK = {None: 0, _TitleSource.DERIVED: 1, _TitleSource.LLM: 2}


class _TitleConflict(ValueError):
    """A unique-title index collision, as core raises it (TitleConflict is a ValueError)."""


class _FakeSessions:
    """Store's own session repository, with the core's rank gate."""

    def __init__(self, source=None, title=None, refuse=(), conflicts=(), raise_on_source=False):
        self.source = source
        self.title = title
        self.refuse = set(refuse)
        self.conflicts = set(conflicts)
        self.raise_on_source = raise_on_source
        self.calls = []

    def get_title_source(self, sid):
        if self.raise_on_source:
            raise RuntimeError("title source unreadable")
        self.calls.append(("get_source",))
        return self.source

    def get_title(self, sid):
        return self.title

    def set_title_source(self, sid, source):
        self.calls.append(("title_source", source))
        self.source = source
        return True

    def set_auto_title(self, sid, title, *, source):
        self.calls.append(("auto", title, source))
        if source is _TitleSource.USER:
            raise ValueError("set_auto_title refuses TitleSource.USER")
        if title in self.conflicts:
            raise _TitleConflict(f"{title!r} is held by another session")
        if title in self.refuse:
            return False
        if self.source is _TitleSource.USER:
            return False
        if _RANK[self.source] >= _RANK[source]:
            return False
        self.title = title
        self.source = source
        return True

    def next_title_in_lineage(self, base_title):
        self.calls.append(("lineage", base_title))
        return f"{base_title} #2"


def test_write_llm_title_rank_ladder():
    # user titles are untouchable: no writes at all
    sessions = _FakeSessions(_TitleSource.USER, "My Own Name")
    assert mod._write_llm_title(sessions, "s", "New Name") is False
    assert sessions.calls == [("get_source",)]
    # derived upgrades straight through at llm rank
    sessions = _FakeSessions(_TitleSource.DERIVED, "Old Derived")
    assert mod._write_llm_title(sessions, "s", "New Name") is True
    assert sessions.calls == [("get_source",), ("auto", "New Name", _TitleSource.LLM)]
    assert sessions.title == "New Name" and sessions.source is _TitleSource.LLM
    # llm -> llm lowers to derived first so the rank-gated write does not no-op
    sessions = _FakeSessions(_TitleSource.LLM, "Old Name")
    assert mod._write_llm_title(sessions, "s", "New Name") is True
    assert sessions.calls == [
        ("get_source",),
        ("title_source", _TitleSource.DERIVED),
        ("auto", "New Name", _TitleSource.LLM),
    ]
    assert sessions.title == "New Name" and sessions.source is _TitleSource.LLM
    # a named row with no provenance ranks as user in core, so leave it alone
    sessions = _FakeSessions(None, "Legacy Name")
    assert mod._write_llm_title(sessions, "s", "New Name") is False
    assert sessions.calls == [("get_source",)]


def test_untitled_row_with_no_source_is_written():
    sessions = _FakeSessions(None, None)
    assert mod._write_llm_title(sessions, "s", "New Name") is True
    assert sessions.calls == [("get_source",), ("auto", "New Name", _TitleSource.LLM)]


def test_failed_rewrite_restores_the_previous_title():
    sessions = _FakeSessions(_TitleSource.LLM, "Old Name", refuse={"New Name"})
    assert mod._write_llm_title(sessions, "s", "New Name") is False
    # the value and its original llm provenance both come back
    assert sessions.title == "Old Name"
    assert sessions.source is _TitleSource.LLM
    assert sessions.calls == [
        ("get_source",),
        ("title_source", _TitleSource.DERIVED),
        ("auto", "New Name", _TitleSource.LLM),
        ("title_source", _TitleSource.LLM),
    ]


def test_title_collision_writes_the_deduped_name():
    sessions = _FakeSessions(_TitleSource.DERIVED, None, conflicts={"Same Name"})
    assert mod._write_llm_title(sessions, "s", "Same Name") is True
    assert sessions.title == "Same Name #2"
    assert sessions.calls == [
        ("get_source",),
        ("auto", "Same Name", _TitleSource.LLM),
        ("lineage", "Same Name"),
        ("auto", "Same Name #2", _TitleSource.LLM),
    ]


def test_unreadable_title_source_is_never_written_to():
    # Fail closed: a failed read must not look like "no user title".
    sessions = _FakeSessions(_TitleSource.DERIVED, None, raise_on_source=True)
    assert mod._write_llm_title(sessions, "s", "New Name") is False
    assert sessions.calls == []
    assert sessions.title is None


def test_missing_title_api_is_never_written_to():
    saved = mod.TitleSource
    mod.TitleSource = None
    try:
        sessions = _FakeSessions(_TitleSource.DERIVED, None)
        assert mod._write_llm_title(sessions, "s", "New Name") is False
        assert sessions.calls == []
    finally:
        mod.TitleSource = saved


class _Store:
    """Minimal persistence_assembly.Persistence context manager."""

    def __init__(self, sessions):
        self.sessions = sessions
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed = True
        return False


_MOD_TITLE_SOURCE = "mod.TitleSource"
_BLOCKED_MODULES = ("agent.title_generator", "hermes_state")


def _install_host_stubs(sessions):
    """Stub the host-only imports so _retitle runs standalone."""
    agent_pkg = types.ModuleType("agent")
    plugin_llm = types.ModuleType("agent.plugin_llm")

    class PluginLlmTextInput:
        def __init__(self, text):
            self.text = text

    plugin_llm.PluginLlmTextInput = PluginLlmTextInput
    agent_pkg.plugin_llm = plugin_llm

    persistence_pkg = types.ModuleType("persistence")
    conversation_pkg = types.ModuleType("persistence.conversation")
    sessions_mod = types.ModuleType("persistence.conversation.sessions")
    sessions_mod.TitleSource = _TitleSource
    persistence_pkg.conversation = conversation_pkg
    conversation_pkg.sessions = sessions_mod

    assembly = types.ModuleType("persistence_assembly")
    opened = {}

    def profile_scope(profile=None, *, home=None):
        return "scope:test"

    def open_persistence(scope, *, eager=False):
        opened["scope"] = scope
        return _Store(sessions)

    assembly.profile_scope = profile_scope
    assembly.open_persistence = open_persistence
    assembly.opened = opened

    stubs = {
        "agent": agent_pkg,
        "agent.plugin_llm": plugin_llm,
        "persistence": persistence_pkg,
        "persistence.conversation": conversation_pkg,
        "persistence.conversation.sessions": sessions_mod,
        "persistence_assembly": assembly,
    }
    old = {k: sys.modules.get(k) for k in stubs if k != _MOD_TITLE_SOURCE}
    old[_MOD_TITLE_SOURCE] = mod.TitleSource
    sys.modules.update({k: v for k, v in stubs.items() if k != _MOD_TITLE_SOURCE})
    for name in _BLOCKED_MODULES:
        sys.modules.pop(name, None)
    mod.TitleSource = _TitleSource
    return old


def _restore_modules(old):
    for k, v in old.items():
        if k == _MOD_TITLE_SOURCE:
            mod.TitleSource = v
            continue
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
    sessions = _FakeSessions(_TitleSource.DERIVED, None)
    old = _install_host_stubs(sessions)
    try:
        status = mod._retitle(_RetitleCtx(), "s-e2e", "USER: something\n\nASSISTANT: else")
        assert status == "ok"
        assert sessions.calls == [("get_source",), ("auto", "Fresh Session Name", _TitleSource.LLM)]
        assert sessions.title == "Fresh Session Name"
        assert sessions.source is _TitleSource.LLM
        # the write went through the store the plugin opened, at the active scope
        assert sys.modules["persistence_assembly"].opened["scope"] == "scope:test"
    finally:
        _restore_modules(old)


def test_retitle_reports_write_failure_and_empty_model():
    sessions = _FakeSessions(_TitleSource.DERIVED, None, refuse={"Fresh Session Name"})
    old = _install_host_stubs(sessions)
    try:
        assert mod._retitle(_RetitleCtx(), "s-fail", "USER: q\n\nASSISTANT: a") == "write_failed"
        assert sessions.title is None
    finally:
        _restore_modules(old)
    old = _install_host_stubs(_FakeSessions(_TitleSource.DERIVED, None))
    try:
        assert mod._retitle(_RetitleCtx(parsed={}), "s-empty", "USER: q") == "no_title"
    finally:
        _restore_modules(old)


def test_retitle_never_imports_private_core_modules():
    class _Blocked:
        def find_spec(self, name, path=None, target=None):
            if name in _BLOCKED_MODULES:
                raise AssertionError(f"plugin imported private module {name!r}")
            return None

    sentinel = _Blocked()
    sessions = _FakeSessions(_TitleSource.DERIVED, None)
    old = _install_host_stubs(sessions)
    sys.meta_path.insert(0, sentinel)
    try:
        assert mod._retitle(_RetitleCtx(), "s-clean", "USER: q\n\nASSISTANT: a") == "ok"
        assert sessions.title == "Fresh Session Name"
    finally:
        sys.meta_path.remove(sentinel)
        _restore_modules(old)


def test_machine_openers_classified_without_core_imports():
    # Item 4: no agent.title_generator, no hermes_state anywhere in sys.modules.
    for name in _BLOCKED_MODULES:
        assert name not in sys.modules, name
    assert mod._is_titleable_user_message("Fix the failing login test") is True
    assert mod._is_titleable_user_message("  [SYSTEM ignore me]  ") is False
    assert mod._is_titleable_user_message("<system>boot</system>") is False
    assert mod._is_titleable_user_message("[OUT-OF-BAND USER MESSAGE] hi") is False
    assert mod._is_titleable_user_message("[Tool result: ok]") is False
    assert mod._is_titleable_user_message("[CONTEXT COMPACTION 3]") is False
    assert mod._is_titleable_user_message("   ") is False
    assert mod._is_titleable_user_message(None) is False
    # counting still treats machine openers as non-titleable
    assert mod._extra_counts([], "[SYSTEM x]") is False
    assert mod._extra_counts([], "a real prompt") is True
    assert mod._is_real_user_message({"role": "user", "content": "[Runtime note: hi]"}) is False
    assert mod._is_real_user_message({"role": "user", "content": "a real prompt"}) is True
    assert mod._is_real_user_message({"role": "assistant", "content": "a real prompt"}) is False


def test_retitle_thread_runs_in_the_callers_context():
    marker = contextvars.ContextVar("sessionretitler_marker", default=None)
    marker.set("tenant-a")
    history = []
    for i in range(10):
        history.append({"role": "user", "content": f"question {i}"})
        history.append({"role": "assistant", "content": f"answer {i}"})

    captured = {}

    class _FakeThread:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            captured["started"] = True

    ctx = _FakeCtx()
    real_thread = threading.Thread
    threading.Thread = _FakeThread
    try:
        mod._maybe_retitle(ctx, "s-ctx", history, "question 10")
    finally:
        threading.Thread = real_thread

    assert captured.get("started") is True
    target = captured["target"]
    args = captured["args"]
    assert captured["daemon"] is True
    # the thread target is the captured context's run(), not the job itself
    assert target is not mod._retitle_and_release
    assert getattr(target, "__name__", "") == "run"
    assert isinstance(getattr(target, "__self__", None), contextvars.Context)
    assert len(args) == 5 and args[0] is mod._retitle_and_release
    assert args[1] is ctx and args[2] == "s-ctx"

    seen = {}

    def worker():
        seen["worker_own"] = marker.get()  # a fresh thread has no caller context

        def probe():
            seen["propagated"] = marker.get()

        target(probe)

    worker_thread = real_thread(target=worker, daemon=True)
    worker_thread.start()
    worker_thread.join(5)
    assert not worker_thread.is_alive()
    assert seen["worker_own"] is None
    assert seen["propagated"] == "tenant-a"
    mod._inflight.discard("s-ctx")
    marker.set(None)


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
    test_default_interval_is_ten()
    test_count_user_messages()
    test_clean_title_truncates_instead_of_dropping()
    test_digest_sees_boundary_message()
    test_digest_tail_cut_keeps_whole_blocks()
    test_pairs_gate_counts_line_anchors()
    test_record_claim_ladder()
    test_record_count_rebases_after_compaction()
    test_release_claim_gives_the_boundary_back()
    test_write_llm_title_rank_ladder()
    test_untitled_row_with_no_source_is_written()
    test_failed_rewrite_restores_the_previous_title()
    test_title_collision_writes_the_deduped_name()
    test_unreadable_title_source_is_never_written_to()
    test_missing_title_api_is_never_written_to()
    test_retitle_persists_cleaned_title()
    test_retitle_reports_write_failure_and_empty_model()
    test_retitle_never_imports_private_core_modules()
    test_machine_openers_classified_without_core_imports()
    test_retitle_thread_runs_in_the_callers_context()
    test_register_owns_auxiliary_task()
    print("ok")
