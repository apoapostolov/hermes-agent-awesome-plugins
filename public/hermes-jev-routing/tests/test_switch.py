"""Catalog edition records a cross-provider pick and does not switch."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import Decision, RouteTarget  # noqa: E402
from switch import maybe_switch  # noqa: E402


def _decision(held=False):
    return Decision(
        desired_tier="high",
        tier="high",
        target=RouteTarget("openai-codex", "gpt-6-sol"),
        model=None,
        tier_index=2,
        demand_score=2,
        budget_pressure=0,
        downgraded=False,
        low_confidence_fallback=False,
        kind_specialised=False,
        held=held,
        reason="test",
        notes=(),
    )


class PublicSwitchTests(unittest.TestCase):
    def test_auto_records_missing_agent(self):
        self.assertEqual(maybe_switch(_decision(), "sess", "auto"), "missing-agent")

    def test_shadow_and_hold_skip(self):
        self.assertEqual(maybe_switch(_decision(), "sess", "shadow"), "skip")
        self.assertEqual(maybe_switch(_decision(held=True), "sess", "auto"), "skip")


if __name__ == "__main__":
    unittest.main()
