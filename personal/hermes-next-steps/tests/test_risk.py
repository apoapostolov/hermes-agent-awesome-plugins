"""The risky pill: which options the classifier calls dangerous, and how it reaches the chips."""

from __future__ import annotations

import json
import unittest

import offers
import recommend
from chips import Pending, attach, handler


def answers(*pairs) -> str:
    """A classifier reply: (risky, safe) per option, in chip order."""
    out = {}
    for index, (risk, safe) in enumerate(pairs, start=1):
        out["q%d" % index] = {
            "label": recommend.SAFE if safe > risk else recommend.RISKY,
            "probabilities": {recommend.RISKY: risk, recommend.SAFE: safe},
        }
    return json.dumps({"ok": True, "answers": out})


def dispatcher(payload: str):
    def dispatch(name, args):
        return payload

    return dispatch


class QuestionTest(unittest.TestCase):
    def test_every_option_gets_its_own_question(self):
        questions = recommend.risk_questions(["Tag it", "Force-push it"])
        self.assertEqual(sorted(questions), ["q1", "q2"])
        self.assertEqual(set(questions["q1"]["criteria"]), {"risky", "safe"})
        self.assertIn("Option 1 of 2: Tag it", questions["q1"]["instructions"])

    def test_each_question_names_the_siblings(self):
        questions = recommend.risk_questions(["A", "B", "C"])
        self.assertIn("2 (B)", questions["q1"]["instructions"])
        self.assertIn("3 (C)", questions["q1"]["instructions"])

    def test_the_state_numbers_the_candidates(self):
        state = recommend.risk_state_for(["A", "B"], "Push the branch.")
        self.assertIn("Push the branch.", state)
        self.assertIn("1. A", state)


class PicksTest(unittest.TestCase):
    def picks(self, payload, options=("Safe step", "Force-push it", "Leave it")):
        return recommend.risky_picks(dispatcher(payload), list(options), "context")

    def test_a_clear_risk_is_marked(self):
        self.assertEqual(self.picks(answers((0.1, 0.9), (0.85, 0.15), (0.05, 0.95))), [2])

    def test_below_the_bar_marks_nothing(self):
        self.assertEqual(self.picks(answers((0.1, 0.9), (0.55, 0.45), (0.05, 0.95))), [])

    def test_a_split_verdict_marks_nothing(self):
        self.assertEqual(self.picks(answers((0.1, 0.9), (0.62, 0.62), (0.05, 0.95))), [])

    def test_several_can_be_risky(self):
        self.assertEqual(self.picks(answers((0.9, 0.1), (0.8, 0.2), (0.05, 0.95))), [1, 2])

    def test_no_classifier_marks_nothing(self):
        def broken(name, args):
            raise RuntimeError("no classifier")

        self.assertEqual(recommend.risky_picks(broken, ["A", "B"], ""), [])

    def test_a_single_option_is_not_asked(self):
        self.assertEqual(self.picks(answers((0.9, 0.1)), ["Only it"]), [])


class ToolTest(unittest.TestCase):
    def build(self, want=True, picks=(2,)):
        store = Pending()
        tool = handler(
            store,
            recommend_picks=lambda options, context: [],
            wants_recommend=lambda: False,
            risk_picks=lambda options, context: list(picks),
            wants_risk=lambda: want,
        )
        return store, tool

    def test_the_setting_on_marks_the_chips(self):
        store, tool = self.build()
        reply = tool({"options": ["Tag it", "Force-push it"], "recommend": False}, session_id="s1")
        self.assertEqual(store.take("s1")[4], "2")
        self.assertIn("risky 2", reply)

    def test_the_setting_off_marks_nothing(self):
        store, tool = self.build(want=False)
        tool({"options": ["Tag it", "Force-push it"], "recommend": False}, session_id="s1")
        self.assertEqual(store.take("s1")[4], "")

    def test_a_call_can_ask_for_the_pass_itself(self):
        store, tool = self.build(want=False)
        tool({"options": ["Tag it", "Force-push it"], "recommend": False, "risky": True}, session_id="s1")
        self.assertEqual(store.take("s1")[4], "2")

    def test_a_call_can_refuse_it(self):
        store, tool = self.build(want=True)
        tool({"options": ["Tag it", "Force-push it"], "recommend": False, "risky": False}, session_id="s1")
        self.assertEqual(store.take("s1")[4], "")

    def test_a_broken_classifier_costs_only_the_pill(self):
        store = Pending()

        def boom(options, context):
            raise RuntimeError("classifier down")

        tool = handler(
            store,
            recommend_picks=lambda options, context: [],
            wants_recommend=lambda: False,
            risk_picks=boom,
            wants_risk=lambda: True,
        )
        reply = tool({"options": ["Tag it", "Force-push it"], "recommend": False}, session_id="s1")
        self.assertIn("Chips registered", reply)
        self.assertEqual(store.take("s1")[4], "")

    def test_the_directive_carries_the_attribute(self):
        store, tool = self.build()
        tool({"options": ["Tag it", "Force-push it"], "recommend": False}, session_id="s1")
        out = attach("Done.", "s1", platform="desktop", pending=store)
        self.assertIn('risky="2"', out)


class AttributeTest(unittest.TestCase):
    def test_strip_removes_the_mark(self):
        text = '::nextsteps{risky="2" multi="1" q1="A" q2="B"}'
        self.assertEqual(offers.strip_risky(text), '::nextsteps{multi="1" q1="A" q2="B"}')

    def test_strip_leaves_no_double_space(self):
        text = '::nextsteps{sid="x" risky="1" multi="1" q1="A" q2="B"}'
        self.assertNotIn('  ', offers.strip_risky(text))

    def test_strip_leaves_other_attributes(self):
        text = '::nextsteps{alt="1,2" risky="1" rec="2" q1="A" q2="B"}'
        out = offers.strip_risky(text)
        self.assertNotIn("risky", out)
        self.assertIn('alt="1,2"', out)
        self.assertIn('rec="2"', out)

    def test_strip_leaves_prose_alone(self):
        self.assertEqual(offers.strip_risky("No chips here."), "No chips here.")


if __name__ == "__main__":
    unittest.main()
