"""The cached-agent switch, with fake frames and no Hermes import."""

from __future__ import annotations

import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from decide import Decision, RouteTarget  # noqa: E402
from switch import apply_switch, find_live_agent, maybe_switch  # noqa: E402


class Frame:
    def __init__(self, locals_, back=None):
        self.f_locals = locals_
        self.f_back = back


class FakeAgent:
    def __init__(self, session_id, provider, model):
        self.session_id = session_id
        self.provider = provider
        self.model = model
        self.calls = []

    def switch_model(self, model, provider, api_key="", base_url="", api_mode="", capabilities=None):
        self.calls.append((model, provider))
        self.model = model
        self.provider = provider


def _decision(provider, model, held=False):
    return Decision(
        desired_tier="high",
        tier="high",
        target=RouteTarget(provider, model),
        model=None,
        tier_index=2,
        demand_score=2,
        budget_pressure=0,
        downgraded=False,
        low_confidence_fallback=False,
        kind_specialised=False,
        held=held,
        reason="test",
        notes=(),
    )


class SwitchTests(unittest.TestCase):
    def test_cache_lookup_beats_a_same_named_local(self):
        live = FakeAgent("sess-1", "opencode-go", "space-bunny-free")
        gateway = type("GW", (), {})()
        gateway._agent_cache = {"desktop:1": (live, "sig")}
        gateway._agent_cache_lock = threading.Lock()
        frames = {7: Frame({"self": gateway, "agent": FakeAgent("other", "xai-oauth", "grok-4.6")})}
        found = find_live_agent("sess-1", frames)
        self.assertIs(found, live)

    def test_stack_agent_when_there_is_no_cache(self):
        live = FakeAgent("sess-2", "xai-oauth", "grok-4.6")
        frames = {3: Frame({"agent": live})}
        self.assertIs(find_live_agent("sess-2", frames), live)

    def test_auto_switch_calls_switch_model_before_return(self):
        live = FakeAgent("sess-3", "opencode-go", "space-bunny-free")
        frames = {1: Frame({"agent": live})}
        result = maybe_switch(_decision("openai-codex", "gpt-6-sol"), "sess-3", "auto", frames)
        self.assertEqual(result, "switched")
        self.assertEqual(live.calls, [("gpt-6-sol", "openai-codex")])
        self.assertEqual(live.provider, "openai-codex")

    def test_shadow_and_hold_do_not_switch(self):
        live = FakeAgent("sess-4", "opencode-go", "space-bunny-free")
        frames = {1: Frame({"agent": live})}
        self.assertEqual(maybe_switch(_decision("openai-codex", "gpt-6-sol"), "sess-4", "shadow", frames), "skip")
        self.assertEqual(maybe_switch(_decision("openai-codex", "gpt-6-sol", held=True), "sess-4", "auto", frames), "skip")
        self.assertEqual(live.calls, [])

    def test_missing_agent_is_recorded_not_raised(self):
        self.assertEqual(maybe_switch(_decision("openai-codex", "gpt-6-sol"), "missing", "auto", {}), "missing-agent")

    def test_same_model_does_not_call_switch(self):
        live = FakeAgent("sess-5", "xai-oauth", "grok-4.6")
        self.assertEqual(apply_switch(live, _decision("xai-oauth", "grok-4.6")), "same")
        self.assertEqual(live.calls, [])

    def test_switch_sets_reasoning_effort_from_the_row(self):
        live = FakeAgent("sess-6", "opencode-go", "space-bunny-free")
        live.reasoning_config = {"enabled": True, "effort": "low"}
        decision = _decision("xai-oauth", "grok-4.6")
        decision = Decision(
            desired_tier=decision.desired_tier,
            tier=decision.tier,
            target=RouteTarget("xai-oauth", "grok-4.6", thinking_level="high"),
            model=decision.model,
            tier_index=decision.tier_index,
            demand_score=decision.demand_score,
            budget_pressure=decision.budget_pressure,
            downgraded=decision.downgraded,
            low_confidence_fallback=decision.low_confidence_fallback,
            kind_specialised=decision.kind_specialised,
            held=decision.held,
            reason=decision.reason,
            notes=decision.notes,
        )
        self.assertEqual(apply_switch(live, decision), "switched")
        self.assertEqual(live.reasoning_config, {"enabled": True, "effort": "high"})


if __name__ == "__main__":
    unittest.main()
