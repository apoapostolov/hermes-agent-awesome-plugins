"""The plugin's own system-prompt section: end a choice with chips, not prose.

Hermes freezes it into each new session's prompt under "## Plugin Context: <name>".
The section is told the session's platform: Hermes Desktop gets the chip rule, every
other surface (Telegram, the CLI, ...) is told to offer a numbered list instead,
because a raw ::nextsteps line would arrive as text there.

On the Desktop the rule prefers the `next_steps` tool: the options travel as
arguments, so nothing has to be escaped and an invalid option is caught before it
reaches the reply. The directive form stays documented as the fallback, because a
model without tool calling still has to be able to produce chips.

When a decision classifier is available the rule also says to ask it which options
are worth taking now, so the reply arrives with the likely steps already picked
instead of making the user read five chips first.
"""

from __future__ import annotations

# Surfaces where the desktop half draws the directive.
DRAWS = frozenset({"local", "desktop"})

MAX_CHARS = 2_200

DESKTOP = (
    "This chat draws Next Steps under a reply. When the next step is a choice, "
    "do not ask for it in prose: never end with \"say the word and I'll...\", "
    "\"want me to...?\", \"shall I...?\", a \"let me know\" line, or a list of things you "
    "could do next.\n"
    "Call next_steps with 2 to 5 imperative, specific options under 120 characters "
    "each, most likely first, and do not write any ::nextsteps line yourself: the "
    "plugin attaches the chips to the reply you are about to write. Chips are picked and "
    "sent together by default, so pass multi=false only when the options are exclusive, "
    "because a picked row lets the user send two contradicting steps as one message. "
    "When some options exclude each other but the rest can be combined, pass alternates "
    "as pairs of 1-based numbers, so a click clears its opposite instead of sending both: "
    "[[1, 3]] means options 1 and 3 cannot both be picked. An option that means leaving "
    "things as they are is opposed to every action, and that pairing is applied even when "
    "you pass nothing, so say it in the labels rather than the prose. "
    "Never offer an option you would not do as it stands.\n"
    "If you cannot call tools, end instead with this directive alone on its own line, one "
    "qN per option; add multi=\"0\" only for an exclusive choice, and alt=\"1,3\" for "
    "options that cannot be picked together while the rest can:\n"
    "::nextsteps{q1=\"Push the branch and open the PR\" q2=\"Add a CHANGELOG entry\"}\n"
    "Never put a directive inside a sentence, a list or a code block, and never write it "
    "twice. Put what you did in the prose; the chips carry what can follow."
)

OTHER = (
    "This surface cannot draw Next Steps, so never write a ::nextsteps directive "
    "and never call next_steps here. When offering next steps, end with a short "
    "numbered list of concrete options instead of an open question."
)

SUBTITLE = (
    " A chip can carry a second, dimmer line when the label alone would be misread: pass "
    "subtitles with the chips (one entry per option, empty where it needs none) or dN on "
    "the directive. Say what the step touches or what a bare verb hides, never what the "
    "label already says, and leave it out when the option is already clear: a line under "
    "every chip is noise, and it is clipped at two lines anyway."
)

RISK = (
    " Mark the options that could do damage rather than just cost time: deleting or "
    "overwriting something, rewriting published history, spending money, running a "
    "migration, or a change that could break a working setup. Pass risk=true with the "
    "chips, or risky=\"2\" on the directive, so those chips carry a RISKY pill; a step "
    "that is merely slow or incomplete is not risky."
)

RECOMMEND = (
    " When the chips are a real choice rather than an obvious next step, pass "
    "recommend=true so the decision classifier marks the options worth taking now; they "
    "carry a Recommended tag and start out picked, so recommend only options you would "
    "be happy for the user to send as they stand. On the text-directive path, "
    "next_steps_recommend returns the same verdict as an attribute to paste (rec=\"1,3\")."
)


def chips_rule(session: dict, recommends: bool = False, risk: bool = False) -> str:
    """The section's text for one session: the chip rule on the app, text-only elsewhere.

    {"platform": "local"} → DESKTOP;  with a classifier → DESKTOP + RECOMMEND;
    {"platform": "telegram"} → OTHER;  {} → OTHER
    """
    session = session or {}
    if session.get("platform") in DRAWS:
        return DESKTOP + SUBTITLE + (RECOMMEND if recommends else "") + (RISK if risk else "")
    return OTHER
