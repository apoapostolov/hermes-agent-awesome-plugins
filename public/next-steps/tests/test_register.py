"""What register(ctx) wires up, and that the hook stays off unless the owner turns it on."""

from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_plugin():
    """Import this folder as a package (its name has a dash, so it cannot be imported by name)."""
    spec = importlib.util.spec_from_file_location(
        "next_steps", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["next_steps"] = module
    spec.loader.exec_module(module)
    return module


plugin = load_plugin()

OFFER = "Branch is pushed.\n\nWant me to open the PR?"


class FakeCtx:
    def __init__(self, settings=None, plugins=()):
        self.settings = settings or {}
        self.plugins = set(plugins)
        self.sections = []
        self.hooks = {}
        self.tools = {}

    def register_system_prompt_section(self, section_id, content, **kwargs):
        self.sections.append((section_id, content, kwargs))

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def register_tool(self, name=None, toolset=None, schema=None, handler=None, **kwargs):
        self.tools[name] = {"toolset": toolset, "schema": schema, "handler": handler}

    def has_plugin(self, plugin_id):
        return plugin_id in self.plugins

    def get_config(self, key, default=None):
        return self.settings.get(key, default)

    def dispatch_tool(self, name, args, **kwargs):
        raise RuntimeError("no classifier in tests")


class RegisterTest(unittest.TestCase):
    def test_registers_one_prompt_section_and_the_output_hook(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        self.assertEqual([s[0] for s in ctx.sections], ["next-steps"])
        self.assertEqual(ctx.sections[0][2]["max_chars"], plugin.MAX_CHARS)
        self.assertEqual(list(ctx.hooks), ["transform_llm_output"])

    def test_prompt_section_never_asks_for_a_directive_off_desktop(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        rule = ctx.sections[0][1]
        self.assertIn("::nextsteps", rule({"platform": "local"}))
        self.assertIn("never write a ::nextsteps directive", rule({"platform": "telegram"}))

    def test_hook_is_silent_until_auto_offers_is_on(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text=OFFER, platform="local"))

    def test_hook_rewrites_the_offer_when_enabled(self):
        ctx = FakeCtx({"auto_offers": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertEqual(
            hook(response_text=OFFER, platform="local"),
            'Branch is pushed.\n\n::nextsteps{q1="Open the PR"}',
        )

    def test_hook_leaves_other_surfaces_alone_even_when_enabled(self):
        ctx = FakeCtx({"auto_offers": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text=OFFER, platform="telegram"))

    def test_hook_survives_kwargs_and_a_broken_setting_store(self):
        ctx = FakeCtx({"auto_offers": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(turn_id="t1", model="m", session_id="s"))
        ctx.get_config = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no store"))
        self.assertIsNone(hook(response_text=OFFER, platform="local"))

    def test_offer_hook_ignores_non_string_replies(self):
        self.assertIsNone(plugin.offer_hook(response_text=None, platform="local", auto_offers=True))


class RecommendRegistrationTest(unittest.TestCase):
    def test_the_recommend_tool_is_always_registered(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        self.assertEqual(sorted(ctx.tools), ["next_steps", "next_steps_recommend"])
        tool = ctx.tools["next_steps_recommend"]
        self.assertEqual(tool["toolset"], "next_steps")
        self.assertEqual(tool["schema"]["name"], "next_steps_recommend")
        self.assertEqual(tool["schema"]["parameters"]["required"], ["options"])

    def test_a_classifier_loaded_after_this_plugin_is_still_seen(self):
        # Plugins register in dependency order and next-steps loads before nerve,
        # so the probe has to run per session, not once at registration.
        ctx = FakeCtx()
        plugin.register(ctx)
        rule = ctx.sections[0][1]
        self.assertNotIn("next_steps_recommend", rule({"platform": "local"}))
        ctx.plugins.add("nerve")
        self.assertIn("next_steps_recommend", rule({"platform": "local"}))

    def test_the_rule_mentions_the_classifier_only_when_one_is_loaded(self):
        without = FakeCtx()
        plugin.register(without)
        rule = without.sections[0][1]
        self.assertNotIn("next_steps_recommend", rule({"platform": "local"}))
        with_ranker = FakeCtx(plugins=["nerve"])
        plugin.register(with_ranker)
        rule = with_ranker.sections[0][1]
        self.assertIn("next_steps_recommend", rule({"platform": "local"}))
        self.assertNotIn("next_steps_recommend", rule({"platform": "telegram"}))

    def test_the_owner_can_turn_recommendations_off(self):
        ctx = FakeCtx(settings={"auto_recommend": False}, plugins=["nerve"])
        plugin.register(ctx)
        self.assertNotIn("next_steps_recommend", ctx.sections[0][1]({"platform": "local"}))
        ctx.settings["auto_recommend"] = True
        self.assertIn("next_steps_recommend", ctx.sections[0][1]({"platform": "local"}))

    def test_a_classifier_plugin_answers_through_the_tool(self):
        ctx = FakeCtx(plugins=["nerve"])
        answers = {
            "answers": {
                "q1": {"probabilities": {"take it now": 0.81, "later": 0.1, "skip": 0.09}},
                "q2": {"probabilities": {"take it now": 0.31, "later": 0.6, "skip": 0.09}},
            },
            "ok": True,
        }
        import json

        ctx.dispatch_tool = lambda name, args, **kw: json.dumps(answers)
        plugin.register(ctx)
        out = ctx.tools["next_steps_recommend"]["handler"]({"options": ["A", "B"], "context": "x"})
        self.assertIn('rec="1"', out)

    # -- the accent setting travels in the directive -----------------------

    def test_accent_on_adds_nothing_to_a_reply(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text='::nextsteps{q1="A"}', platform="local"))
        self.assertIsNone(hook(response_text=OFFER, platform="local"))

    def test_accent_off_stamps_every_directive_it_sees(self):
        ctx = FakeCtx(settings={"accent_recommended": False})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertEqual(
            hook(response_text='::nextsteps{rec="1" q1="A"}', platform="local"),
            '::nextsteps{accent="0" rec="1" q1="A"}',
        )

    def test_accent_off_still_leaves_prose_alone(self):
        ctx = FakeCtx(settings={"accent_recommended": False})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text="Just an answer, no chips.", platform="local"))
        self.assertIsNone(hook(response_text=OFFER, platform="local"), "auto_offers is off")

    def test_accent_off_and_auto_offers_stamp_the_converted_chips(self):
        ctx = FakeCtx(settings={"accent_recommended": False, "auto_offers": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        out = hook(response_text=OFFER, platform="local")
        self.assertIn('::nextsteps{accent="0" ', out)
        self.assertIn('q1="Open the PR"', out)

    def test_a_broken_setting_store_keeps_the_defaults(self):
        ctx = FakeCtx()

        def boom(key, default=None):
            raise RuntimeError("config unreadable")

        ctx.get_config = boom
        plugin.register(ctx)
        self.assertIsNone(ctx.hooks["transform_llm_output"](response_text='::nextsteps{q1="A"}', platform="local"))


    def test_without_a_classifier_everything_else_still_works(self):
        """'Optional' is a promise: no nerve means no tags, and nothing else changes."""
        ctx = FakeCtx()  # neither nerve nor jev is loaded
        plugin.register(ctx)
        rule = ctx.sections[0][1]
        local = rule({"platform": "local"})
        self.assertIn("::nextsteps", local)
        self.assertNotIn("next_steps_recommend", local)
        converted = plugin.offer_hook(response_text=OFFER, platform="local", auto_offers=True)
        self.assertIsNotNone(converted)
        self.assertIn("::nextsteps", converted)
        self.assertIn("leave rec out", ctx.tools["next_steps_recommend"]["handler"]({"options": ["A", "B"]}))

    def test_the_classifier_is_not_declared_as_a_required_plugin(self):
        # requires_plugins is advisory in Hermes, but an unmet one logs a warning that a
        # required plugin is missing, which reads as a broken install to anyone who
        # skipped the classifier on purpose. The probe is runtime, so the manifest stays quiet.
        for line in (ROOT / "plugin.yaml").read_text(encoding="utf-8").splitlines():
            if line.startswith("requires_plugins"):
                self.assertNotIn("nerve", line)


    def test_carry_over_marks_the_reply_and_adds_a_block_when_it_has_none(self):
        ctx = FakeCtx({"carry_over": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertEqual(
            hook(response_text='::nextsteps{q1="A"}', platform="local"),
            '::nextsteps{carry="1" q1="A"}',
        )
        self.assertEqual(
            hook(response_text="Nothing to offer.", platform="local"),
            'Nothing to offer.\n\n::nextsteps{carry="1"}',
        )

    def test_carry_over_is_off_by_default(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text="Nothing to offer.", platform="local"))

    def test_carry_over_never_reaches_another_surface(self):
        ctx = FakeCtx({"carry_over": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        self.assertIsNone(hook(response_text="Nothing to offer.", platform="telegram"))

    def test_carry_and_offer_conversion_compose(self):
        # The converted directive is the one that gets marked, so reply 1 in a
        # queued session carries over too.
        ctx = FakeCtx({"carry_over": True, "auto_offers": True})
        plugin.register(ctx)
        hook = ctx.hooks["transform_llm_output"]
        out = hook(response_text=OFFER, platform="local")
        self.assertEqual(out, 'Branch is pushed.\n\n::nextsteps{carry="1" q1="Open the PR"}')

    def test_carry_over_also_ships_with_the_accent_off(self):
        # Two independent jobs on one hook: turning the accent off must not stop
        # the carry stamp, and the accent stamp must survive it.
        ctx = FakeCtx({"carry_over": True, "accent_recommended": False})
        plugin.register(ctx)
        out = ctx.hooks["transform_llm_output"](response_text='::nextsteps{rec="1" q1="A"}', platform="local")
        self.assertIn('accent="0"', out)
        self.assertIn('carry="1"', out)



class SteerSettingTest(unittest.TestCase):
    """send_as_steer is off unless asked for, and reaches the chips when it is on."""

    def hook(self, settings, text='Done.\n\n::nextsteps{q1="A" q2="B"}', session="s1"):
        ctx = FakeCtx(settings=settings)
        plugin.register(ctx)
        return ctx.hooks["transform_llm_output"](response_text=text, platform="local", session_id=session)

    def test_off_by_default(self):
        out = self.hook({})
        self.assertNotIn('steer="1"', out or "")

    def test_on_adds_the_attribute(self):
        out = self.hook({"send_as_steer": True})
        self.assertIn('steer="1"', out or "")
        self.assertIn('q2="B"', out or "")

    def test_it_rides_with_the_other_stamps(self):
        out = self.hook({"send_as_steer": True, "carry_over": True})
        self.assertIn('steer="1"', out or "")
        self.assertIn('carry="1"', out or "")
        self.assertIn('multi="1"', out or "")


class AlternateRuleTest(unittest.TestCase):
    """A decision carries its exclusions, even when the model wrote no alt of its own."""

    def hook(self, text, settings=None):
        ctx = FakeCtx(settings=settings or {})
        plugin.register(ctx)
        return ctx.hooks["transform_llm_output"](response_text=text, platform="local", session_id="s1")

    def test_the_deferral_is_marked_opposed_to_the_actions(self):
        out = self.hook('Done.\n\n::nextsteps{multi="1" q1="Push it" q2="Tag it" q3="Leave as it is"}')
        self.assertIn('alt="1,3|2,3"', out)

    def test_two_actions_alone_are_left_alone(self):
        out = self.hook('Done.\n\n::nextsteps{multi="1" q1="Push it" q2="Tag it"}')
        self.assertNotIn('alt=', out)

    def test_the_models_own_groups_survive(self):
        out = self.hook('Done.\n\n::nextsteps{alt="1,2" multi="1" q1="Push it" q2="Tag it" q3="Leave it"}')
        self.assertIn('alt="1,2|1,3|2,3"', out)

    def test_a_reply_without_chips_is_untouched(self):
        out = self.hook("Just prose, no options.")
        self.assertIsNone(out)

    def test_a_deferral_in_the_middle_is_moved_to_the_end(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        out = ctx.hooks["transform_llm_output"](
            response_text='Done.\n\n::nextsteps{alt="1,3" multi="1" q1="Force-push it" q2="Leave it as it is" q3="Delete the tag"}',
            platform="local",
            session_id="s1",
        )
        self.assertIn('q1="Force-push it"', out)
        self.assertIn('q2="Delete the tag"', out, "the two actions sit together")
        self.assertIn('q3="Leave it as it is"', out, "and the deferral closes the row")


class RiskyRuleTest(unittest.TestCase):
    """The pill is opt-in in both directions: no setting, no mark, whatever the model wrote."""

    def test_a_mark_is_stripped_when_the_setting_is_off(self):
        ctx = FakeCtx()
        plugin.register(ctx)
        out = ctx.hooks["transform_llm_output"](
            response_text='Done.\n\n::nextsteps{risky="2" multi="1" q1="Tag it" q2="Force-push"}',
            platform="local",
            session_id="s1",
        )
        self.assertNotIn("risky", out)

    def test_a_mark_survives_when_the_setting_is_on(self):
        ctx = FakeCtx(settings={"flag_risky": True})
        plugin.register(ctx)
        out = ctx.hooks["transform_llm_output"](
            response_text='Done.\n\n::nextsteps{risky="2" multi="1" q1="Tag it" q2="Force-push"}',
            platform="local",
            session_id="s1",
        )
        self.assertIn('risky="2"', out)

    def test_the_rule_explains_the_mark_only_when_it_is_on(self):
        off = FakeCtx()
        plugin.register(off)
        off_section = off.sections[0][1]({"platform": "local"})
        self.assertNotIn("RISKY", off_section)

        on = FakeCtx(settings={"flag_risky": True})
        plugin.register(on)
        on_section = on.sections[0][1]({"platform": "local"})
        self.assertIn("RISKY", on_section)
        self.assertIn("risk=true", on_section)

    def test_the_rule_stays_the_same_length_off_desktop(self):
        ctx = FakeCtx(settings={"flag_risky": True})
        plugin.register(ctx)
        self.assertNotIn("RISKY", ctx.sections[0][1]({"platform": "telegram"}))

if __name__ == "__main__":
    unittest.main()
