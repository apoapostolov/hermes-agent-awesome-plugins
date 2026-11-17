"""Contract tests for the delegation-nudge middleware.

Dependency-free on purpose: the plugin host ships neither pytest nor PyYAML, so
this runs with `python -m unittest discover -s personal/delegation-nudge/tests -t .`.
The middleware is driven with a fake context, exactly as the host calls it.
"""

import importlib.util
import sys
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
    def middleware(self, **config):
        self.ctx = FakeCtx({"threshold": 10, "repeat_after": 0, "enabled": True, **config})
        self.mod = load_plugin()
        self.mod.register(self.ctx)
        self.assertIn("llm_request", self.ctx.middleware)
        return self.ctx.middleware["llm_request"]

    def test_silent_below_threshold(self):
        mw = self.middleware()
        self.assertIsNone(mw(request=chat_payload(turn_results=9), session_id="s", turn_id="t", api_call_count=9))

    def test_note_lands_on_the_current_user_message(self):
        mw = self.middleware()
        out = mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t", api_call_count=10)
        self.assertIsInstance(out, dict)
        self.assertIn("request", out)
        users = [m for m in out["request"]["messages"] if m.get("role") == "user"]
        self.assertIn("delegation check", users[-1]["content"])
        self.assertIn("scan", users[-1]["content"])
        self.assertEqual("an earlier request", users[0]["content"])

    def test_tool_results_are_never_edited(self):
        mw = self.middleware()
        before = chat_payload(turn_results=10)
        out = mw(request=before, session_id="s", turn_id="t", api_call_count=10)
        tools_before = [m["content"] for m in before["messages"] if m.get("role") == "tool"]
        tools_after = [m["content"] for m in out["request"]["messages"] if m.get("role") == "tool"]
        self.assertEqual(tools_before, tools_after)

    def test_once_per_turn(self):
        mw = self.middleware()
        self.assertIsNotNone(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t1", api_call_count=10))
        self.assertIsNone(mw(request=chat_payload(turn_results=12), session_id="s", turn_id="t1", api_call_count=12))

    def test_dispatch_silences_the_turn(self):
        mw = self.middleware()
        self.assertIsNone(
            mw(request=chat_payload(turn_results=3, delegated=True), session_id="s", turn_id="t", api_call_count=4)
        )
        self.assertIsNone(mw(request=chat_payload(turn_results=40), session_id="s", turn_id="t", api_call_count=40))

    def test_counts_the_current_turn_not_the_history(self):
        mw = self.middleware()
        self.assertIsNone(
            mw(request=chat_payload(old_results=200, turn_results=2), session_id="s", turn_id="t", api_call_count=3)
        )
        out = mw(request=chat_payload(old_results=200, turn_results=2), session_id="s", turn_id="t2", api_call_count=10)
        self.assertIsNotNone(out)

    def test_subagent_is_silent(self):
        mw = self.middleware()
        self.ctx.hooks["subagent_start"](session_id="child")
        self.assertIsNone(mw(request=chat_payload(turn_results=30), session_id="child", turn_id="t"))
        self.ctx.hooks["subagent_stop"](session_id="child")
        self.assertIsNotNone(mw(request=chat_payload(turn_results=30), session_id="child", turn_id="t2"))

    def test_disabled_switch(self):
        mw = self.middleware(enabled=False)
        self.assertIsNone(mw(request=chat_payload(turn_results=50), session_id="s", turn_id="t", api_call_count=50))

    def test_repeat_after_rearms(self):
        mw = self.middleware(threshold=5, repeat_after=5)
        self.assertIsNotNone(mw(request=chat_payload(turn_results=5), session_id="s", turn_id="t", api_call_count=5))
        self.assertIsNone(mw(request=chat_payload(turn_results=6), session_id="s", turn_id="t", api_call_count=6))
        self.assertIsNotNone(mw(request=chat_payload(turn_results=10), session_id="s", turn_id="t", api_call_count=10))

    def test_codex_input_shape(self):
        mw = self.middleware()
        items = [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "go"}]}]
        for i in range(10):
            items.append({"type": "function_call", "name": "read_file", "arguments": "{}"})
            items.append({"type": "function_call_output", "call_id": f"c{i}", "output": "ok"})
        out = mw(request={"input": items}, session_id="s", turn_id="t", api_call_count=10)
        self.assertIsNotNone(out)
        self.assertIn("delegation check", out["request"]["input"][0]["content"][-1]["text"])

    def test_multimodal_user_content_keeps_its_parts(self):
        mw = self.middleware()
        payload = chat_payload(turn_results=10)
        payload["messages"][-1]["role"]  # sanity: last message is a tool result
        payload["messages"][1]["content"] = [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ]
        key = [i for i, m in enumerate(payload["messages"]) if m.get("role") == "user"][-1]
        payload["messages"][key]["content"] = [
            {"type": "text", "text": "look"},
            {"type": "image_url", "image_url": {"url": "x"}},
        ]
        out = mw(request=payload, session_id="s", turn_id="t", api_call_count=10)
        parts = out["request"]["messages"][key]["content"]
        self.assertEqual(2, len(parts) - 1)
        self.assertEqual("image_url", parts[1]["type"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
