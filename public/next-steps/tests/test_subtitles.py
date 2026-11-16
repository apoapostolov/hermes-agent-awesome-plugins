"""A chip's second line: where it comes from, and what survives the trip."""

from __future__ import annotations

import unittest

import offers
import recommend
from chips import Pending, attach, handler


class ParseTest(unittest.TestCase):
    def test_d_attributes_land_on_their_chip(self):
        self.assertEqual(offers.parse_subtitles('d2="Rewrites origin"', 3), ["", "Rewrites origin", ""])

    def test_a_list_is_padded_to_the_option_count(self):
        self.assertEqual(offers.parse_subtitles(["One"], 3), ["One", "", ""])

    def test_whitespace_and_wrapping_collapse(self):
        self.assertEqual(offers.parse_subtitles(["  a  \n b \t c "], 1), ["a b c"])

    def test_an_over_long_line_is_cut(self):
        out = offers.parse_subtitles(["x" * 400], 1)[0]
        self.assertEqual(len(out), 160)

    def test_nothing_is_normal(self):
        self.assertEqual(offers.parse_subtitles(None, 2), ["", ""])
        self.assertEqual(offers.parse_subtitles(["", ""], 2), ["", ""])

    def test_out_of_range_numbers_are_dropped(self):
        self.assertEqual(offers.parse_subtitles('d9="nope"', 2), ["", ""])


class DirectiveTest(unittest.TestCase):
    def test_the_attribute_rides_the_directive(self):
        out = offers.directive(["Tag it", "Push it"], subs=["", "Rewrites origin"])
        self.assertIn('d2="Rewrites origin"', out)
        self.assertNotIn("d1=", out, "an empty subtitle writes nothing")

    def test_no_subtitle_leaves_the_directive_unchanged(self):
        out = offers.directive(["Tag it", "Push it"])
        self.assertNotIn(" d", out)

    def test_a_quote_in_a_subtitle_cannot_break_the_brace(self):
        out = offers.directive(["Tag it", "Push it"], subs=['Says "no"', ""])
        self.assertEqual(out.count("}"), 1)
        self.assertIn("d1=", out)


class ReorderTest(unittest.TestCase):
    def test_a_subtitle_travels_with_its_chip(self):
        text = '::nextsteps{alt="1,3" d1="Rewrites origin" q1="Force-push" q2="Leave it as it is" q3="Delete the tag"}'
        deferrals = [2]
        moved = offers.reorder_alternates(text, deferrals)
        self.assertIn('q1="Force-push"', moved)
        self.assertIn('q3="Leave it as it is"', moved)
        self.assertIn('d1="Rewrites origin"', moved, "the subtitle stays on the chip it describes")

    def test_a_reorder_is_still_idempotent_with_subtitles(self):
        text = '::nextsteps{alt="1,3" d1="Rewrites origin" q1="Force-push" q2="Leave it as it is" q3="Delete the tag"}'
        once = offers.reorder_alternates(text, [2])
        labels = offers.directive_options(once)
        deferrals = [n for n, label in enumerate(labels, start=1) if recommend.is_none_option(label)]
        self.assertEqual(offers.reorder_alternates(once, deferrals), once)


class ToolTest(unittest.TestCase):
    def build(self):
        store = Pending()
        tool = handler(
            store,
            recommend_picks=lambda options, context: [],
            wants_recommend=lambda: False,
            risk_picks=lambda options, context: [],
            wants_risk=lambda: False,
        )
        return store, tool

    def test_the_tool_takes_subtitles_and_attaches_them(self):
        store, tool = self.build()
        tool(
            {
                "options": ["Tag it", "Push it"],
                "recommend": False,
                "subtitles": ["", "Rewrites origin, discarding their commit"],
            },
            session_id="s1",
        )
        # attach is what consumes the registration, so read the directive first.
        out = attach("Done.", "s1", platform="desktop", pending=store)
        self.assertIn('d2="Rewrites origin, discarding their commit"', out)

    def test_the_registration_keeps_the_subtitles_for_the_directive(self):
        store, tool = self.build()
        tool({"options": ["Tag it", "Push it"], "recommend": False, "subtitles": ["", "Rewrites origin"]},
             session_id="s3")
        self.assertEqual(store.take("s3")[5], ["", "Rewrites origin"])

    def test_a_missing_subtitle_list_costs_nothing(self):
        store, tool = self.build()
        tool({"options": ["Tag it", "Push it"], "recommend": False}, session_id="s1")
        self.assertEqual(store.take("s1")[5], ["", ""])
        self.assertIn("Chips registered", tool({"options": ["A", "B"], "recommend": False}, session_id="s2"))

    def test_the_schema_advertises_subtitles(self):
        from chips import NEXT_STEPS_SCHEMA

        self.assertIn("subtitles", NEXT_STEPS_SCHEMA["parameters"]["properties"])
