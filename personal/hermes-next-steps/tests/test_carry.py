"""carry="1": a reply keeps its own chips and also draws what earlier replies left."""

import unittest

import offers


class StampCarryTest(unittest.TestCase):
    def test_an_existing_directive_is_marked(self):
        out = offers.stamp_carry('Branch is pushed.\n\n::nextsteps{q1="Open the PR" q2="Tag it"}', platform='local')
        self.assertIn('::nextsteps{carry="1" q1="Open the PR"', out)

    def test_a_directive_with_attributes_keeps_them(self):
        out = offers.stamp_carry('::nextsteps{multi="1" rec="2" q1="A" q2="B"}', platform='local')
        self.assertIn('carry="1"', out)
        self.assertIn('multi="1"', out)
        self.assertIn('rec="2"', out)

    def test_stamping_twice_changes_nothing(self):
        once = offers.stamp_carry('Done.\n\n::nextsteps{q1="A"}', platform='local')
        self.assertEqual(offers.stamp_carry(once, platform='local'), once)

    def test_a_reply_that_proposes_nothing_gets_one_empty_block(self):
        # The directive slot is the only place a desktop plugin can draw, so an
        # empty block is what lets a chip-less reply show the carried proposals.
        out = offers.stamp_carry('The migration is finished.', platform='local')
        self.assertEqual(out, 'The migration is finished.\n\n::nextsteps{carry="1"}')

    def test_trailing_newlines_do_not_leave_a_gap(self):
        out = offers.stamp_carry('Done.\n\n', platform='local')
        self.assertEqual(out, 'Done.\n\n::nextsteps{carry="1"}')

    def test_another_surface_gets_the_text_untouched(self):
        text = 'The migration is finished.'
        self.assertEqual(offers.stamp_carry(text, platform='telegram'), text)
        self.assertEqual(offers.stamp_carry(text, platform='cli'), text)

    def test_desktop_is_also_a_surface_that_draws(self):
        self.assertIn('carry="1"', offers.stamp_carry('Done.', platform='desktop'))

    def test_prose_is_untouched(self):
        text = 'Two things changed.\n\n- the parser\n- the tests'
        self.assertTrue(offers.stamp_carry(text, platform='local').startswith(text))

    def test_empty_and_junk_input_comes_back(self):
        for value in ('', None, 42):
            self.assertEqual(offers.stamp_carry(value, platform='local'), value)


if __name__ == '__main__':
    unittest.main()
