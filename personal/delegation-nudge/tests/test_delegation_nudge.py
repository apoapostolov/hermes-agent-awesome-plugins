"""Contract tests for the delegation-nudge middleware.

Dependency-free on purpose: the plugin host ships neither pytest nor a test
runner, so this runs with `python -m unittest discover -s tests -t .` from the
plugin directory. The middleware is driven with a fake context, exactly as the
host calls it.
"""

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def load_plugin(name="delegation_nudge_under_test"):
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN_DIR / "__init__.py", submodule_search_locations=[str(PLUGIN_DIR)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class FakeCtx:
    """Only what the plugin touches: config lookups and registrations."""

    def __init__(self, config=None):
        self.config = dict(config or {})
        self.middleware = {}
        self.hooks = {}

    def get_config(self, key, default=None):
        return self.config.get(key, default)

    def register_middleware(self, kind, callback):
        self.middleware[kind] = callback

    def register_hook(self, name, callback):
        self.hooks[name] = callback


def chat_payload(old_results=0, turn_results=0, delegated=False):
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "an earlier request"},
    ]
    for i in range(old_results):
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"o{i}", "function": {"name": "read_file", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"o{i}", "content": "old result"})
    messages.append({"role": "user", "content": "the current request"})
    for i in range(turn_results):
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": f"t{i}", "function": {"name": "terminal", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"t{i}", "content": "new result"})
    if delegated:
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": "d0", "function": {"name": "delegate_task", "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": "d0", "content": "dispatched"})
    return {"messages": messages, "model": "test-model"}


class NudgeTest(unittest.TestCase):
    def setUp(self):
        self._home = os.environ.get("HERMES_HOME")
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["HERMES_HOME"] = self._tmp.name

    def tearDown(self):
        if self._home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._home
        self._tmp.cleanup()

    def middleware(self, **config):
        self.ctx = FakeCtx({"threshold": 10, "escalate_at": 25, "repeat_after": 0, "enabled": True, **config})
        self.mod = load_plugin()
        self.mod.register(self.ctx)
        self.assertIn("llm_request", self.ctx.middleware)
        return self.ctx.middleware["llm_request"]

    def write_config(self, body):
        Path(self._tmp.name, "config.yaml").write_text(body, encoding="utf-8")

    def note(self, out):
        users = [m for m in out["request"]["messages"] if m.get("role") == "user"]
        return users[-1]["content"]

    # 1. tool results drive the count, not API rounds
    def test_counts_tool_results_not_loop_iterations(self):
        mw = self.middleware()
        payload = chat_payload(turn_results=9)
        self.assertIsNone(mw(request=payload, session_id="s", turn_id="t", api_call_count=99))
        self.assertIsNotNone(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t2", api_call_count=2))

    def test_silent_below_threshold(self):
        mw = self.middleware()
        self.assertIsNone(mw(request=chat_payload(turn_results=9), session_id="s", turn_id="t", api_call_count=9))

    def test_note_lands_on_the_current_user_message(self):
        mw = self.middleware()
        out = mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t", api_call_count=10)
        self.assertIsInstance(out, dict)
        content = self.note(out)
        self.assertIn("delegation check", content)
        older = [m for m in out["request"]["messages"] if m.get("role") == "user"][0]
        self.assertEqual("an earlier request", older["content"])

    def test_first_note_names_routes_and_asks_for_a_reason(self):
        mw = self.middleware()
        content = self.note(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t", api_call_count=10))
        self.assertIn("scan", content)
        self.assertIn("staying inline because", content)

    def test_routes_come_from_config(self):
        self.write_config(
            "delegation:\n"
            "  backends:\n"
            "    model_map:\n"
            "      options:\n"
            "        - name: scan\n"
            "          provider: opencode-go\n"
            "          model: hy4-flash-free\n"
            "          description: File sweeps and lookups. No judgment calls.\n"
            "        - name: deep\n"
            "          provider: opencode-go\n"
            "          model: deepseek-v4.1-flash\n"
            "          description: Hard debugging and design.\n"
        )
        mw = self.middleware()
        content = self.note(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t"))
        self.assertIn("scan (free) opencode-go/hy4-flash-free", content)
        self.assertIn("deep (cheap) opencode-go/deepseek-v4.1-flash", content)

    def test_routes_fall_back_when_config_is_absent(self):
        mw = self.middleware()
        content = self.note(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t"))
        self.assertIn("scan (free, file sweeps and lookups)", content)

    def test_tool_results_are_never_edited(self):
        mw = self.middleware()
        before = chat_payload(turn_results=10)
        out = mw(request=before, session_id="s", turn_id="t")
        tools_before = [m["content"] for m in before["messages"] if m.get("role") == "tool"]
        tools_after = [m["content"] for m in out["request"]["messages"] if m.get("role") == "tool"]
        self.assertEqual(tools_before, tools_after)

    def test_second_note_escalates_and_names_the_bill(self):
        mw = self.middleware()
        first = mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t")
        self.assertIn("delegation check]", self.note(first))
        second = mw(request=chat_payload(turn_results=26), session_id="s", turn_id="t")
        self.assertIsNotNone(second, "25 or more results should trigger the second note")
        self.assertIn("second call", self.note(second))
        self.assertIn("26 tool results", self.note(second))

    def test_never_more_than_two_notes(self):
        mw = self.middleware()
        mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t")
        mw(request=chat_payload(turn_results=26), session_id="s", turn_id="t")
        self.assertIsNone(mw(request=chat_payload(turn_results=90), session_id="s", turn_id="t"))

    def test_dispatch_silences_the_turn(self):
        mw = self.middleware()
        self.assertIsNone(mw(request=chat_payload(turn_results=3, delegated=True), session_id="s", turn_id="t"))
        self.assertIsNone(mw(request=chat_payload(turn_results=40), session_id="s", turn_id="t"))

    def test_counts_the_current_turn_not_the_history(self):
        mw = self.middleware()
        self.assertIsNone(mw(request=chat_payload(old_results=200, turn_results=2), session_id="s", turn_id="t"))
        self.assertIsNotNone(mw(request=chat_payload(old_results=200, turn_results=10), session_id="s", turn_id="t2"))

    def test_subagent_is_silent(self):
        mw = self.middleware()
        self.ctx.hooks["subagent_start"](session_id="child")
        self.assertIsNone(mw(request=chat_payload(turn_results=30), session_id="child", turn_id="t"))
        self.ctx.hooks["subagent_stop"](session_id="child")
        self.assertIsNotNone(mw(request=chat_payload(turn_results=30), session_id="child", turn_id="t2"))

    def test_disabled_switch(self):
        mw = self.middleware(enabled=False)
        self.assertIsNone(mw(request=chat_payload(turn_results=50), session_id="s", turn_id="t"))

    def test_repeat_after_rearms(self):
        mw = self.middleware(threshold=5, escalate_at=100, repeat_after=5)
        self.assertIsNotNone(mw(request=chat_payload(turn_results=5), session_id="s", turn_id="t"))
        self.assertIsNone(mw(request=chat_payload(turn_results=6), session_id="s", turn_id="t"))
        self.assertIsNotNone(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t"))

    def test_codex_input_shape(self):
        mw = self.middleware()
        items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "go"}]}]
        for i in range(10):
            items.append({"type": "function_call", "name": "read_file", "arguments": "{}"})
            items.append({"type": "function_call_output", "call_id": f"c{i}", "output": "ok"})
        out = mw(request={"input": items}, session_id="s", turn_id="t")
        self.assertIsNotNone(out)
        self.assertIn("delegation check", out["request"]["input"][0]["content"][-1]["text"])

    def test_multimodal_user_content_keeps_its_parts(self):
        mw = self.middleware()
        payload = chat_payload(turn_results=10)
        key = [i for i, m in enumerate(payload["messages"]) if m.get("role") == "user"][-1]
        payload["messages"][key]["content"] = [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ]
        out = mw(request=payload, session_id="s", turn_id="t")
        parts = out["request"]["messages"][key]["content"]
        self.assertEqual(3, len(parts))
        self.assertEqual("image_url", parts[1]["type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
