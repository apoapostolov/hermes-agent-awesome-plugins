"""A prompt that must not re-route, and the context the judge needs."""

from __future__ import annotations

import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jev import build_state  # noqa: E402
from skip import should_skip  # noqa: E402


class SkipTests(unittest.TestCase):
    def test_empty_and_slash(self):
        self.assertEqual(should_skip("   "), "empty")
        self.assertEqual(should_skip("/jev-routing why"), "slash command")

    def test_acknowledgements_do_not_route(self):
        for word in ("yes", "ok", "Thanks!", "go ahead.", "ty"):
            self.assertEqual(should_skip(word), "acknowledgement", word)

    def test_a_short_turn_only_skips_when_history_exists(self):
        self.assertEqual(should_skip("do that", 12, has_history=True), "short continuation")
        self.assertIsNone(should_skip("do that", 12, has_history=False))

    def test_a_real_request_routes(self):
        self.assertIsNone(should_skip("find the flaky test and fix it", 12, has_history=True))


class StateTests(unittest.TestCase):
    def test_state_carries_cwd_context_and_spend(self):
        state = build_state(
            "refactor the parser",
            history="user: earlier",
            active_model="xai-oauth/grok-4.7",
            cwd="C:/git/monorepo",
            context_tokens=361081,
            spend={"today": 1.25, "month": 8.0, "pressure": 0.62, "daily_cap": 2.0, "monthly_cap": None},
        )
        self.assertEqual(state["environment"]["cwd"], "C:/git/monorepo")
        self.assertEqual(state["environment"]["context_tokens_used"], 361081)
        self.assertEqual(state["budget"]["spent_today_usd"], 1.25)
        self.assertEqual(state["budget"]["daily_cap_usd"], 2.0)
        self.assertIsNone(state["budget"]["monthly_cap_usd"])

    def test_absent_optionals_stay_null(self):
        state = build_state("hello", spend=None)
        self.assertIsNone(state["environment"]["cwd"])
        self.assertIsNone(state["environment"]["context_tokens_used"])
        self.assertEqual(state["budget"]["spent_today_usd"], 0)


if __name__ == "__main__":
    unittest.main()
