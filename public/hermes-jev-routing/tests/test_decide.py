"""Lock the demand math."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import (  # noqa: E402
    Analysis,
    AvailableModel,
    Cache,
    FreePool,
    RouteTarget,
    RouterConfig,
    Spend,
    decide,
    js_round,
    same_provider_rewrite,
)


def _model(provider: str, model_id: str, input_cost: float = 1.0) -> AvailableModel:
    return AvailableModel(
        provider=provider,
        id=model_id,
        cost={"input": input_cost, "cache_read": input_cost * 0.1, "cache_write": 0},
    )


def _config(**overrides) -> RouterConfig:
    routes = {
        "quick": [RouteTarget("opencode-go", "space-bunny-free")],
        "standard": [RouteTarget("opencode-go", "deepseek-v4-flash")],
        "high": [RouteTarget("xai-oauth", "grok-4.6")],
        "premium": [RouteTarget("openai-codex", "gpt-6-sol")],
        "xpremium": [RouteTarget("openai-codex", "gpt-6-astra")],
    }
    routes.update(overrides.pop("routes", {}))
    base = RouterConfig(
        routes=routes,
        kind_models={
            "implement": [
                RouteTarget("opencode-go", "kimi-k3", min_tier="high", priority=0),
                RouteTarget("opencode-go", "space-bunny-free", min_tier="quick", priority=12),
            ]
        },
        kind_minimum_tier={"plan": "high", "implement": "standard", "chat": "quick"},
        free=FreePool(
            enabled=True,
            policy="fallback-only",
            pool=(RouteTarget("opencode-go", "space-bunny-free"),),
        ),
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _models() -> list[AvailableModel]:
    return [
        _model("opencode-go", "space-bunny-free", 0),
        _model("opencode-go", "deepseek-v4-flash", 0.5),
        _model("opencode-go", "kimi-k3", 2),
        _model("xai-oauth", "grok-4.6", 3),
        _model("openai-codex", "gpt-6-sol", 15),
        _model("openai-codex", "gpt-6-astra", 30),
    ]


class DecideTests(unittest.TestCase):
    def test_js_round_matches_half_up(self):
        self.assertEqual(js_round(2.5), 3)
        self.assertEqual(js_round(1.75), 2)

    def test_medium_implement_lands_on_high(self):
        decision = decide(
            Analysis("implement", 1.70, 1.55, 0.82, 0.9),
            _config(),
            _models(),
        )
        self.assertIsNotNone(decision)
        self.assertEqual(decision.desired_tier, "high")
        self.assertEqual(decision.target.model, "space-bunny-free")
        self.assertTrue(decision.kind_specialised)
        self.assertIn("free pool -> space-bunny-free", decision.notes)

    def test_priority_beats_closer_min_tier(self):
        decision = decide(
            Analysis("implement", 2.2, 2.0, 0.8, 0.9),
            _config(),
            _models(),
        )
        self.assertEqual(decision.target.model, "space-bunny-free")
        self.assertGreaterEqual(decision.tier_index, 2)

    def test_plan_floor_blocks_quick(self):
        decision = decide(
            Analysis("plan", 0.2, 0.2, 0.1, 0.9),
            _config(),
            _models(),
        )
        self.assertGreaterEqual(decision.tier_index, 2)
        self.assertTrue(any("floors at high" in note for note in decision.notes))

    def test_low_confidence_drops_to_standard(self):
        decision = decide(
            Analysis("implement", 1.70, 1.55, 0.82, 0.2),
            _config(
                free=FreePool(enabled=False, policy="fallback-only", pool=()),
                kind_models={},
            ),
            _models(),
        )
        self.assertTrue(decision.low_confidence_fallback)
        self.assertEqual(decision.tier, "standard")
        self.assertEqual(decision.target.model, "deepseek-v4-flash")

    def test_xpremium_needs_premium_demand_and_confidence(self):
        decision = decide(
            Analysis("plan", 3, 3, 0.9, 0.9),
            _config(),
            _models(),
        )
        self.assertEqual(decision.desired_tier, "xpremium")
        self.assertEqual(decision.target.provider, "openai-codex")

    def test_unsure_premium_does_not_open_xpremium(self):
        decision = decide(
            Analysis("plan", 3, 3, 0.9, 0.2),
            _config(),
            _models(),
        )
        self.assertNotEqual(decision.desired_tier, "xpremium")

    def test_hard_budget_caps_architectural_work_at_standard(self):
        decision = decide(
            Analysis("plan", 3, 3, 0.9, 0.9),
            _config(),
            _models(),
            Spend(pressure=0.95, today=9),
        )
        self.assertTrue(decision.downgraded)
        self.assertLessEqual(decision.tier_index, 1)

    def test_cache_hold_blocks_a_costly_lateral_swap(self):
        current = _model("opencode-go", "deepseek-v4-flash", 0.5)
        decision = decide(
            Analysis("chat", 1.0, 1.0, 0.3, 0.9),
            _config(
                routes={
                    "standard": [
                        RouteTarget("opencode-go", "kimi-k3"),
                        RouteTarget("opencode-go", "deepseek-v4-flash"),
                    ]
                },
                cache=Cache(aware=True, deadband=0.25, max_penalty_usd=0.0, bypass_tier_delta=2),
                free=FreePool(enabled=False, policy="fallback-only", pool=()),
                kind_models={},
            ),
            _models(),
            context_tokens=200_000,
            current_index=1,
            current_model=current,
        )
        self.assertTrue(decision.held)
        self.assertEqual(decision.target.model, "deepseek-v4-flash")

    def test_rewrite_stays_on_the_bound_provider(self):
        decision = decide(
            Analysis("plan", 3, 3, 0.9, 0.9),
            _config(free=FreePool(enabled=False, policy="fallback-only", pool=())),
            _models(),
        )
        self.assertIsNone(same_provider_rewrite({"model": "grok-4.7"}, decision, "opencode-go", "auto"))
        self.assertIsNone(same_provider_rewrite({"model": "grok-4.7"}, decision, "openai-codex", "shadow"))

    def test_rewrite_changes_model_inside_the_bound_provider(self):
        decision = decide(
            Analysis("chat", 0.2, 0.2, 0.1, 0.9),
            _config(free=FreePool(enabled=False, policy="fallback-only", pool=()), kind_models={}),
            _models(),
        )
        rewritten = same_provider_rewrite({"model": "grok-4.7"}, decision, "opencode-go", "auto")
        self.assertEqual(rewritten["model"], decision.target.model)
        self.assertEqual(decision.target.provider, "opencode-go")


if __name__ == "__main__":
    unittest.main()
