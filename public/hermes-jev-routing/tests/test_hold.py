"""Stickiness and the quota hold are decisions, not host luck."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import AvailableModel, RouteTarget  # noqa: E402
from hold import action_glyph, request_hold, should_hold_send, sticky_keep  # noqa: E402


class Config:
    stickiness = True


class HoldTests(unittest.TestCase):
    def test_stickiness_keeps_the_active_model(self):
        current = AvailableModel("xai-oauth", "grok-4.7")
        decision = type("D", (), {"target": RouteTarget("xai-oauth", "grok-4.7")})()
        self.assertTrue(sticky_keep(Config(), current, decision))
        self.assertFalse(sticky_keep(type("C", (), {"stickiness": False})(), current, decision))

    def test_an_ineligible_current_with_no_route_holds(self):
        current = AvailableModel("openai-codex", "gpt-6-sol")
        gate = lambda target, _model: target.provider != "openai-codex"
        self.assertTrue(should_hold_send(None, "skip", current, gate))
        self.assertFalse(should_hold_send(object(), "switched", current, gate))

    def test_request_hold_calls_interrupt_before_the_socket(self):
        seen = {}

        class Agent:
            def interrupt(self, message=None, **kwargs):
                seen["message"] = message
                return True

        self.assertTrue(request_hold(Agent(), "prompt not sent"))
        self.assertEqual(seen["message"], "prompt not sent")
        self.assertEqual(action_glyph(sticky=True, switched="skip", mode="auto"), "=")


if __name__ == "__main__":
    unittest.main()
