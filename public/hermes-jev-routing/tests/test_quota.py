"""Quota floors skip a model whose remaining window is below the stricter floor."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import Analysis, AvailableModel, RouteTarget, RouterConfig, decide  # noqa: E402
from quota import codex_eligibility, quota_allows, stricter  # noqa: E402


class QuotaTests(unittest.TestCase):
    def test_stricter_floor_wins_and_equality_passes(self):
        floors = stricter({"fiveHour": 0.05}, {"weekly": 0.30, "fiveHour": 0.10})
        self.assertEqual(floors["fiveHour"], 0.10)
        self.assertTrue(quota_allows({"fiveHour": 0.10, "weekly": 0.30}, floors))
        self.assertFalse(quota_allows({"fiveHour": 0.09, "weekly": 0.30}, floors))

    def test_unknown_reading_follows_policy(self):
        self.assertTrue(quota_allows(None, {"weekly": 0.3}, "use"))
        self.assertFalse(quota_allows(None, {"weekly": 0.3}, "skip"))

    def test_low_weekly_skips_codex_and_keeps_the_next_model(self):
        config = RouterConfig(
            routes={
                "high": [
                    RouteTarget("openai-codex", "gpt-6-sol", min_quota={"weekly": 0.30}),
                    RouteTarget("xai-oauth", "grok-4.6"),
                ]
            },
            quota_floors={"openai-codex": {"fiveHour": 0.05, "weekly": 0.05}},
            quota_on_unknown={"openai-codex": "use"},
        )
        models = [
            AvailableModel("openai-codex", "gpt-6-sol"),
            AvailableModel("xai-oauth", "grok-4.6"),
        ]
        decision = decide(
            Analysis("implement", 2.2, 2.0, 0.8, 0.9),
            config,
            models,
            eligibility=codex_eligibility(config, {"fiveHour": 0.40, "weekly": 0.10}),
        )
        self.assertEqual(decision.target.model, "grok-4.6")
        self.assertTrue(any("skipped" in note for note in decision.notes))

    def test_stale_or_reset_reading_is_unknown(self):
        from quota import QuotaReading, QuotaSnapshot, evaluate_codex, parse_codex_payload

        target = RouteTarget("openai-codex", "gpt-6-luna", min_quota={"fiveHour": 0.05})
        stale = QuotaSnapshot(fetched_at=0, windows={"fiveHour": QuotaReading(0.9)})
        allowed, notes = evaluate_codex(
            target, enabled=True, floors={"fiveHour": 0.05}, on_unknown="use",
            ttl_sec=120, snapshot=stale, now_ms=200_000,
        )
        self.assertTrue(allowed)
        self.assertIn("unknown", notes[0])
        reset = QuotaSnapshot(fetched_at=1_000_000, windows={"fiveHour": QuotaReading(0.9, reset_at=500_000)})
        allowed, notes = evaluate_codex(
            target, enabled=True, floors={"fiveHour": 0.05}, on_unknown="skip",
            ttl_sec=120, snapshot=reset, now_ms=1_010_000,
        )
        self.assertFalse(allowed)
        parsed = parse_codex_payload(
            {"rate_limit": {"primary_window": {"limit_window_seconds": 18000, "used_percent": 20, "reset_at": 50}}},
            10_000,
        )
        self.assertAlmostEqual(parsed.windows["fiveHour"].remaining, 0.8)
        self.assertEqual(parsed.windows["fiveHour"].reset_at, 50_000)


if __name__ == "__main__":
    unittest.main()
