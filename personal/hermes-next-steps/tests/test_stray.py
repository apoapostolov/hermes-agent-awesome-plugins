"""A printed classifier call and a dead `recommend=` attribute never reach the reply.

Both were seen in real sessions: a directive followed by a fenced
`{"recommend": "2"}` block, which renders as a code block, and `recommend="1"`
written inside the directive where the renderer reads `rec` and ignores the rest.
"""

import unittest

import offers
import stray

DIRECTIVE = '::nextsteps{multi="0" q1="Push the branch" q2="Leave it as it stands"}'


class PrintedCall(unittest.TestCase):
    def test_a_trailing_call_block_goes(self):
        reply = DIRECTIVE + '\n\n```json\n{"recommend": "2"}\n```'
        self.assertEqual(stray.strip_call(reply), DIRECTIVE)

    def test_a_bare_fence_without_a_language_goes(self):
        self.assertEqual(stray.strip_call('Done.\n\n```\n{"rec": "1"}\n```'), "Done.")

    def test_whitespace_after_the_block_does_not_save_it(self):
        self.assertEqual(stray.strip_call('Done.\n```json\n{"recommend": "1"}\n```\n\n'), "Done.")

    def test_a_block_with_an_extra_key_is_somebody_s_example(self):
        reply = 'Done.\n\n```json\n{"recommend": "1", "note": "keep me"}\n```'
        self.assertEqual(stray.strip_call(reply), reply)

    def test_a_block_that_does_not_end_the_reply_stays(self):
        reply = '```json\n{"recommend": "1"}\n```\n\nThat is the shape it returns.'
        self.assertEqual(stray.strip_call(reply), reply)

    def test_a_block_that_is_not_json_stays(self):
        reply = 'Done.\n\n```\nnot a call\n```'
        self.assertEqual(stray.strip_call(reply), reply)

    def test_a_reply_without_a_fence_is_returned_as_written(self):
        self.assertEqual(stray.strip_call(DIRECTIVE), DIRECTIVE)
        self.assertEqual(stray.strip_call(""), "")


class DeadAttribute(unittest.TestCase):
    def test_the_tool_argument_name_goes(self):
        reply = '::nextsteps{multi="0" q1="Find the writer" q2="Leave them" recommend="1" alt="1,2"}'
        self.assertEqual(
            offers.strip_recommend_attribute(reply),
            '::nextsteps{multi="0" q1="Find the writer" q2="Leave them" alt="1,2"}',
        )

    def test_an_attribute_that_opens_the_directive_leaves_no_leading_space(self):
        self.assertEqual(
            offers.strip_recommend_attribute('::nextsteps{recommend="2" q1="A" q2="B"}'),
            '::nextsteps{q1="A" q2="B"}',
        )

    def test_rec_survives(self):
        reply = '::nextsteps{q1="A" q2="B" rec="1"}'
        self.assertEqual(offers.strip_recommend_attribute(reply), reply)

    def test_a_label_that_talks_about_recommending_survives(self):
        reply = '::nextsteps{q1="Review the recommended reading" q2="Skip it"}'
        self.assertEqual(offers.strip_recommend_attribute(reply), reply)


if __name__ == "__main__":
    unittest.main()
