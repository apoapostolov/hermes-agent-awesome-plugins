"""Answer mode stays a directive fallback; the tool always draws chips."""

from __future__ import annotations

import unittest

import offers
import prompt_section
from chips import Pending, NEXT_STEPS_SCHEMA, attach, handler


class DirectiveTest(unittest.TestCase):
    def test_answer_replaces_pickability(self):
        out = offers.directive(["Deploy?", "Tag?"], answer=True)
        self.assertIn('answer="1"', out)
        self.assertNotIn("multi=", out, "a form is not a chip row")
        self.assertIn('q1="Deploy?"', out)

    def test_a_plain_directive_does_not_change(self):
        self.assertEqual(offers.directive(["A", "B"]), '::nextsteps{multi="1" q1="A" q2="B"}')

    def test_the_hook_does_not_add_multi_to_an_answer_block(self):
        text = '::nextsteps{answer="1" q1="Deploy?" q2="Tag?"}'
        self.assertEqual(offers.stamp_multi(text), text)


class ToolTest(unittest.TestCase):
    def test_the_tool_does_not_expose_answer(self):
        self.assertNotIn("answer", NEXT_STEPS_SCHEMA["parameters"]["properties"])

    def test_a_stale_answer_call_still_draws_chips(self):
        store = Pending()
        out = handler(store)({"options": ["A", "B"], "answer": True}, "s1")
        self.assertIn("multi", out)
        self.assertNotIn("answer fields", out)
        self.assertIs(store.take("s1")[6], False)

    def test_a_call_without_the_flag_stays_a_chip_block(self):
        store = Pending()
        handler(store)({"options": ["A", "B"]}, "s2")
        self.assertIs(store.take("s2")[6], False)


class AttachTest(unittest.TestCase):
    def test_a_directive_answer_reaches_the_reply(self):
        store = Pending()
        store.put("s3", ["Deploy?", "Tag?"], None, "", "", "", (), True)
        text = attach("Done.", "s3", platform="local", pending=store)
        self.assertTrue(text.startswith("Done.\n\n::nextsteps{"))
        self.assertIn('answer="1"', text)


class PromptTest(unittest.TestCase):
    def test_the_rule_does_not_offer_answer_mode(self):
        self.assertNotIn("answer=true", prompt_section.chips_rule({"platform": "local"}))

    def test_every_variant_fits_the_cap(self):
        for name, text in prompt_section.prompt_texts():
            self.assertLessEqual(len(text), prompt_section.MAX_CHARS, name)
