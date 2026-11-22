"""hermes-next-steps: clickable Next Steps, the rule that fills them, and the picker.

The desktop half (desktop/plugin.js) draws a `::nextsteps{…}` paragraph as chips
under a reply. This half gives the model two ways to fill it: `next_steps`
registers the options as tool arguments and the reply hook appends the directive,
which needs no escaping and cannot be malformed, while the bundled prompt rule keeps
the text directive as the fallback for a model that cannot call tools. It also
converts a closing offer written in prose anyway (opt-in), and exposes
`next_steps_recommend`, which asks the decision classifier which of the options are
worth taking now so the chips arrive pre-picked.

Both halves are optional: the plugin works as a single file dropped into
desktop-plugins/, where the model emits the directive on its own.
"""

from __future__ import annotations

from .chips import NEXT_STEPS_SCHEMA, PENDING, attach, handler as chips_handler
from .offers import (
    directive_options,
    rewrite,
    stamp_accent,
    stamp_alternates,
    stamp_carry,
    stamp_multi,
    stamp_session,
    stamp_steer,
    reorder_alternates,
    strip_recommend_attribute,
    strip_risky,
)
from .prompt_section import MAX_CHARS, chips_rule
from .stray import strip_call
from .recommend import (
    NEXT_STEPS_RECOMMEND_SCHEMA,
    alternate_groups,
    is_none_option,
    risky_picks,
    handler as recommend_handler,
    picks_for,
)

NAME = "hermes-next-steps"
TOOLSET = NAME.replace("-", "_")
SETTING = "auto_offers"
RECOMMEND_SETTING = "auto_recommend"
ACCENT_SETTING = "accent_recommended"
CARRY_SETTING = "carry_over"
STEER_SETTING = "send_as_steer"
RISK_SETTING = "flag_risky"
# Plugins that register the decision classifier (`nerve_assess`, or the older
# `jev_assess` name of the same contract).
RANKER_PLUGINS = ("nerve", "jev")


def offer_hook(response_text: str = "", platform: str = "", auto_offers: bool = False) -> str | None:
    """The reply with its closing offer drawn as chips, or None to leave it alone.

    Off by default: a hook that rewrites replies is opt-in, and the prompt section
    already asks for the directive.
    """
    if not auto_offers or not isinstance(response_text, str):
        return None
    return rewrite(response_text, platform=platform)


def has_ranker(ctx) -> bool:
    """Whether a decision classifier plugin is loaded. Advisory: the tool degrades on its own."""
    for plugin_id in RANKER_PLUGINS:
        try:
            if ctx.has_plugin(plugin_id):
                return True
        except Exception:
            continue
    return False


def _config(ctx, key: str, default):
    try:
        return ctx.get_config(key, default)
    except Exception:  # an unreadable setting store must not break registration
        return default


def section_text(session: dict, recommends: bool = False, risk: bool = False) -> str:
    """The prompt section for one session (the section is a callable, so this runs per session)."""
    return chips_rule(session, recommends=recommends, risk=risk)


def register(ctx) -> None:
    # The section is rendered when a session starts, not when the plugin loads, so
    # the classifier probe runs there: plugins register in dependency order and
    # `hermes-next-steps` loads before `nerve`, which made an eager probe always False.
    # The setting is read in the same place, so a toggle applies to the next session.
    def section(session):
        recommends = bool(_config(ctx, RECOMMEND_SETTING, True)) and has_ranker(ctx)
        risk = bool(_config(ctx, RISK_SETTING, False))
        return section_text(session, recommends=recommends, risk=risk)

    ctx.register_system_prompt_section(NAME, section, max_chars=MAX_CHARS)

    ctx.register_tool(
        name="next_steps_recommend",
        toolset=TOOLSET,
        schema=NEXT_STEPS_RECOMMEND_SCHEMA,
        handler=recommend_handler(ctx.dispatch_tool),
        description=(
            "Rank the next steps you are about to offer, for the rec attribute of the chips. "
            "Optional: it needs the nerve classifier plugin, and without one it answers "
            "'leave rec out' so the chips simply go unmarked."
        ),
        emoji="🎯",
    )

    # The structured channel: the model passes the options as arguments and the hook
    # below appends the directive to the reply it is about to write. Reading settings
    # and probing the classifier happen per call, because plugins register in
    # dependency order and this one loads before the classifier does.
    def wants_recommend() -> bool:
        return bool(_config(ctx, RECOMMEND_SETTING, True)) and has_ranker(ctx)

    def classify(options, context_line):
        return picks_for(ctx.dispatch_tool, options, context_line)

    # The risky pill is opt-in, read per call like every other setting, and it needs a
    # classifier: without one nothing is marked, because a guess about damage is worse
    # than no warning at all.
    def wants_risk() -> bool:
        return bool(_config(ctx, RISK_SETTING, False)) and has_ranker(ctx)

    def classify_risk(options, context_line):
        return risky_picks(ctx.dispatch_tool, options, context_line)

    ctx.register_tool(
        name="next_steps",
        toolset=TOOLSET,
        schema=NEXT_STEPS_SCHEMA,
        handler=chips_handler(
            PENDING, ctx.dispatch_tool, classify, wants_recommend, classify_risk, wants_risk
        ),
        description=(
            "Register the chips under the reply you are about to write, instead of writing "
            "a ::nextsteps directive. Options are validated; the chips attach to that reply "
            "automatically, and recommend=true marks the ones worth taking now."
        ),
        emoji="🧩",
    )

    def transform(
        response_text: str = "", platform: str = "", session_id: str = "", **kwargs
    ) -> str | None:
        """Six jobs: five gated by their own rule and read per call, one repair that always runs.

        - next_steps: a registration from the tool becomes the reply's directive.
        - auto_offers: a closing offer written in prose becomes a directive.
        - accent_recommended off: the directive gets accent="0", because the
          renderer cannot read plugin settings and the default is accented.
        - carry_over on: the directive gets carry="1", and a reply with no chips
          gets one empty block so its message still shows the unanswered ones.
        - always: pickability for two or more chips, and the chat fingerprint, so a
          chat only ever carries its own proposals.
        - always: a classifier call a model printed as a JSON block, and the tool's
          argument name written into the directive as `recommend=`, are removed
          (see stray.py): neither is text to show, and neither is the classifier's
          answer.

        The tool's chips are attached before the stamps run, so the directive they
        produce picks up the accent and carry attributes exactly like a written one.
        A reply that already carries a directive keeps it; the registration is
        dropped rather than doubling the block.
        """
        del kwargs
        if not isinstance(response_text, str) or not response_text:
            PENDING.forget(session_id)
            return None
        try:
            auto_offers = bool(ctx.get_config(SETTING, False))
        except Exception:  # an unreadable setting must not break a reply
            auto_offers = False
        try:
            accent = bool(ctx.get_config(ACCENT_SETTING, True))
        except Exception:
            accent = True
        try:
            carry = bool(ctx.get_config(CARRY_SETTING, False))
        except Exception:
            carry = False
        try:
            steer = bool(ctx.get_config(STEER_SETTING, False))
        except Exception:
            steer = False
        # Model noise first, so everything below reads a clean directive.
        changed = strip_recommend_attribute(strip_call(response_text))
        if auto_offers:
            converted = offer_hook(response_text=changed, platform=platform, auto_offers=True)
            if converted:
                changed = converted
        attached = attach(changed, session_id, platform=platform, pending=PENDING)
        if attached:
            changed = attached
        # Pickability is the default for two or more chips: writing it into the
        # directive means a renderer from before this rule agrees with a new one.
        # Unconditional, so it cannot sit behind an early return for the settings.
        changed = stamp_multi(changed)
        # The decision implies some exclusions by itself (an option that means
        # "take none of these" is the alternative to every action), so that rule is
        # applied to whatever the reply carries, model-written groups included.
        if not _config(ctx, RISK_SETTING, False):
            changed = strip_risky(changed)
        options = directive_options(changed)
        if options:
            enforced = alternate_groups(options)
            if enforced:
                changed = stamp_alternates(changed, enforced, len(options))
            # Alternates belong next to each other, and the option that means "leave it"
            # closes the row: a reader should not have to hunt for the route a chip replaces.
            deferrals = [n for n, label in enumerate(options, start=1) if is_none_option(label)]
            changed = reorder_alternates(changed, deferrals)
        if steer:
            changed = stamp_steer(changed)
        if not accent:
            changed = stamp_accent(changed, "0")
        if carry:
            changed = stamp_carry(changed, platform=platform)
        # The chat id goes in last, so the empty block carry may have added is
        # named as well: a block without a session is how proposals leaked.
        changed = stamp_session(changed, session_id)
        return changed if changed != response_text else None

    ctx.register_hook("transform_llm_output", transform)
