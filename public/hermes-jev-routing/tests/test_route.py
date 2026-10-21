"""Request-level routing: what the catalog edition may change, and what it may not."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import AvailableModel, Decision, RouteTarget, RouterConfig  # noqa: E402
from route import (  # noqa: E402
    BoundModel,
    action_glyph,
    crosses_provider,
    current_from,
    rewrite,
    sticky_keep,
    tier_index_for,
)


def _decision(provider="opencode-go", model="glm-5.3", thinking="high", tier="standard"):
    return Decision(
        desired_tier=tier,
        tier=tier,
        target=RouteTarget(provider, model, thinking_level=thinking),
        model=AvailableModel(provider, model),
        tier_index=1,
        demand_score=1.6,
        budget_pressure=0,
        downgraded=False,
        low_confidence_fallback=False,
        kind_specialised=False,
        held=False,
        reason="implement",
        notes=(),
    )


def _config():
    return RouterConfig(
        routes={
            "quick": (RouteTarget("opencode-go", "glm-5.3-flash"),),
            "standard": (RouteTarget("opencode-go", "glm-5.3"),),
            "high": (),
            "premium": (),
            "xpremium": (),
        },
        kind_models={},
        kind_minimum_tier={},
    )


class RewriteTests(unittest.TestCase):
    def test_same_provider_rewrites_the_model(self):
        updated = rewrite({"model": "glm-5.3-flash"}, _decision(), "opencode-go", "auto")
        self.assertEqual(updated["model"], "glm-5.3")

    def test_cross_provider_is_not_rewritten(self):
        decision = _decision(provider="openai-codex", model="gpt-6-sol")
        self.assertIsNone(rewrite({"model": "glm-5.3"}, decision, "opencode-go", "auto"))
        self.assertTrue(crosses_provider(decision, "opencode-go"))

    def test_shadow_and_held_never_rewrite(self):
        self.assertIsNone(rewrite({"model": "x"}, _decision(), "opencode-go", "shadow"))
        self.assertIsNone(rewrite({"model": "x"}, None, "opencode-go", "auto"))

    def test_reasoning_only_lands_on_a_field_the_request_has(self):
        plain = rewrite({"model": "glm-5.3-flash"}, _decision(), "opencode-go", "auto")
        self.assertNotIn("reasoning_effort", plain)
        wire = rewrite(
            {"model": "glm-5.3-flash", "reasoning_effort": "low"}, _decision(), "opencode-go", "auto"
        )
        self.assertEqual(wire["reasoning_effort"], "high")

    def test_already_on_the_pick_reports_nothing(self):
        self.assertIsNone(rewrite({"model": "glm-5.3"}, _decision(), "opencode-go", "auto"))
        self.assertIsNone(
            rewrite({"model": "glm-5.3", "reasoning_effort": "high"}, _decision(), "opencode-go", "auto")
        )

    def test_a_reasoning_change_alone_still_rewrites(self):
        updated = rewrite(
            {"model": "glm-5.3", "reasoning_effort": "low"}, _decision(), "opencode-go", "auto"
        )
        self.assertEqual(updated["reasoning_effort"], "high")

    def test_the_original_request_is_not_mutated(self):
        request = {"model": "glm-5.3-flash"}
        rewrite(request, _decision(), "opencode-go", "auto")
        self.assertEqual(request["model"], "glm-5.3-flash")


class BoundModelTests(unittest.TestCase):
    def test_hook_payload_gives_the_model_but_not_the_provider(self):
        current = current_from({"model": "glm-5.3"})
        self.assertEqual(current, BoundModel(provider="", id="glm-5.3"))
        self.assertIsNone(current_from({}))

    def test_unknown_provider_still_matches_the_model_for_stickiness(self):
        config = _config()
        decision = _decision(provider="opencode-go", model="glm-5.3")
        self.assertTrue(sticky_keep(config, BoundModel("", "glm-5.3"), decision))
        self.assertFalse(sticky_keep(config, BoundModel("", "glm-5.3-flash"), decision))

    def test_tier_index_falls_back_to_the_model_when_the_provider_is_unknown(self):
        config = _config()
        self.assertEqual(tier_index_for(config, "", "glm-5.3"), 1)
        self.assertEqual(tier_index_for(config, "opencode-go", "glm-5.3"), 1)
        self.assertIsNone(tier_index_for(config, "", "nope"))


class GlyphTests(unittest.TestCase):
    def test_glyphs_are_distinct_per_outcome(self):
        self.assertEqual(action_glyph(sticky=True, status="same", mode="auto"), "=")
        self.assertEqual(action_glyph(sticky=False, status="applied", mode="auto"), ">")
        self.assertEqual(action_glyph(sticky=False, status="offered", mode="notify"), ".")
        self.assertEqual(action_glyph(sticky=False, status="offered", mode="auto"), "x")


if __name__ == "__main__":
    unittest.main()
