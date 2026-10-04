"""A withdrawn model loses the chain; an unknown provider keeps it."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import availability  # noqa: E402
from decide import AvailableModel  # noqa: E402


class FakeCatalogue:
    """Stands in for hermes_cli.models.cached_provider_model_ids."""

    def __init__(self, rows):
        self.rows = rows

    def __call__(self, provider, **kwargs):
        value = self.rows.get(provider)
        if isinstance(value, Exception):
            raise value
        return list(value or [])


class AvailabilityTests(unittest.TestCase):
    def setUp(self):
        availability.forget()
        self._real_reader = availability.read_ids

    def tearDown(self):
        availability.read_ids = self._real_reader
        availability.forget()

    def _stub(self, rows):
        availability.read_ids = lambda provider: list(rows.get(provider) or [])

    def _stub_raise(self, provider):
        def boom(_provider):
            raise RuntimeError("probe failed")

        availability.read_ids = boom

    def test_a_withdrawn_model_is_dropped(self):
        self._stub({"openai-codex": ["gpt-6-sol"]})
        kept = availability.live_models([
            AvailableModel("openai-codex", "gpt-6-luna"),
            AvailableModel("openai-codex", "gpt-6-sol"),
        ])
        self.assertEqual([(m.provider, m.id) for m in kept], [("openai-codex", "gpt-6-sol")])

    def test_an_unknown_provider_keeps_every_row(self):
        self._stub({})
        kept = availability.live_models([
            AvailableModel("opencode-go", "space-bunny-free"),
            AvailableModel("opencode-go", "longcat-2.5-preview-free"),
        ])
        self.assertEqual(len(kept), 2)

    def test_an_empty_catalogue_is_unknown_not_empty(self):
        self._stub({"openai-codex": []})
        kept = availability.live_models([AvailableModel("openai-codex", "gpt-6-sol")])
        self.assertEqual(len(kept), 1)

    def test_a_failed_probe_keeps_the_row(self):
        self._stub_raise("openai-codex")
        kept = availability.live_models([AvailableModel("openai-codex", "gpt-6-sol")])
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()
