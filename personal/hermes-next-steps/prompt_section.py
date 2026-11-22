"""The plugin's own system-prompt section: end a choice with chips, not prose.

Hermes freezes it into each new session's prompt under "## Plugin Context: <name>".
The section is told the session's platform: Hermes Desktop gets the chip rule, every
other surface (Telegram, the CLI, ...) is told to offer a numbered list instead,
because a raw ::nextsteps line would arrive as text there.

On the Desktop the rule prefers the `next_steps` tool: the options travel as
arguments, so nothing has to be escaped and an invalid option is caught before it
reaches the reply. The directive form stays documented as the fallback, because a
model without tool calling still has to be able to produce chips. A reply that asks
several points separately can set answer=true: its options become labelled reply
fields instead of chips.

When a decision classifier is available the rule also says to ask it which options
are worth taking now, so the reply arrives with the likely steps already picked
instead of making the user read five chips first.

Hermes skips a plugin section longer than its own cap instead of truncating it, and
the cap is applied to the text, not to the `max_chars` a plugin declares. So the fit
is enforced here: MAX_CHARS sits under the host's 2,200, and `_fit` drops optional
paragraphs rather than letting a section grow past it and be lost whole.
"""

from __future__ import annotations

# Surfaces where the desktop half draws the directive.
DRAWS = frozenset({"local", "desktop"})

# Kept under the host's 2,200 cap so the whole section survives, and used as the
# declared max_chars on registration.
MAX_CHARS = 2_100

DESKTOP = (
    "\n"
    "This chat draws Next Steps under a reply. When the next step is a choice, never ask in prose: no \"say the word\", \"want me to...?\", \"shall I...?\" or a list of options. Call next_steps with 2 to 5 imperative options under 120 characters, most likely first; write no ::nextsteps line: the chips attach to the reply. Several chips can be picked together, so pass multi=false only when options are exclusive. Pass alternates as 1-based pairs ([[1, 3]] means 1 and 3 exclude each other); an option meaning \"leave things as they are\" opposes every action, so say it in a label. Never offer an option you would not do. Without tool calls, end with this line alone, one qN per option, multi=\"0\" when exclusive, alt=\"1,3\" for conflicts:\n"
    "::nextsteps{q1=\"Push the branch and open the PR\" q2=\"Add a CHANGELOG entry\"}\n"
    "Never put a directive in a sentence, list or code block, never write it twice, and never follow it with a tool call or JSON. The prose says what you did; the chips carry what follows."
)

# A different reply shape: the user has to answer the points, not pick one. It is an
# opt-in mode, so it sits beside the chip rule rather than replacing it.
ANSWER = (
    "\n"
    "When the reply asks the user to answer several points separately, pass answer=true: each option becomes a labelled reply field, and answers are sent back as numbered item: answer lines. Use it for questions, not choices."
)

OTHER = (
    "This surface cannot draw Next Steps, so never write a ::nextsteps directive "
    "and never call next_steps here. When offering next steps, end with a short "
    "numbered list of concrete options instead of an open question."
)

SUBTITLE = (
    "\n"
    " A chip can carry a dimmer second line when its label would misread: pass subtitles (one per option, empty where none is needed) or dN. Say what the step touches that the label hides, never what the label already says, and leave it out when the option is clear: a line under every chip is noise."
)

RISK = (
    "\n"
    " Mark options that could do damage rather than cost time: deleting or overwriting something, rewriting published history, spending money, a migration, or a change that could break a working setup. Pass risk=true, or risky=\"2\" on the directive, for the RISKY pill."
)

RECOMMEND = (
    "\n"
    " When the chips are a real choice, pass recommend=true so the classifier marks the options worth taking now: they start picked, so recommend only what you would send as it stands. On the directive path call next_steps_recommend and write its numbers as rec=\"1,3\"; never a recommend attribute or a JSON block."
)


def _fit(parts: list[str]) -> str:
    """Join the paragraphs, dropping optional ones until the section fits MAX_CHARS.

    Order is priority: the descriptions that make the features reachable go last, so
    a section that has to shrink keeps the rule that makes chips appear at all.
    """
    while len(parts) > 1 and len("".join(parts)) > MAX_CHARS:
        parts = parts[:-1]
    return "".join(parts)


def chips_rule(session: dict, recommends: bool = False, risk: bool = False) -> str:
    """The section's text for one session: the chip rule on the app, text-only elsewhere.

    {"platform": "local"} -> DESKTOP;  with a classifier -> DESKTOP + RECOMMEND;
    {"platform": "telegram"} -> OTHER;  {} -> OTHER
    """
    session = session or {}
    if session.get("platform") not in DRAWS:
        return OTHER
    parts = [DESKTOP, ANSWER, SUBTITLE]
    if recommends:
        parts.append(RECOMMEND)
    if risk:
        parts.append(RISK)
    return _fit(parts)


def prompt_texts() -> list[tuple[str, str]]:
    """Every shape this section can take, for the pack's admission check.

    Hermes measures the section against its own cap and skips an oversized one instead
    of truncating it, so a size that grows past the cap costs the whole rule. Publishing
    the variants lets scripts/admission_check.py fail a release instead of a session.
    """
    return [
        ("desktop", chips_rule({"platform": "local"}, False, False)),
        ("desktop+recommend", chips_rule({"platform": "local"}, True, False)),
        ("desktop+risk", chips_rule({"platform": "local"}, False, True)),
        ("desktop+recommend+risk", chips_rule({"platform": "local"}, True, True)),
        ("other surfaces", chips_rule({"platform": "telegram"}, False, False)),
    ]
