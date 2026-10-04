"""The Jev line is for the turn that was just sent. The strip only interrupts a model change."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import AvailableModel, Decision, FreePool, RouteTarget, RouterConfig  # noqa: E402
from notice import format_jev_line, should_interrupt  # noqa: E402


def _decision(provider="openai-codex", model="gpt-6-sol", tier="premium"):
    return Decision(
        desired_tier=tier,
        tier=tier,
        target=RouteTarget(provider, model, thinking_level="medium"),
        model=None,
        tier_index=3,
        demand_score=2.8,
        budget_pressure=0,
        downgraded=False,
        low_confidence_fallback=False,
        kind_specialised=False,
        held=False,
        reason="implement",
        notes=(),
    )


class NoticeTests(unittest.TestCase):
    def test_line_carries_tier_model_thinking_and_reason(self):
        self.assertEqual(
            format_jev_line(_decision()),
            "premium · openai-codex/gpt-6-sol · medium · implement",
        )

    def test_same_model_does_not_interrupt(self):
        decision = _decision()
        current = AvailableModel("openai-codex", "gpt-6-sol")
        self.assertFalse(should_interrupt(decision, current, ("premium",)))

    def test_a_guarded_model_change_interrupts(self):
        decision = _decision()
        current = AvailableModel("xai-oauth", "grok-4.7")
        self.assertTrue(should_interrupt(decision, current, ("premium", "xpremium")))
        self.assertFalse(should_interrupt(decision, current, ()))


if __name__ == "__main__":
    unittest.main()
