"""A held turn must stop the send and owe the prompt back."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hold import hold_for_approval  # noqa: E402


class FakeAgent:
    def __init__(self):
        self.steered = []
        self.interrupted = []
        self._interrupt_requested = False

    def steer(self, text):
        self.steered.append(text)
        return True

    def interrupt(self, message=None, **kwargs):
        self.interrupted.append(message)
        self._interrupt_requested = True
        return True


class ApprovalHoldTests(unittest.TestCase):
    def test_the_turn_stops_and_the_prompt_is_owed_back(self):
        agent = FakeAgent()
        self.assertTrue(hold_for_approval(agent, "refactor the parser", "confirm"))
        self.assertTrue(agent._interrupt_requested)
        self.assertEqual(agent.steered, ["refactor the parser"])

    def test_no_agent_or_no_prompt_is_a_miss(self):
        self.assertFalse(hold_for_approval(None, "x", "confirm"))
        self.assertFalse(hold_for_approval(FakeAgent(), "", "confirm"))


if __name__ == "__main__":
    unittest.main()
