"""The prompt section has to survive the host's cap, or it is dropped whole.

Hermes applies its own limit to the text a plugin registers and skips an oversized
section instead of truncating it. On a machine with a decision classifier the section
reached 2,335 characters against a 2,200 cap and vanished, so the rule that makes a
reply end in chips never reached the model.
"""

import unittest

import prompt_section as ps


class FitsTheHostCap(unittest.TestCase):
    def test_every_combination_stays_inside_the_declared_cap(self):
        for recommends in (False, True):
            for risk in (False, True):
                text = ps.chips_rule({"platform": "local"}, recommends, risk)
                self.assertLessEqual(len(text), ps.MAX_CHARS, (recommends, risk, len(text)))

    def test_the_cap_sits_under_the_host_limit(self):
        self.assertLess(ps.MAX_CHARS, 2200)

    def test_optional_paragraphs_go_before_the_rule(self):
        original = ps.MAX_CHARS
        try:
            ps.MAX_CHARS = len(ps.DESKTOP) + 40
            text = ps.chips_rule({"platform": "local"}, True, True)
        finally:
            ps.MAX_CHARS = original
        self.assertLessEqual(len(text), len(ps.DESKTOP) + 40)
        self.assertTrue(text.startswith(ps.DESKTOP[:80]))
        self.assertNotIn("RISKY pill", text)

    def test_other_surfaces_are_told_to_offer_a_list(self):
        self.assertEqual(ps.chips_rule({}), ps.OTHER)
        self.assertEqual(ps.chips_rule({"platform": "telegram"}), ps.OTHER)

    def test_the_rule_names_the_tool_and_the_directive(self):
        text = ps.chips_rule({"platform": "local"}, True, False)
        for needle in ("next_steps", "::nextsteps", "multi=false", "alternates", "recommend=true"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
