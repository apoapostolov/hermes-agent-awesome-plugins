"""The cache guard must hold for the right reason, with real prices."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import (  # noqa: E402
    Analysis,
    AvailableModel,
    Cache,
    RouteTarget,
    RouterConfig,
    decide,
)

CHEAP = {"input": 0.10, "output": 0.10, "cache_read": 0.01, "cache_write": 0.0}
PRICEY = {"input": 15.0, "output": 15.0, "cache_read": 1.5, "cache_write": 0.0}


def _config(cache=None):
    return RouterConfig(
        routes={
            "quick": (RouteTarget("p", "small"),),
            "standard": (RouteTarget("p", "mid"),),
            "high": (RouteTarget("p", "big"),),
            "premium": (),
            "xpremium": (),
        },
        cache=cache or Cache(aware=True, deadband=0.25, max_penalty_usd=0.05, bypass_tier_delta=2),
    )


MODELS = (
    AvailableModel("p", "small", CHEAP),
    AvailableModel("p", "mid", CHEAP),
    AvailableModel("p", "big", PRICEY),
)


class CacheBranchTests(unittest.TestCase):
    def test_a_priced_same_tier_swap_that_misses_the_cache_holds(self):
        """delta 0 and unaffordable: the warm cache wins. This needs a real cost."""
        config = _config()
        config.routes["standard"] = (RouteTarget("p", "big"), RouteTarget("p", "mid"))
        decision = decide(
            Analysis("implement", 1.0, 1.0, 0.0, 0.9),
            config,
            MODELS,
            current_index=1,
            current_model=MODELS[1],
            context_tokens=400_000,
        )
        self.assertEqual(decision.tier_index, 1)
        self.assertTrue(decision.held)
        self.assertIn("miss the cache", " ".join(decision.notes))

    def test_an_unpriced_model_never_holds(self):
        """No cost means penalty 0 means affordable. A guess must not block."""
        config = _config()
        config.routes["standard"] = (RouteTarget("p", "big"), RouteTarget("p", "mid"))
        unpriced = (AvailableModel("p", "mid"), AvailableModel("p", "big"))
        decision = decide(
            Analysis("implement", 1.0, 1.0, 0.0, 0.9),
            config,
            unpriced,
            current_index=1,
            current_model=unpriced[0],
            context_tokens=400_000,
        )
        self.assertFalse(decision.held)

    def test_demand_inside_the_current_band_holds_regardless_of_cost(self):
        decision = decide(
            Analysis("implement", 1.6, 1.6, 0.5, 0.9),
            _config(),
            MODELS,
            current_index=1,
            current_model=MODELS[1],
            context_tokens=50,
        )
        self.assertTrue(decision.held)
        self.assertIn("band", " ".join(decision.notes))

    def test_a_big_upgrade_out_of_the_band_pays_for_its_own_miss(self):
        decision = decide(
            Analysis("plan", 3.0, 3.0, 0.9, 0.9),
            _config(),
            MODELS,
            current_index=0,
            current_model=MODELS[0],
            context_tokens=400_000,
        )
        self.assertFalse(decision.held)
        self.assertEqual(decision.target.model, "big")

    def test_a_small_move_out_of_the_band_still_checks_the_price(self):
        decision = decide(
            Analysis("plan", 3.0, 3.0, 0.9, 0.9),
            _config(Cache(aware=True, deadband=0.25, max_penalty_usd=0.05, bypass_tier_delta=3)),
            MODELS,
            current_index=1,
            current_model=MODELS[1],
            context_tokens=400_000,
        )
        self.assertTrue(decision.held)
        self.assertIn("cache penalty", " ".join(decision.notes))


if __name__ == "__main__":
    unittest.main()
