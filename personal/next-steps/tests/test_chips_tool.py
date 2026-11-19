"""The next_steps tool: validation, the pending store, and the reply hook.

The point of the tool channel is that the model passes a JSON array instead of writing
a directive by hand, so most of these tests are about what happens to bad input and
about the one registration that belongs to each reply.
"""

from __future__ import annotations

import json
import unittest

from chips import (
    MAX_OPTION_CHARS,
    MAX_OPTIONS,
    Pending,
    attach,
    clean,
    handler,
    rec_attribute,
)
from offers import DIRECTIVE_RE, directive


class CleanTest(unittest.TestCase):
    def test_order_is_kept_and_whitespace_collapsed(self):
        self.assertEqual(clean(["  Push  the branch ", "Tag it"]), ["Push the branch", "Tag it"])

    def test_duplicates_are_dropped_case_insensitively(self):
        self.assertEqual(clean(["Tag it", "tag IT", "Push it"]), ["Tag it", "Push it"])

    def test_blanks_and_non_strings_are_dropped(self):
        self.assertEqual(clean(["Push it", "", None, 42, "Tag it"]), ["Push it", "Tag it"])

    def test_newline_text_is_accepted(self):
        self.assertEqual(clean("Push it\nTag it\n"), ["Push it", "Tag it"])

    def test_a_long_label_is_truncated_not_rejected(self):
        label = "x" * (MAX_OPTION_CHARS + 40)
        out = clean([label, "Tag it"])
        self.assertEqual(len(out[0]), MAX_OPTION_CHARS)
        self.assertTrue(out[0].endswith("\u2026"))

    def test_more_than_six_is_cut_to_six(self):
        out = clean(["option %d" % i for i in range(9)])
        self.assertEqual(len(out), MAX_OPTIONS)

    def test_one_option_is_refused(self):
        with self.assertRaises(ValueError):
            clean(["Push it"])

    def test_all_duplicates_collapse_to_a_refusal(self):
        with self.assertRaises(ValueError):
            clean(["Tag it", "Tag it"])

    def test_a_non_list_is_refused(self):
        with self.assertRaises(ValueError):
            clean({"options": ["a", "b"]})


class RecAttributeTest(unittest.TestCase):
    def test_numbers_are_kept_in_order_and_deduplicated(self):
        self.assertEqual(rec_attribute([3, 1, 3], 3), "3,1")

    def test_out_of_range_and_junk_are_dropped(self):
        self.assertEqual(rec_attribute([0, 1, 9, "x", None], 3), "1")

    def test_nothing_usable_is_empty(self):
        self.assertEqual(rec_attribute([], 3), "")
        self.assertEqual(rec_attribute("1,2", 3), "")


class PendingTest(unittest.TestCase):
    def test_take_consumes_once(self):
        store = Pending()
        store.put("s1", ["A", "B"], False, "1")
        self.assertEqual(store.take("s1"), (['A', 'B'], False, '1', '', '', ['', ''], False))
        self.assertIsNone(store.take("s1"))

    def test_sessions_do_not_leak_into_each_other(self):
        store = Pending()
        store.put("s1", ["A", "B"])
        self.assertIsNone(store.take("s2"))
        self.assertIsNotNone(store.take("s1"))

    def test_an_expired_registration_is_dropped(self):
        now = [0.0]
        store = Pending(ttl=10.0, clock=lambda: now[0])
        store.put("s1", ["A", "B"])
        now[0] = 11.0
        self.assertIsNone(store.take("s1"))
        self.assertFalse(store.has("s1"))

    def test_a_fresh_registration_survives_the_window(self):
        now = [0.0]
        store = Pending(ttl=10.0, clock=lambda: now[0])
        store.put("s1", ["A", "B"])
        now[0] = 9.0
        self.assertTrue(store.has("s1"))

    def test_forget_drops_it(self):
        store = Pending()
        store.put("s1", ["A", "B"])
        store.forget("s1")
        self.assertIsNone(store.take("s1"))


class AttachTest(unittest.TestCase):
    def test_the_directive_is_appended_with_the_registered_shape(self):
        store = Pending()
        store.put("s1", ["Push it", "Tag it"], False, "2")
        out = attach("Done.", "s1", platform="local", pending=store)
        self.assertTrue(out.startswith("Done.\n\n::nextsteps{"))
        self.assertIn('rec="2"', out)
        self.assertNotIn('multi="1"', out)
        self.assertIn('q1="Push it"', out)

    def test_multi_true_survives(self):
        store = Pending()
        store.put("s1", ["A", "B", "C"], True)
        out = attach("Done.", "s1", platform="desktop", pending=store)
        self.assertIn('multi="1"', out)

    def test_off_desktop_nothing_is_attached_and_the_entry_is_dropped(self):
        store = Pending()
        store.put("s1", ["A", "B"])
        self.assertIsNone(attach("Done.", "s1", platform="telegram", pending=store))
        self.assertIsNone(store.take("s1"))

    def test_a_written_directive_wins_and_the_registration_is_dropped(self):
        store = Pending()
        store.put("s1", ["A", "B"])
        text = 'Done.\n\n::nextsteps{q1="Own" q2="Chips"}'
        self.assertIsNone(attach(text, "s1", platform="local", pending=store))
        self.assertIsNone(store.take("s1"))

    def test_no_registration_means_no_change(self):
        store = Pending()
        self.assertIsNone(attach("Done.", "s1", platform="local", pending=store))

    def test_empty_text_drops_the_registration(self):
        store = Pending()
        store.put("s1", ["A", "B"])
        self.assertIsNone(attach("", "s1", platform="local", pending=store))
        self.assertIsNone(store.take("s1"))


class HandlerTest(unittest.TestCase):
    def make(self, picks=None, wants=None):
        store = Pending()
        calls = []

        def recommend_picks(options, context_line):
            calls.append((list(options), context_line))
            return picks if picks is not None else []

        handler_fn = handler(store, None, recommend_picks, None if wants is None else (lambda: wants))
        return store, handler_fn, calls

    def test_a_good_call_registers_and_tells_the_model_not_to_write_a_directive(self):
        store, tool, _ = self.make(picks=[])
        reply = tool({"options": ["Push it", "Tag it"], "multi": False}, session_id="s1")
        self.assertIn("Chips registered", reply)
        self.assertIn("do not also write a ::nextsteps line", reply)
        self.assertEqual(store.take("s1"), (['Push it', 'Tag it'], False, '', '', '', ['', ''], False))

    def test_a_bad_call_registers_nothing(self):
        store, tool, _ = self.make()
        reply = tool({"options": ["only one"]}, session_id="s1")
        self.assertIn("Chips not registered", reply)
        self.assertIsNone(store.take("s1"))

    def test_recommend_false_skips_the_classifier(self):
        store, tool, calls = self.make(picks=[1])
        reply = tool({"options": ["A", "B"], "recommend": False}, session_id="s1")
        self.assertEqual(calls, [])
        self.assertEqual(store.take("s1"), (['A', 'B'], None, '', '', '', ['', ''], False))
        self.assertNotIn("recommended", reply)

    def test_recommend_marks_the_numbers_the_classifier_returned(self):
        store, tool, calls = self.make(picks=[2])
        reply = tool({"options": ["A", "B"], "recommend": True, "context": "a review"}, session_id="s1")
        self.assertEqual(calls, [(["A", "B"], "a review")])
        self.assertEqual(store.take("s1"), (['A', 'B'], None, '2', '', '', ['', ''], False))
        self.assertIn("recommended 2", reply)

    def test_the_setting_decides_when_the_argument_is_absent(self):
        store, tool, calls = self.make(picks=[], wants=False)
        tool({"options": ["A", "B"]}, session_id="s1")
        self.assertEqual(calls, [])

    def test_a_classifier_failure_still_keeps_the_chips(self):
        store = Pending()

        def boom(options, context_line):
            raise RuntimeError("classifier down")

        tool = handler(store, None, boom, lambda: True)
        reply = tool({"options": ["A", "B"]}, session_id="s1")
        self.assertIn("Chips registered", reply)
        self.assertEqual(store.take("s1"), (['A', 'B'], None, '', '', '', ['', ''], False))

    def test_nothing_cleared_is_reported_without_a_rec_attribute(self):
        store, tool, _ = self.make(picks=[])
        reply = tool({"options": ["A", "B"]}, session_id="s1")
        self.assertIn("nothing cleared the bar", reply)
        self.assertEqual(store.take("s1"), (['A', 'B'], None, '', '', '', ['', ''], False))


class RegistrationTest(unittest.TestCase):
    """The claim that matters to the app: the tool exists and the hook exists."""

    def test_the_plugin_registers_both_tools_and_the_hook(self):
        import importlib.util
        import pathlib
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "next_steps_pkg", root / "__init__.py", submodule_search_locations=[str(root)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["next_steps_pkg"] = module
        spec.loader.exec_module(module)

        class Ctx:
            def __init__(self):
                self.tools, self.hooks, self.sections = {}, {}, []

            def get_config(self, key, default=None):
                return default

            def dispatch_tool(self, name, args):
                raise RuntimeError("no classifier in this probe")

            def has_plugin(self, name):
                return name == "nerve"

            def register_tool(self, name, toolset, schema, handler, **kwargs):
                self.tools[name] = schema

            def register_hook(self, name, fn):
                self.hooks[name] = fn

            def register_system_prompt_section(self, *args, **kwargs):
                self.sections.append(args)

        ctx = Ctx()
        module.register(ctx)
        self.assertEqual(sorted(ctx.tools), ["next_steps", "next_steps_recommend"])
        self.assertIn("transform_llm_output", ctx.hooks)
        self.assertEqual(ctx.tools["next_steps"]["parameters"]["required"], ["options"])

    def test_end_to_end_through_the_hook(self):
        import importlib.util
        import pathlib
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "next_steps_pkg2", root / "__init__.py", submodule_search_locations=[str(root)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["next_steps_pkg2"] = module
        spec.loader.exec_module(module)

        settings = {"carry_over": True, "accent_recommended": True, "auto_offers": False}

        class Ctx:
            def __init__(self):
                self.hooks, self.tools = {}, {}

            def get_config(self, key, default=None):
                return settings.get(key, default)

            def dispatch_tool(self, name, args):
                raise RuntimeError("no classifier here")

            def has_plugin(self, name):
                return False

            def register_tool(self, name, toolset, schema, handler, **kwargs):
                self.tools[name] = handler

            def register_hook(self, name, fn):
                self.hooks[name] = fn

            def register_system_prompt_section(self, *args, **kwargs):
                pass

        ctx = Ctx()
        module.register(ctx)
        tool = ctx.tools["next_steps"]
        hook = ctx.hooks["transform_llm_output"]
        tool({"options": ["Push it", "Tag it"], "multi": False}, session_id="sess-1")
        out = hook(response_text="Done.", platform="local", session_id="sess-1")
        self.assertIn("::nextsteps{", out)
        self.assertIn('carry="1"', out)
        self.assertIn('q1="Push it"', out)
        self.assertNotIn('multi="1"', out)
        # The registration is consumed: a second reply gets only the carry block.
        second = hook(response_text="All green.", platform="local", session_id="sess-1")
        # The empty block carry adds is named for the chat too, so a chat only ever
        # carries its own proposals.
        self.assertIn('carry="1"', second)
        self.assertIn('sid="', second)

    def test_the_text_directive_still_wins_over_a_registration(self):
        import importlib.util
        import pathlib
        import sys

        root = pathlib.Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "next_steps_pkg3", root / "__init__.py", submodule_search_locations=[str(root)]
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules["next_steps_pkg3"] = module
        spec.loader.exec_module(module)

        class Ctx:
            def __init__(self):
                self.hooks, self.tools = {}, {}

            def get_config(self, key, default=None):
                return {"carry_over": False, "accent_recommended": True, "auto_offers": False}.get(key, default)

            def dispatch_tool(self, name, args):
                raise RuntimeError("no classifier here")

            def has_plugin(self, name):
                return False

            def register_tool(self, name, toolset, schema, handler, **kwargs):
                self.tools[name] = handler

            def register_hook(self, name, fn):
                self.hooks[name] = fn

            def register_system_prompt_section(self, *args, **kwargs):
                pass

        ctx = Ctx()
        module.register(ctx)
        ctx.tools["next_steps"]({"options": ["A", "B"]}, session_id="s9")
        own = 'Done.\n\n::nextsteps{q1="Mine" q2="Own"}'
        out = ctx.hooks["transform_llm_output"](response_text=own, platform="local", session_id="s9")
        # The registration is dropped and the written chips stay, but the stamps
        # still apply to them: pickability, and the chat fingerprint.
        self.assertIn('q1="Mine"', out)
        self.assertIn('q2="Own"', out)
        self.assertNotIn('q1="A"', out)
        self.assertIn('multi="1"', out)
        self.assertIn('sid="', out)



class AlternateArgTest(unittest.TestCase):
    """The tool takes the pairs the model declares and adds the one rule it must not lose."""

    def make(self):
        from chips import Pending, handler

        store = Pending()
        return store, handler(store, recommend_picks=lambda options, context: []), ()

    def test_declared_pairs_are_stored(self):
        store, tool, _ = self.make()
        tool({"options": ["Force-push", "Add a note", "Tag it"], "alternates": [[1, 3]]}, session_id="s1")
        self.assertEqual(store.take("s1")[3], "1,3")

    def test_a_deferral_is_paired_with_every_action(self):
        store, tool, _ = self.make()
        tool({"options": ["Push it", "Tag it", "Leave as it is"], "recommend": False}, session_id="s1")
        self.assertEqual(store.take("s1")[3], "1,3|2,3")

    def test_declared_and_implied_groups_merge(self):
        store, tool, _ = self.make()
        tool(
            {"options": ["Push it", "Tag it", "Leave as it is"], "alternates": [[1, 2]], "recommend": False},
            session_id="s1",
        )
        self.assertEqual(store.take("s1")[3], "1,2|1,3|2,3")

    def test_the_directive_carries_the_attribute(self):
        store, tool, _ = self.make()
        tool({"options": ["Push it", "Leave as it is"], "recommend": False}, session_id="s1")
        from chips import attach

        out = attach("Done.", "s1", platform="desktop", pending=store)
        self.assertIn('alt="1,2"', out)

if __name__ == "__main__":
    unittest.main()
