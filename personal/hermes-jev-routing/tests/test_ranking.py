"""Score proposals stay off the hand table until a tier is missing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ranking import ScoreEntry, Scores, spread_by_provider, suggest_routes  # noqa: E402


class RankingTests(unittest.TestCase):
    def test_spread_avoids_a_repeat_when_another_provider_fits(self):
        chain = [
            {"provider": "a", "model": "1"},
            {"provider": "a", "model": "2"},
            {"provider": "b", "model": "3"},
        ]
        spread = spread_by_provider(chain)
        self.assertNotEqual(spread[0]["provider"], spread[1]["provider"])

    def test_suggest_skips_unknown_models_and_ranks_by_value(self):
        scores = Scores(
            models={
                "openai-codex/gpt-6-sol": ScoreEntry(0.9, {"implement": 0.95}, {"input": 5, "output": 15}),
                "xai-oauth/grok-4.6": ScoreEntry(0.8, {"implement": 0.7}, {"input": 1, "output": 1}),
                "missing/nope": ScoreEntry(0.99, {}),
            }
        )
        result = suggest_routes(
            task_kinds=["implement"],
            models=[("openai-codex", "gpt-6-sol"), ("xai-oauth", "grok-4.6")],
            scores=scores,
            spread=False,
        )
        self.assertEqual(result["routes"]["premium"][0]["model"], "gpt-6-sol")
        self.assertEqual(result["routes"]["high"][0]["model"], "grok-4.6")
        self.assertEqual(result["unmatched"], ["missing/nope"])
        self.assertEqual(result["kindModels"]["implement"][0]["model"], "grok-4.6")
        self.assertEqual(result["kindModels"]["implement"][0]["priority"], 2)

    def test_hand_chain_wins_over_generated(self):
        import json
        import tempfile
        from config import fill_from_generated

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            hand = root / "hermes-jev-routing.json"
            generated = root / "hermes-jev-routing.generated.json"
            hand.write_text(json.dumps({"routes": {"high": [{"provider": "xai-oauth", "model": "grok-4.6"}]}}), encoding="utf-8")
            generated.write_text(
                json.dumps({
                    "routes": {
                        "high": [{"provider": "openai-codex", "model": "gpt-6-sol"}],
                        "quick": [{"provider": "opencode-go", "model": "space-bunny-free"}],
                        "xpremium": [{"provider": "openai-codex", "model": "gpt-6-astra"}],
                    }
                }),
                encoding="utf-8",
            )
            merged = fill_from_generated(json.loads(hand.read_text(encoding="utf-8")), hand)
            self.assertEqual(merged["routes"]["high"][0]["model"], "grok-4.6")
            self.assertEqual(merged["routes"]["quick"][0]["model"], "space-bunny-free")
            self.assertNotIn("xpremium", merged["routes"])


if __name__ == "__main__":
    unittest.main()
