"""Options that exclude each other: the attribute, the parser, and the rule the decision implies."""

from __future__ import annotations

import unittest

import offers
import recommend


class ParseTest(unittest.TestCase):
    def test_a_string_of_groups(self):
        self.assertEqual(offers.parse_alternates("1,3|2,4", 4), [[1, 3], [2, 4]])

    def test_nested_lists_from_a_tool_call(self):
        self.assertEqual(offers.parse_alternates([[1, 3], [2, 4]], 4), [[1, 3], [2, 4]])

    def test_a_group_of_one_means_nothing(self):
        self.assertEqual(offers.parse_alternates("1|2,3", 3), [[2, 3]])

    def test_numbers_out_of_range_are_dropped(self):
        self.assertEqual(offers.parse_alternates("1,9", 3), [])
        self.assertEqual(offers.parse_alternates("0,1,2", 3), [[1, 2]])

    def test_members_come_back_sorted_and_distinct(self):
        self.assertEqual(offers.parse_alternates("3,1,3", 3), [[1, 3]])

    def test_the_same_group_twice_is_kept_once(self):
        self.assertEqual(offers.parse_alternates("1,2|2,1", 3), [[1, 2]])

    def test_junk_is_ignored(self):
        self.assertEqual(offers.parse_alternates(None, 3), [])
        self.assertEqual(offers.parse_alternates("", 3), [])
        self.assertEqual(offers.parse_alternates("x,y", 3), [])

    def test_the_attribute_text(self):
        self.assertEqual(offers.alternate_attribute([[3, 1], [2, 3]], 3), "1,3|2,3")
        self.assertEqual(offers.alternate_attribute([], 3), "")


class MergeTest(unittest.TestCase):
    def test_the_policy_group_is_added(self):
        self.assertEqual(offers.merge_alternates("1,2", [[3, 1]], 3), [[1, 2], [1, 3]])

    def test_an_existing_group_is_not_duplicated(self):
        self.assertEqual(offers.merge_alternates("1,3", [[3, 1]], 3), [[1, 3]])

    def test_it_is_idempotent(self):
        once = offers.merge_alternates("1,2", [[3, 1]], 3)
        self.assertEqual(offers.merge_alternates(once, [[3, 1]], 3), once)


class StampTest(unittest.TestCase):
    def test_a_directive_without_groups_gains_them(self):
        text = '::nextsteps{q1="Push it" q2="Leave as it is"}'
        self.assertIn('alt="1,2"', offers.stamp_alternates(text, [[1, 2]], 2))

    def test_the_models_own_groups_survive(self):
        text = '::nextsteps{alt="1,2" q1="A" q2="B" q3="Leave it"}'
        out = offers.stamp_alternates(text, [[3, 1], [3, 2]], 3)
        self.assertIn('alt="1,2|1,3|2,3"', out)

    def test_a_second_pass_changes_nothing(self):
        text = '::nextsteps{q1="A" q2="Leave it"}'
        once = offers.stamp_alternates(text, [[1, 2]], 2)
        self.assertEqual(offers.stamp_alternates(once, [[1, 2]], 2), once)

    def test_prose_and_other_directives_are_left_alone(self):
        self.assertEqual(offers.stamp_alternates("No chips here.", [[1, 2]], 2), "No chips here.")

    def test_the_options_are_read_back_in_order(self):
        text = '::nextsteps{q2="Second" q1="First"}'
        self.assertEqual(offers.directive_options(text), ["First", "Second"])


class ImpliedTest(unittest.TestCase):
    def test_a_deferral_is_opposed_to_every_action(self):
        groups = recommend.alternate_groups(["Ship it", "Tag it", "Leave as it is"])
        self.assertEqual(groups, [[1, 3], [2, 3]])

    def test_actions_alone_are_compatible(self):
        self.assertEqual(recommend.alternate_groups(["Ship it", "Tag it"]), [])

    def test_two_deferrals_also_exclude_each_other(self):
        groups = recommend.alternate_groups(["Ship it", "Do nothing", "Wait for review"])
        self.assertIn([1, 2], groups)
        self.assertIn([1, 3], groups)
        self.assertIn([2, 3], groups)

    def test_the_phrasings_a_model_uses(self):
        for label in ("Leave as it is", "leave it for tomorrow", "Not now", "Status quo", "No change"):
            self.assertEqual(
                recommend.alternate_groups(["Ship it", label]),
                [[1, 2]],
                label,
            )


class OrderTest(unittest.TestCase):
    """Alternates sit together, and the option that means "leave it" closes the row."""

    def test_no_groups_means_no_change(self):
        self.assertEqual(offers.alternate_order([], 3), [1, 2, 3])

    def test_a_cluster_pulls_together(self):
        # 1 and 3 exclude each other, 2 does not: 2 slides right.
        self.assertEqual(offers.alternate_order([[1, 3]], 3), [1, 3, 2])

    def test_chained_groups_make_one_cluster(self):
        self.assertEqual(offers.alternate_order([[1, 3], [3, 4]], 4), [1, 3, 4, 2])

    def test_a_deferral_closes_the_row(self):
        self.assertEqual(offers.alternate_order([[1, 3]], 3, deferrals=[3]), [1, 2, 3])

    def test_two_deferrals_keep_their_order_at_the_end(self):
        self.assertEqual(offers.alternate_order([[2, 4]], 4, deferrals=[2, 4]), [1, 3, 2, 4])

    def test_an_alternate_of_everything_goes_last_even_unnamed(self):
        self.assertEqual(offers.alternate_order([[1, 2], [1, 3], [1, 4]], 4), [2, 3, 4, 1])

    def test_two_actions_and_a_deferral_put_the_deferral_last(self):
        # Every chip is an alternate of the other two here, so only the phrasing decides.
        groups = [[1, 3], [1, 2], [2, 3]]
        self.assertEqual(offers.alternate_order(groups, 3, deferrals=[2]), [1, 3, 2])

    def test_the_reorder_moves_labels_and_numbers(self):
        text = '::nextsteps{alt="1,3" rec="3" risky="1" q1="Force-push" q2="Add a note" q3="Leave it"}'
        out = offers.reorder_alternates(text, deferrals=[3])
        self.assertIn('q1="Force-push"', out)
        self.assertIn('q2="Add a note"', out)
        self.assertIn('q3="Leave it"', out, "the deferral closes the row")
        self.assertIn('alt="1,3"', out)

    def test_the_marks_follow_their_chip(self):
        text = '::nextsteps{alt="2,4" rec="2" risky="2" q1="Ship" q2="Delete the tag" q3="Notes" q4="Recreate"}'
        out = offers.reorder_alternates(text)
        self.assertIn('rec="2"', out, "the recommendation stays on the delete chip")
        self.assertIn('risky="2"', out)
        self.assertIn('alt="2,3"', out, "the partner slid from slot 4 to slot 3")
        self.assertIn('q3="Recreate"', out)

    def test_a_reorder_that_changes_nothing_returns_the_text(self):
        text = '::nextsteps{alt="1,2" q1="A" q2="B" q3="C"}'
        self.assertEqual(offers.reorder_alternates(text), text)

    def test_a_second_pass_changes_nothing(self):
        text = '::nextsteps{alt="1,3" q1="Force-push" q2="Add a note" q3="Leave it"}'
        once = offers.reorder_alternates(text, deferrals=[3])
        self.assertEqual(offers.reorder_alternates(once, deferrals=[3]), once)

    def test_prose_is_untouched(self):
        self.assertEqual(offers.reorder_alternates("No chips here."), "No chips here.")


if __name__ == "__main__":
    unittest.main()
