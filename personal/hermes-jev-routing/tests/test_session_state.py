"""A /jev-routing override belongs to the session that set it.

Run from the plugin directory: python tests/test_session_state.py
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1] / "__init__.py"
spec = importlib.util.spec_from_file_location("jev_session_plugin", PLUGIN)
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
assert spec.loader is not None
spec.loader.exec_module(plugin)


class FakeCtx:
    """The plugin's own settings reader: mode shadow, no JSON config path."""

    def __init__(self, mode: str = "shadow", path: str = "") -> None:
        self.mode = mode
        self.path = path

    def get_config(self, key, default=None):
        return {"mode": self.mode, "config_path": self.path}.get(key, default)


class SessionStateTests(unittest.TestCase):
    def setUp(self):
        plugin._SESSIONS.clear()
        plugin._LAST.clear()
        plugin._LAST.update({"mode": "shadow", "config_path": ""})
        plugin._CTX = FakeCtx()

    def tearDown(self):
        plugin._CTX = None
        plugin._SESSIONS.clear()

    def test_off_applies_only_to_its_own_session(self):
        self.assertIn("disabled", plugin._command("off", session_id="a"))
        plugin.on_pre_llm_call(session_id="a", user_message="")
        self.assertIs(plugin._LAST.get("enabled"), False)
        plugin.on_pre_llm_call(session_id="b", user_message="")
        self.assertNotIn("enabled", plugin._LAST)

    def test_mode_override_survives_the_next_config_read(self):
        plugin._command("mode notify", session_id="a")
        plugin.on_pre_llm_call(session_id="a", user_message="")
        self.assertEqual(plugin._LAST["mode"], "notify")
        # the same turn in another session reads the configured mode, not a's
        plugin.on_pre_llm_call(session_id="b", user_message="")
        self.assertEqual(plugin._LAST["mode"], "shadow")

    def test_why_reads_the_calling_sessions_prompt(self):
        plugin._SESSIONS["a"] = {"prompt": "prompt from session a"}
        plugin._SESSIONS["b"] = {"prompt": "prompt from session b"}
        original = plugin._dry_route
        plugin._dry_route = lambda text: f"dry:{text}"
        try:
            self.assertEqual(plugin._command("why", session_id="a"), "dry:prompt from session a")
            self.assertEqual(plugin._command("why", session_id="b"), "dry:prompt from session b")
        finally:
            plugin._dry_route = original

    def test_turn_facts_land_in_the_owning_session_only(self):
        plugin.on_pre_llm_call(session_id="a", user_message="")
        self.assertIn("prompt", plugin._SESSIONS["a"])
        self.assertNotIn("prompt", plugin._SESSIONS.get("b", {}))

    def test_session_delete_drops_overrides(self):
        plugin._command("off", session_id="a")
        plugin._command("mode auto", session_id="b")
        plugin.on_session_delete(session_id="a")
        self.assertNotIn("a", plugin._SESSIONS)
        self.assertIn("b", plugin._SESSIONS)
        plugin.on_session_delete(deleted_ids=["b"])
        self.assertNotIn("b", plugin._SESSIONS)

    def test_overrides_never_leak_into_the_turn_keys(self):
        plugin._command("mode auto", session_id="a")
        plugin.on_pre_llm_call(session_id="a", user_message="")
        # _mirror_turn must not copy mode back as a per-session pin
        plugin._SESSIONS["a"].pop("mode", None)
        plugin.on_pre_llm_call(session_id="a", user_message="")
        self.assertEqual(plugin._LAST["mode"], "shadow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
