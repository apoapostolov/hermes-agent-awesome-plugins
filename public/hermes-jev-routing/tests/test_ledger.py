"""Ledger math, why text, and a dry-run that does not switch."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from commands import dry_run, explain, revert_target  # noqa: E402
from decide import Analysis, AvailableModel, Budget, RouteTarget, RouterConfig, Spend  # noqa: E402
from ledger import load_ledger, record_cost, save_ledger, spend_snapshot  # noqa: E402


class LedgerTests(unittest.TestCase):
    def test_pressure_uses_the_stricter_cap(self):
        ledger = {"days": {}, "months": {}, "jev": {}}
        now = datetime(2026, 10, 4, tzinfo=timezone.utc)
        record_cost(ledger, "openai-codex/gpt-6-sol", 0.8, now)
        snapshot = spend_snapshot(ledger, Budget(daily_usd=1.0, monthly_usd=10.0), now)
        self.assertEqual(snapshot.today, 0.8)
        self.assertEqual(snapshot.pressure, 0.8)

    def test_zero_cost_is_ignored_and_a_missing_file_is_empty(self):
        ledger = {"days": {}, "months": {}, "jev": {}}
        record_cost(ledger, "x", 0)
        self.assertEqual(ledger["days"], {})
        self.assertEqual(load_ledger(Path("missing-ledger.json"))["version"], 1)

    def test_a_reported_total_is_kept(self):
        from ledger import usage_cost
        self.assertEqual(usage_cost({"cost": {"total": 0.42}}), 0.42)
        self.assertEqual(usage_cost({}), 0.0)
        path = Path(__file__).with_name("_ledger.json")
        ledger = {"version": 1, "days": {}, "months": {}, "jev": {"requests": 0, "inputTokens": 0, "outputTokens": 0}}
        record_cost(ledger, "a/b", 0.125, datetime(2026, 10, 4, tzinfo=timezone.utc))
        save_ledger(path, ledger)
        loaded = load_ledger(path)
        path.unlink()
        self.assertEqual(loaded["days"]["2026-10-04"]["total"], 0.125)


class CommandTests(unittest.TestCase):
    def test_why_uses_the_stored_judgment(self):
        text = explain(Analysis("implement", 2.0, 1.0, 0.2, 0.8), None)
        self.assertIn("kind: implement", text)
        self.assertIn("no route available", text)

    def test_dry_run_does_not_need_a_switch(self):
        config = RouterConfig(
            routes={"quick": (RouteTarget("opencode-go", "space-bunny-free"),)},
            budget=Budget(daily_usd=1.0),
        )
        text = dry_run(
            Analysis("chat", 0.2, 0.2, 0.0),
            config,
            (AvailableModel("opencode-go", "space-bunny-free"),),
            spend=Spend(pressure=0.95),
        )
        self.assertIn("quick", text)

    def test_revert_needs_a_recorded_model(self):
        self.assertIsNone(revert_target(None))
        target = revert_target({"provider": "xai-oauth", "model": "grok-4.7"})
        self.assertEqual((target.provider, target.model), ("xai-oauth", "grok-4.7"))


if __name__ == "__main__":
    unittest.main()
