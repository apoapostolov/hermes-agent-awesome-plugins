"""Config loader, Jev parse, and the turn action, with no network."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import load_router_config, models_from_config  # noqa: E402
from decide import Analysis  # noqa: E402
from jev import build_questions, classify, parse_analysis  # noqa: E402
from turn import route_turn  # noqa: E402

class LoaderTests(unittest.TestCase):
    def test_config_round_trip(self):
        raw = {
            "confidenceThreshold": 0.34,
            "minPromptChars": 12,
            "jevModel": "jev-latest",
            "routes": {
                "quick": [{"provider": "opencode-go", "model": "space-bunny-free", "thinkingLevel": "medium"}],
                "standard": [],
                "high": [{"provider": "xai-oauth", "model": "grok-4.6", "priority": 0}],
                "premium": [],
                "xpremium": [],
            },
            "kindModels": {
                "implement": [
                    {"provider": "opencode-go", "model": "space-bunny-free", "minTier": "quick", "priority": 12}
                ]
            },
            "kindMinimumTier": {"plan": "high"},
            "free": {"enabled": True, "policy": "fallback-only", "pool": [
                {"provider": "opencode-go", "model": "space-bunny-free"}
            ]},
            "cache": {"maxPenaltyUsd": 0, "bypassTierDelta": 2},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "router.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            config, settings = load_router_config(path)
        self.assertEqual(config.routes["quick"][0].thinking_level, "medium")
        self.assertEqual(config.kind_models["implement"][0].priority, 12)
        self.assertEqual(config.kind_minimum_tier["plan"], "high")
        self.assertEqual(config.cache.max_penalty_usd, 0)
        self.assertEqual(settings.jev_model, "jev-latest")
        self.assertTrue(any(model.id == "grok-4.6" for model in models_from_config(config)))


class JevTests(unittest.TestCase):
    def test_parse_rejects_an_unknown_kind(self):
        with self.assertRaises(Exception):
            parse_analysis({"answers": {"task_kind": {"choice": "nope", "confidence": 0.9}}}, {"chat": "talk"})

    def test_classify_posts_the_four_questions_and_hides_the_key(self):
        seen = {}

        def transport(url, headers, body, timeout_s):
            seen["url"] = url
            seen["auth"] = headers["Authorization"]
            seen["questions"] = set(body["questions"])
            seen["timeout"] = timeout_s
            return {"answers": {
                "task_kind": {"choice": "implement", "confidence": 0.8},
                "complexity": {"score": 1.7},
                "capability_deserved": {"score": 1.5},
                "needs_deep_reasoning": {"noul": 0.2},
            }}

        analysis = classify(
            "rename the helper",
            api_key="secret-key",
            endpoint="https://example.test/v1",
            jev_model="jev-latest",
            task_kinds={"implement": "code", "chat": "talk"},
            timeout_ms=3500,
            transport=transport,
        )
        self.assertEqual(analysis.kind, "implement")
        self.assertEqual(seen["questions"], {"task_kind", "complexity", "capability_deserved", "needs_deep_reasoning"})
        self.assertEqual(seen["auth"], "Bearer secret-key")
        self.assertNotIn("secret-key", json.dumps(build_questions({"implement": "code"})))
        self.assertEqual(seen["timeout"], 3.5)


class TurnTests(unittest.TestCase):
    def test_shadow_does_not_rewrite_across_providers(self):
        def fake(_prompt, _history):
            return Analysis("plan", 3, 3, 0.9, 0.9)

        raw = {
            "routes": {
                "quick": [{"provider": "opencode-go", "model": "space-bunny-free"}],
                "high": [{"provider": "xai-oauth", "model": "grok-4.6"}],
                "premium": [{"provider": "openai-codex", "model": "gpt-6-sol"}],
                "xpremium": [{"provider": "openai-codex", "model": "gpt-6-astra"}],
            },
            "kindMinimumTier": {"plan": "high"},
            "free": {"enabled": False, "policy": "fallback-only", "pool": []},
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "router.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            config, _settings = load_router_config(path)
        shadow = route_turn("plan the release carefully", config, classify=fake, bound_provider="opencode-go", mode="shadow")
        auto = route_turn("plan the release carefully", config, classify=fake, bound_provider="opencode-go", mode="auto")
        self.assertEqual(shadow.action, "shadow")
        self.assertEqual(auto.action, "switch")
        self.assertNotEqual(auto.decision.target.provider, "opencode-go")


if __name__ == "__main__":
    unittest.main()
