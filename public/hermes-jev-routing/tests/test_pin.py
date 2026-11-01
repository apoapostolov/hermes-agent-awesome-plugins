"""The revert/approve pin path must keep a Responses reasoning object intact.

`on_llm_request` used to write the thinking level straight into whichever
reasoning field the request carried, so a Responses-style object became the
string ``"low"`` and lost its ``summary``. The plugin is loaded as a package
here because the pin path lives on the module that registers the hook.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN))


def _load_plugin():
    name = "hermes_jev_routing_under_test"
    spec = importlib.util.spec_from_file_location(
        name, PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


plugin = _load_plugin()


class PinTests(unittest.TestCase):
    def setUp(self):
        plugin._LAST.clear()
        plugin._LAST["mode"] = "shadow"
        plugin._SESSIONS.clear()

    def _pin(self, request, pin, provider="openai-codex"):
        plugin._LAST["pin"] = dict(pin)
        return plugin.on_llm_request(session_id="s1", provider=provider, request=request)

    def test_a_responses_object_keeps_its_summary(self):
        request = {"model": "gpt-6-astra", "reasoning": {"effort": "high", "summary": "auto"}}
        result = self._pin(
            request,
            {"provider": "openai-codex", "model": "gpt-6-luna", "thinking": "low"},
        )
        self.assertEqual(result["request"]["model"], "gpt-6-luna")
        self.assertEqual(result["request"]["reasoning"], {"effort": "low", "summary": "auto"})
        self.assertEqual(request["reasoning"], {"effort": "high", "summary": "auto"})

    def test_a_plain_string_field_still_takes_the_level(self):
        result = self._pin(
            {"model": "glm-5.3", "reasoning_effort": "low"},
            {"provider": "opencode-go", "model": "glm-5.3-flash", "thinking": "high"},
            provider="opencode-go",
        )
        self.assertEqual(result["request"]["reasoning_effort"], "high")

    def test_a_request_without_a_reasoning_field_is_left_alone(self):
        result = self._pin(
            {"model": "glm-5.3"},
            {"provider": "opencode-go", "model": "glm-5.3-flash", "thinking": "high"},
            provider="opencode-go",
        )
        self.assertEqual(result["request"], {"model": "glm-5.3-flash"})

    def test_the_pin_is_consumed_once(self):
        pin = {"provider": "opencode-go", "model": "glm-5.3-flash", "thinking": "high"}
        self._pin({"model": "glm-5.3"}, pin, provider="opencode-go")
        self.assertIsNone(
            plugin.on_llm_request(session_id="s1", provider="opencode-go", request={"model": "glm-5.3"})
        )


if __name__ == "__main__":
    unittest.main()
