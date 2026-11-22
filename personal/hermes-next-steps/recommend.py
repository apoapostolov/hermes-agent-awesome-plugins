"""Which of the offered next steps are worth doing now, from the decision classifier.

This module is the optional part of the plugin. The classifier is the `nerve`
plugin's `nerve_assess` tool (the older native `jev_assess` contract is accepted
too); without that plugin nothing here runs, no `rec` attribute is written, and the
chips render unmarked while everything else keeps working. Nothing in this module
is imported by the renderer, and nothing about the directive depends on it.

One `nerve_assess` call carries a question per option (up to 16 typed questions on
one shared state), so five options still cost one provider call of 200-350 ms.

The payload gives the classifier what it cannot see on its own: the state lists the
candidates numbered, and every question names the other options. A candidate that is
an *alternative* to another cannot be judged in isolation, because "take it now" is
true of only one of a pair that shares a goal, contradicts itself, or differs only in
when it happens. A candidate that means taking none of the others is the same problem
in a sharper form: taking a step and taking no step cannot both be right.

The policy is code, not a prompt. An option is recommended when it clears
`MIN_TAKE_NOW` and beats both other labels, and three rules keep the result sane:

- a "take none of these" option is never recommended beside another option, and only
  when it is preferred over every other option;
- every option clearing the bar is not a recommendation, so the weakest is left out;
- at most `MAX_RECOMMENDED` survive, strongest first.

No model is involved in the decision: labels in, indexes out. Nothing is
recommended when no classifier answers, and the directive stays valid without a
`rec` attribute.
"""

from __future__ import annotations

import json

# The classifier tools, in the order they are tried. `nerve_assess` is the name the
# nerve plugin registers; `jev_assess` is the older native name of the same contract.
RANKERS = ("nerve_assess", "jev_assess")

RISKY = "risky"
SAFE = "safe"
# A marked step tells the user to be careful, so the bar is high: a coin toss is
# not a warning, and a pill on every second chip is noise rather than advice.
MIN_RISKY = 0.6

TAKE_NOW = "take it now"
LATER = "later"
SKIP = "skip"

# More likely than not: a candidate the distribution prefers over later-or-skip.
MIN_TAKE_NOW = 0.5
# Three marked chips is a recommendation; five marked chips is a wall of orange.
MAX_RECOMMENDED = 3
MAX_OPTIONS = 6

DEFAULT_STATE = "The assistant just finished a reply and is offering the user a few next steps."

# Options that mean "take none of these", waiting included: pushing now and waiting
# for review are one decision at two times, so they are alternatives and not
# companions. Substring matching on purpose, because these are chip labels written by
# a model, not prose to parse.
NONE_MARKERS = (
    "none of the",
    "none of these",
    "none of them",
    "none at all",
    "nothing",
    "neither",
    "do nothing",
    "no action",
    "skip",
    "not now",
    "not yet",
    "hold off",
    "wait",
    "defer",
    "postpone",
    "leave it",
    "leave that",
    "leave as",
    "as it is",
    "keep as",
    "keep it",
    "no change",
    "unchanged",
    "status quo",
    "don't",
    "do not",
    "later",
    "tomorrow",
    "not worth",
)

ANSWER_INSTRUCTIONS = (
    "Judge this candidate on its own: more than one can deserve to be taken now. But when "
    "another option is an alternative to it, meaning a different route to the same goal, its "
    "opposite, or the same step at another time, then only one of that pair can be taken: the "
    "one that defers, waits or undoes the other is not 'take it now' unless the user clearly "
    "prefers it. Do not mark two alternatives both."
)

RISK_INSTRUCTIONS = (
    "Judge only the chance of harm from taking this step: damage to files, data or a "
    "working setup; broken builds or tests; new bugs; spending money; or a mess that needs "
    "its own cleanup afterwards. A step that is merely slow, tedious or incomplete is not "
    "risky. Reversibility counts: a step that can be undone in one command is not the same "
    "as one that cannot be undone at all."
)

RISK_CRITERIA = {
    RISKY: "Taking it could damage something, break something that works, cost money, or leave a mess that needs its own fix.",
    SAFE: "Taking it is contained or reversible; if it goes wrong, nothing else is harmed.",
}

NONE_INSTRUCTIONS = (
    "This candidate means taking none of the others. It earns 'take it now' only when the user "
    "would rather not act, or would rather wait, than take any of the other options here."
)

CRITERIA = {
    TAKE_NOW: "The user would want this next step taken immediately.",
    LATER: "Reasonable, but not the thing to do next.",
    SKIP: "Not wanted.",
}


def is_none_option(option: object) -> bool:
    """Does this option mean "take none of these", a deferral included?"""
    text = " " + str(option or "").casefold() + " "
    return any(marker in text for marker in NONE_MARKERS)


def alternate_groups(options: list[str]) -> list[list[int]]:
    """The alternate pairs a decision implies by itself.

    An option that means "take none of these" is the alternative to every action,
    not the companion of one: ticking it must clear them, and ticking any of them
    must clear it. Two actions are never alternates of each other unless the model
    says so, which is why this returns pairs rather than one group holding
    everything. The numbers are 1-based, the same numbering the chips show.
    """
    numbers = list(range(1, len(options) + 1))
    deferrals = [number for number, option in zip(numbers, options) if is_none_option(option)]
    if not deferrals:
        return []
    actions = [number for number in numbers if number not in deferrals]
    groups: list[list[int]] = [
        sorted([deferral, action]) for deferral in deferrals for action in actions
    ]
    if len(deferrals) > 1:
        groups.append(sorted(deferrals))
    return groups


def state_for(options: list[str], context: str = "") -> str:
    """The shared state: the goal, then every candidate numbered as the chips show them."""
    goal = str(context or "").strip() or DEFAULT_STATE
    numbered = "\n".join("%d. %s" % (index + 1, option) for index, option in enumerate(options))
    return (
        "%s\n\nThe candidate next steps, numbered as the chips will show them:\n%s\n\n"
        "Several candidates can be worth taking now, but two that are alternatives cannot both "
        "be: a different route to the same goal, the opposite of another, or the same step at "
        "another time. A candidate that means taking none of the others is only worth taking "
        "when it is preferred over all of them, and never beside one of them." % (goal, numbered)
    )


def questions(options: list[str]) -> dict[str, dict]:
    """One typed question per option, keyed by its chip number, each naming its siblings.

    ["Push it", "Tag it"] → {"q1": {"type": "choice", "instructions": "Option 1 of 2: Push it…
    The other options: 2 (Tag it)…", "criteria": {"take it now": …, "later": …, "skip": …}}, …}
    """
    count = len(options)
    out: dict[str, dict] = {}
    for index, option in enumerate(options):
        others = ["%d (%s)" % (other + 1, options[other]) for other in range(count) if other != index]
        lines = [
            "Option %d of %d: %s" % (index + 1, count, option),
            "The other options: %s" % ("; ".join(others) if others else "none"),
            ANSWER_INSTRUCTIONS,
        ]
        if is_none_option(option):
            lines.append(NONE_INSTRUCTIONS)
        out["q%d" % (index + 1)] = {
            "type": "choice",
            "instructions": "\n".join(lines),
            "criteria": dict(CRITERIA),
        }
    return out


def risk_state_for(options: list[str], context: str = "") -> str:
    """The shared state for a risk pass: the goal, then the candidates numbered."""
    goal = str(context or "").strip() or DEFAULT_STATE
    numbered = "\n".join("%d. %s" % (index + 1, option) for index, option in enumerate(options))
    return (
        "%s\n\nThe candidate next steps, numbered as the chips will show them:\n%s\n\n"
        "Several candidates can be safe. Judge each one separately for what it could break."
        % (goal, numbered)
    )


def risk_questions(options: list[str]) -> dict[str, dict]:
    """One typed risk question per option, each naming its siblings."""
    count = len(options)
    out: dict[str, dict] = {}
    for index, option in enumerate(options):
        others = ["%d (%s)" % (other + 1, options[other]) for other in range(count) if other != index]
        lines = [
            "Option %d of %d: %s" % (index + 1, count, option),
            "The other options: %s" % ("; ".join(others) if others else "none"),
            RISK_INSTRUCTIONS,
        ]
        out["q%d" % (index + 1)] = {
            "type": "choice",
            "instructions": "\n".join(lines),
            "criteria": dict(RISK_CRITERIA),
        }
    return out


def _ask_risk(dispatch, clean: list[str], context: str) -> dict | None:
    args = {"state": risk_state_for(clean, context), "questions": risk_questions(clean)}
    for name in RANKERS:
        try:
            answers = _answers_from(dispatch(name, args))
        except Exception:  # a missing classifier costs the pill, never the reply
            continue
        if answers:
            return answers
    return None


def risky_picks(dispatch, options: list[str], context: str = "") -> list[int]:
    """The 1-based options whose risk clears the bar, empty when none or no classifier.

    A pill that says "be careful" has to mean it: the risky verdict is only used when
    it clears MIN_RISKY and beats its own safe reading, so a split answer marks
    nothing rather than warning about everything.
    """
    clean = [str(option).strip() for option in options if str(option).strip()][:MAX_OPTIONS]
    if len(clean) < 2:
        return []
    answers = _ask_risk(dispatch, clean, context)
    if not answers:
        return []
    out: list[int] = []
    for index in range(len(clean)):
        question = answers.get("q%d" % (index + 1))
        risk = _probabilities(question, RISKY)
        safe = _probabilities(question, SAFE)
        if risk is None or risk < MIN_RISKY:
            continue
        if safe is not None and safe >= risk:
            continue
        out.append(index + 1)
    return out


def _probabilities(answer: object, label: str) -> float | None:
    if not isinstance(answer, dict):
        return None
    probabilities = answer.get("probabilities")
    if not isinstance(probabilities, dict):
        return None
    value = probabilities.get(label)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def scored(answers: dict, count: int) -> list[tuple[float, int]]:
    """(probability, index) for every option the classifier had an opinion on, best first."""
    out: list[tuple[float, int]] = []
    for index in range(count):
        probability = _probabilities(answers.get("q%d" % (index + 1)), TAKE_NOW)
        if probability is not None:
            out.append((probability, index))
    out.sort(key=lambda pair: (-pair[0], pair[1]))
    return out


def _beats_the_alternatives(answers: dict, index: int) -> bool:
    """Take-it-now has to beat 'later' and 'skip', not merely clear the bar.

    A 0.51 beside a 0.49 skip is a coin toss dressed as a verdict, and marking it
    picks a fight with the classifier's own second choice.
    """
    question = answers.get("q%d" % (index + 1))
    now = _probabilities(question, TAKE_NOW)
    if now is None:
        return False
    for label in (LATER, SKIP):
        other = _probabilities(question, label)
        if other is not None and other >= now:
            return False
    return True


def _without_none_conflict(
    keep: list[int], scores: dict[int, float], options: list[str], count: int
) -> list[int]:
    """A "take none of these" option is never recommended beside another option.

    It is also only recommended when it is preferred over every other option: if any
    action scores at least as high, the action is the answer and the none option is
    dropped, because taking a step and taking no step cannot both be right.
    """
    none_indexes = [index for index in keep if is_none_option(options[index])]
    if not none_indexes:
        return keep
    best_none = max(none_indexes, key=lambda index: (scores[index], -index))
    actions = [index for index in range(count) if not is_none_option(options[index])]
    if not actions:
        return [best_none]
    best_action = max((scores[index] for index in actions if index in scores), default=None)
    if best_action is None or scores[best_none] > best_action:
        return [best_none]
    return [index for index in keep if index not in none_indexes]


def _never_everything(keep: list[int], scores: dict[int, float], count: int) -> list[int]:
    """Every option clearing the bar is not a recommendation: leave the weakest out.

    Asking a person to do all of it says the reply offered no real choice, and with
    two options it reduces to "do both of these".
    """
    if count < 2 or len(keep) < count:
        return keep
    weakest = min(keep, key=lambda index: (scores[index], -index))
    return [index for index in keep if index != weakest]


def picks(answers: dict, count: int, options: list[str] | None = None) -> list[int]:
    """The indexes to recommend, ascending, at most MAX_RECOMMENDED.

    Options are needed for the "none of the above" rule, because it is the wording
    that says what an option means. Without them the arithmetic still applies.

    Three options at 0.81 / 0.79 / 0.77 → the strongest two, because recommending all
    three is not a recommendation. An 0.91 favourite over 0.04s → [0]. Nothing at or
    above 0.5 → [].
    """
    if not isinstance(answers, dict) or count <= 0:
        return []
    scores = {index: probability for probability, index in scored(answers, count)}
    keep = [
        index
        for index in range(count)
        if scores.get(index) is not None
        and scores[index] >= MIN_TAKE_NOW
        and _beats_the_alternatives(answers, index)
    ]
    if options:
        keep = _without_none_conflict(keep, scores, options, count)
    keep = _never_everything(keep, scores, count)
    keep.sort(key=lambda index: (-scores[index], index))
    return sorted(keep[:MAX_RECOMMENDED])


def _notes(options: list[str], answers: dict, recommended: list[int]) -> list[str]:
    """One line per rule that changed the answer, so the model can see why."""
    count = len(options)
    scores = {index: probability for probability, index in scored(answers, count)}
    notes: list[str] = []
    kept_none = [index for index in recommended if is_none_option(options[index])]
    if kept_none:
        notes.append(
            "Option %s means taking none of these and is preferred over every other option, so "
            "it is marked alone." % ", ".join(str(index + 1) for index in kept_none)
        )
    dropped_none = [
        index
        for index in range(count)
        if is_none_option(options[index])
        and index not in recommended
        and scores.get(index, 0) >= MIN_TAKE_NOW
    ]
    if dropped_none:
        notes.append(
            "Option %s means taking none of these, and an action is preferred, so it stays out."
            % ", ".join(str(index + 1) for index in dropped_none)
        )
    if count >= 2 and len(scores) == count and all(s >= MIN_TAKE_NOW for s in scores.values()):
        if len(recommended) < count:
            notes.append(
                "Every option cleared the bar, so the weakest is left out: recommending all of "
                "them is not a recommendation."
            )
    return notes


def reply(options: list[str], answers: dict) -> str:
    """What the model reads: the attribute to write, or why there is none."""
    count = len(options)
    recommended = picks(answers, count, options)
    if not recommended:
        text = "No option reached %.2f on take-it-now, so leave rec out of the directive." % MIN_TAKE_NOW
        best = scored(answers, count)
        if best:
            # Say how close it was: a model told "1 was 0.42" can offer different
            # options next time, where a bare refusal teaches it nothing.
            text += " The highest was %d at %.2f." % (best[0][1] + 1, best[0][0])
        return text
    by_index = {index: probability for probability, index in scored(answers, count)}
    numbers = ",".join(str(index + 1) for index in recommended)
    detail = ", ".join("%d (%.2f)" % (index + 1, by_index[index]) for index in recommended)
    text = 'Recommended %d of %d: %s. Write rec="%s" into the directive.' % (
        len(recommended),
        count,
        detail,
        numbers,
    )
    notes = _notes(options, answers, recommended)
    return text + " " + " ".join(notes) if notes else text


def _answers_from(result: object) -> dict | None:
    """The answers map out of a dispatch result, which arrives as a JSON string."""
    payload = result
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError):
            return None
    if not isinstance(payload, dict):
        return None
    if payload.get("ok") is False:
        return None
    answers = payload.get("answers")
    return answers if isinstance(answers, dict) and answers else None


def _ask(dispatch, clean: list[str], context: str) -> dict | None:
    """One classifier call: the answers map, or None when no ranker answered."""
    args = {
        "state": state_for(clean, context),
        "questions": questions(clean),
    }
    for name in RANKERS:
        try:
            answers = _answers_from(dispatch(name, args))
        except Exception:  # a missing or broken classifier is not a reply failure
            continue
        if answers:
            return answers
    return None


def picks_for(dispatch, options: list[str], context: str = "") -> list[int]:
    """The 1-based option numbers worth taking now, empty when nothing clears.

    The same policy as :func:`recommend`, without the sentence meant for a model: a
    tool that draws its own chips needs the numbers, not the instruction to write
    them into a directive.
    """
    clean = [str(option).strip() for option in options if str(option).strip()][:MAX_OPTIONS]
    if len(clean) < 2:
        return []
    answers = _ask(dispatch, clean, context)
    if not answers:
        return []
    return [index + 1 for index in picks(answers, len(clean), clean)]


def recommend(dispatch, options: list[str], context: str = "") -> str:
    """Ask the classifier, through `dispatch(tool_name, args)`, and phrase the answer.

    `dispatch` is ctx.dispatch_tool: it returns the handler's JSON string and may raise.
    """
    clean = [str(option).strip() for option in options if str(option).strip()]
    if len(clean) < 2:
        return "A recommendation needs at least two options; leave rec out."
    clean = clean[:MAX_OPTIONS]
    answers = _ask(dispatch, clean, context)
    if answers:
        return reply(clean, answers)
    return (
        "No decision classifier answered (%s), so leave rec out and offer the chips as they are."
        % ", ".join(RANKERS)
    )


NEXT_STEPS_RECOMMEND_SCHEMA = {
    "name": "next_steps_recommend",
    "description": (
        "Ask the decision classifier which of the next steps you are about to offer are worth "
        "taking now, for the rec attribute of a ::nextsteps directive. Returns the 1-based option "
        "numbers that cleared the threshold, which can be more than one when several steps belong "
        "together. It never marks two alternatives at once, never marks a 'none of these' option "
        "beside an action, and never marks every option. Call it before writing the directive when "
        'the chips are a real choice, then write rec="<numbers>" into it exactly as returned; if '
        "it says nothing cleared, leave rec out."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": MAX_OPTIONS,
                "description": "The chips' option texts, in the order they will appear.",
            },
            "context": {
                "type": "string",
                "description": (
                    "One sentence on what the user asked for and what the reply just did. The "
                    "classifier judges every option against this, so name the goal."
                ),
            },
        },
        "required": ["options"],
    },
}


def handler(dispatch):
    """The tool handler: params in, the classifier's verdict out."""

    def next_steps_recommend(params: dict, **kwargs) -> str:
        del kwargs
        options = params.get("options") if isinstance(params, dict) else None
        if isinstance(options, str):
            options = options.split("\n")
        if not isinstance(options, list):
            return "next_steps_recommend needs an options array of at least two strings."
        return recommend(dispatch, options, str((params or {}).get("context") or ""))

    return next_steps_recommend
