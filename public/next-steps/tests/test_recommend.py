"""The recommendation policy, against the classifier's real answer shape.

The fixtures are trimmed copies of live `nerve_assess` envelopes (jev-1.14.0 over
typesafe-system-one): one typed choice question per option, probabilities per label.
"""

from __future__ import annotations

import json
import unittest

import recommend

TAKE = recommend.TAKE_NOW


def envelope(*take_now: float, ok: bool = True) -> str:
    """A dispatch result with one q1..qN answer per probability."""
    answers = {}
    for index, probability in enumerate(take_now):
        rest = round((1.0 - probability) / 2, 3)
        answers["q%d" % (index + 1)] = {
            "choice": TAKE if probability >= 0.5 else recommend.LATER,
            "confidence": probability,
            "probabilities": {TAKE: probability, recommend.LATER: rest, recommend.SKIP: rest},
            "type": "choice",
        }
    return json.dumps({"answers": answers, "contract": "assess/v1", "ok": ok})


def dispatcher(result, log=None):
    def dispatch(name, args):
        if log is not None:
            log.append((name, args))
        if isinstance(result, Exception):
            raise result
        return result

    return dispatch


class QuestionsTest(unittest.TestCase):
    def test_one_typed_choice_per_option(self):
        questions = recommend.questions(["Push it", "Tag it"])
        self.assertEqual(sorted(questions), ["q1", "q2"])
        self.assertEqual(questions["q1"]["type"], "choice")
        self.assertEqual(sorted(questions["q1"]["criteria"]), sorted([TAKE, recommend.LATER, recommend.SKIP]))
        self.assertIn("Push it", questions["q1"]["instructions"])
        self.assertIn("Tag it", questions["q2"]["instructions"])

    def test_each_question_owns_its_criteria_copy(self):
        questions = recommend.questions(["A", "B"])
        questions["q1"]["criteria"][TAKE] = "edited"
        self.assertNotEqual(questions["q2"]["criteria"][TAKE], "edited")


class PicksTest(unittest.TestCase):
    def test_all_clearing_the_bar_still_leaves_one_out(self):
        # Recommending every option is not a recommendation: the weakest goes.
        answers = json.loads(envelope(0.81, 0.79, 0.77))["answers"]
        self.assertEqual(recommend.picks(answers, 3), [0, 1])

    def test_a_clear_winner_gets_one(self):
        answers = json.loads(envelope(0.91, 0.04, 0.04, 0.01))["answers"]
        self.assertEqual(recommend.picks(answers, 4), [0])

    def test_nothing_clears_the_bar(self):
        answers = json.loads(envelope(0.4, 0.35, 0.25))["answers"]
        self.assertEqual(recommend.picks(answers, 3), [])

    def test_the_cap_keeps_the_strongest_three(self):
        answers = json.loads(envelope(0.52, 0.9, 0.61, 0.88))["answers"]
        self.assertEqual(recommend.picks(answers, 4), [1, 2, 3])

    def test_missing_or_malformed_answers_are_skipped_not_guessed(self):
        answers = {"q1": {"probabilities": {TAKE: 0.9}}, "q2": {"probabilities": "nope"}, "q3": {}}
        self.assertEqual(recommend.picks(answers, 3), [0])
        self.assertEqual(recommend.picks({}, 3), [])
        self.assertEqual(recommend.picks(answers, 0), [])

    def test_a_boolean_is_not_a_probability(self):
        answers = {"q1": {"probabilities": {TAKE: True}}}
        self.assertEqual(recommend.picks(answers, 1), [])


class PayloadTest(unittest.TestCase):
    def test_the_state_numbers_the_candidates_and_states_the_rules(self):
        state = recommend.state_for(["Push it", "Tag it"])
        self.assertIn("1. Push it", state)
        self.assertIn("2. Tag it", state)
        self.assertIn("alternatives", state)
        self.assertIn("none of the others", state)

    def test_the_goal_leads_the_state(self):
        self.assertTrue(recommend.state_for(["A", "B"], "Apo asked for a review.").startswith("Apo asked"))

    def test_each_question_names_its_siblings(self):
        questions = recommend.questions(["Push it", "Tag it", "Wait"])
        self.assertIn("1 of 3", questions["q1"]["instructions"])
        self.assertIn("2 (Tag it)", questions["q1"]["instructions"])
        self.assertIn("3 (Wait)", questions["q1"]["instructions"])
        self.assertNotIn("1 (Push it)", questions["q1"]["instructions"])
        self.assertIn("Do not mark two alternatives both", questions["q1"]["instructions"])

    def test_only_a_none_option_gets_the_none_instruction(self):
        questions = recommend.questions(["Push it", "None of the above"])
        self.assertNotIn("means taking none of the others", questions["q1"]["instructions"])
        self.assertIn("means taking none of the others", questions["q2"]["instructions"])


class NoneOptionTest(unittest.TestCase):
    """Taking a step and taking no step cannot both be right."""

    def answers(self, *triples):
        out = {}
        for index, (take, later, skip) in enumerate(triples):
            out["q%d" % (index + 1)] = {
                "probabilities": {TAKE: take, recommend.LATER: later, recommend.SKIP: skip},
                "type": "choice",
            }
        return out

    def test_the_marker_covers_deferrals(self):
        for option in ("None of the above", "Do nothing", "Skip the tag", "Wait for review", "Leave it for tomorrow", "Not now"):
            self.assertTrue(recommend.is_none_option(option), option)
        for option in ("Push the branch", "Tag 1.0.3", "Open the PR"):
            self.assertFalse(recommend.is_none_option(option), option)

    def test_a_none_option_is_never_marked_beside_an_action(self):
        options = ["Push the branch", "Wait for review"]
        self.assertEqual(recommend.picks(self.answers((0.8, 0.1, 0.1), (0.7, 0.2, 0.1)), 2, options), [0])

    def test_the_same_pair_in_the_other_order(self):
        options = ["Wait for review", "Push the branch"]
        self.assertEqual(recommend.picks(self.answers((0.7, 0.2, 0.1), (0.8, 0.1, 0.1)), 2, options), [1])

    def test_the_none_option_wins_alone_when_it_is_preferred(self):
        options = ["Push the branch", "Wait for review"]
        self.assertEqual(recommend.picks(self.answers((0.6, 0.1, 0.3), (0.8, 0.1, 0.1)), 2, options), [1])

    def test_two_none_options_collapse_to_the_better_one(self):
        options = ["Wait for review", "None of the above"]
        self.assertEqual(recommend.picks(self.answers((0.9, 0.05, 0.05), (0.7, 0.2, 0.1)), 2, options), [0])

    def test_the_reply_says_why_the_none_option_stays_out(self):
        options = ["Push the branch", "Wait for review"]
        answers = self.answers((0.8, 0.1, 0.1), (0.7, 0.2, 0.1))
        text = recommend.reply(options, answers)
        self.assertIn('rec="1"', text)
        self.assertIn("means taking none of these", text)


class NeverEverythingTest(unittest.TestCase):
    def test_two_options_that_both_clear_the_bar_leave_one_out(self):
        answers = json.loads(envelope(0.9, 0.8))["answers"]
        self.assertEqual(recommend.picks(answers, 2), [0])

    def test_the_reply_says_why(self):
        answers = json.loads(envelope(0.9, 0.8))["answers"]
        self.assertIn("recommending all of them is not a recommendation", recommend.reply(["A", "B"], answers))

    def test_a_single_option_is_never_trimmed(self):
        answers = json.loads(envelope(0.9))["answers"]
        self.assertEqual(recommend.picks(answers, 1), [0])


class DominanceTest(unittest.TestCase):
    def test_a_tie_with_skip_is_not_recommended(self):
        answers = {"q1": {"probabilities": {TAKE: 0.5, recommend.LATER: 0.1, recommend.SKIP: 0.5}}}
        self.assertEqual(recommend.picks(answers, 1), [])

    def test_beating_both_by_a_hair_is_enough(self):
        answers = {"q1": {"probabilities": {TAKE: 0.52, recommend.LATER: 0.25, recommend.SKIP: 0.23}}}
        self.assertEqual(recommend.picks(answers, 1), [0])


class FeedbackTest(unittest.TestCase):
    """What the model reads when the classifier says no, or picks only the none option."""

    def test_a_refusal_reports_how_close_it_was(self):
        answers = json.loads(envelope(0.42, 0.2))["answers"]
        text = recommend.reply(["A", "B"], answers)
        self.assertIn("leave rec out", text)
        self.assertIn("The highest was 1 at 0.42", text)

    def test_a_refusal_with_no_answers_says_only_that(self):
        text = recommend.reply(["A", "B"], {})
        self.assertIn("leave rec out", text)
        self.assertNotIn("The highest was", text)

    def test_a_winning_none_option_is_explained(self):
        answers = {
            "q1": {"probabilities": {TAKE: 0.3, recommend.LATER: 0.2, recommend.SKIP: 0.5}},
            "q2": {"probabilities": {TAKE: 0.9, recommend.LATER: 0.05, recommend.SKIP: 0.05}},
        }
        text = recommend.reply(["Push the branch", "None of the above"], answers)
        self.assertIn('rec="2"', text)
        self.assertIn("is preferred over every other option", text)


class ReplyTest(unittest.TestCase):
    def test_the_attribute_is_ready_to_copy(self):
        answers = json.loads(envelope(0.81, 0.2, 0.77))["answers"]
        text = recommend.reply(["A", "B", "C"], answers)
        self.assertIn('rec="1,3"', text)
        self.assertIn("2 of 3", text)
        self.assertIn("0.81", text)

    def test_no_recommendation_says_so_plainly(self):
        answers = json.loads(envelope(0.3, 0.3))["answers"]
        self.assertIn("leave rec out", recommend.reply(["A", "B"], answers))


class RecommendTest(unittest.TestCase):
    def test_calls_the_classifier_with_the_options_and_context(self):
        log = []
        text = recommend.recommend(dispatcher(envelope(0.9, 0.2), log), ["Push it", "Tag it"], "Apo asked for a review.")
        self.assertEqual(log[0][0], "nerve_assess")
        self.assertTrue(log[0][1]["state"].startswith("Apo asked for a review."))
        self.assertIn("1. Push it", log[0][1]["state"])
        self.assertIn("2. Tag it", log[0][1]["state"])
        self.assertEqual(sorted(log[0][1]["questions"]), ["q1", "q2"])
        self.assertIn('rec="1"', text)

    def test_a_missing_classifier_falls_through_to_the_older_name(self):
        calls = []

        def dispatch(name, args):
            calls.append(name)
            if name == "nerve_assess":
                raise RuntimeError("unknown tool")
            return envelope(0.75, 0.4)

        text = recommend.recommend(dispatch, ["A", "B"])
        self.assertEqual(calls, ["nerve_assess", "jev_assess"])
        self.assertIn('rec="1"', text)

    def test_no_classifier_at_all_leaves_the_directive_alone(self):
        text = recommend.recommend(dispatcher(RuntimeError("no such tool")), ["A", "B"])
        self.assertIn("leave rec out", text)
        self.assertNotIn('rec="', text)

    def test_an_error_envelope_is_not_a_verdict(self):
        text = recommend.recommend(dispatcher(envelope(0.9, 0.9, ok=False)), ["A", "B"])
        self.assertIn("leave rec out", text)

    def test_junk_instead_of_json_is_ignored(self):
        self.assertIn("leave rec out", recommend.recommend(dispatcher("<html>502</html>"), ["A", "B"]))

    def test_two_options_are_the_floor(self):
        self.assertIn("at least two options", recommend.recommend(dispatcher(envelope(0.9)), ["Only one"]))


class HandlerTest(unittest.TestCase):
    def test_options_from_a_params_dict(self):
        handler = recommend.handler(dispatcher(envelope(0.9, 0.1)))
        self.assertIn('rec="1"', handler({"options": ["Push it", "Tag it"], "context": "reviewed a diff"}))

    def test_options_given_as_newline_text(self):
        # Two of three clear the bar: one turn carries both, which is the shape this
        # test is about (the newline split), not the trimming rule.
        handler = recommend.handler(dispatcher(envelope(0.9, 0.8, 0.1)))
        self.assertIn('rec="1,2"', handler({"options": "Push it\nTag it\nWait for review"}))

    def test_missing_options_answers_with_an_instruction(self):
        handler = recommend.handler(dispatcher(envelope(0.9, 0.9)))
        self.assertIn("options array", handler({}))

    def test_six_options_is_the_ceiling(self):
        log = []
        handler = recommend.handler(dispatcher(envelope(0.9, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2), log))
        handler({"options": ["A", "B", "C", "D", "E", "F", "G"]})
        self.assertEqual(len(log[0][1]["questions"]), recommend.MAX_OPTIONS)


if __name__ == "__main__":
    unittest.main()
