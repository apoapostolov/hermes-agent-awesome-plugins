"""A set plugin setting replaces the JSON value. An unset key leaves the file alone."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dataclasses import dataclass  # noqa: E402

from decide import Cache, FreePool, RouterConfig  # noqa: E402
from settings_override import apply_setting_overrides  # noqa: E402


@dataclass
class Settings:
    timeout_ms: int = 3500
    history_turns: int = 4


class OverrideTests(unittest.TestCase):
    def test_unset_keys_do_not_clobber_the_file(self):
        config = RouterConfig(routes={}, confidence_threshold=0.4, confirm_tiers=("premium",))
        settings = Settings()
        apply_setting_overrides(config, settings, {})
        self.assertEqual(config.confidence_threshold, 0.4)
        self.assertEqual(config.confirm_tiers, ("premium",))
        self.assertEqual(settings.timeout_ms, 3500)

    def test_a_set_threshold_replaces_the_file(self):
        config = RouterConfig(routes={}, confidence_threshold=0.4, free=FreePool(enabled=True, policy="fallback-only"))
        settings = Settings()
        apply_setting_overrides(
            config,
            settings,
            {"confidence_threshold": 0.2, "free_policy": "prefer", "timeout_ms": 8000},
        )
        self.assertEqual(config.confidence_threshold, 0.2)
        self.assertEqual(config.free.policy, "prefer")
        self.assertTrue(config.free.enabled)
        self.assertEqual(settings.timeout_ms, 8000)
        self.assertIsInstance(config.cache, Cache)


if __name__ == "__main__":
    unittest.main()
