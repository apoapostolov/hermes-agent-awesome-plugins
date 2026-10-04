"""A confirm click picks a target without asking Jev."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from choice import parse_confirm_choice, target_for_choice  # noqa: E402
from decide import Decision, FreePool, RouteTarget, RouterConfig  # noqa: E402


def _config():
    return RouterConfig(
        routes={"premium": [RouteTarget("openai-codex", "gpt-6-sol", thinking_level="medium")]},
        free=FreePool(enabled=True, pool=(RouteTarget("opencode-go", "space-bunny-free", thinking_level="medium"),)),
    )


class ChoiceTests(unittest.TestCase):
    def test_free_is_the_first_pool_model(self):
        target = target_for_choice(_config(), "free")
        self.assertEqual((target.provider, target.model), ("opencode-go", "space-bunny-free"))

    def test_x_keeps_the_current_model(self):
        self.assertIsNone(target_for_choice(_config(), "x"))

    def test_yes_uses_the_previous_target(self):
        previous = Decision(
            desired_tier="premium",
            tier="premium",
            target=RouteTarget("openai-codex", "gpt-6-sol"),
            model=None,
            tier_index=3,
            demand_score=3,
            budget_pressure=0,
            downgraded=False,
            low_confidence_fallback=False,
            kind_specialised=False,
            held=True,
            reason="held",
            notes=(),
        )
        target = target_for_choice(_config(), "yes", previous)
        self.assertEqual(target.model, "gpt-6-sol")

    def test_plain_chat_is_not_a_choice(self):
        self.assertIsNone(parse_confirm_choice("click free"))
        self.assertEqual(parse_confirm_choice("jev-confirm:free"), "free")


if __name__ == "__main__":
    unittest.main()
