"""Chips registered by a tool call, instead of parsed out of the reply text.

The directive-in-text route works with any model that can write text, and it keeps
working: this module adds a second, structured channel beside it.

A model writing `::nextsteps{q1="Fix the \"broken\" build"}` by hand has to escape
quotes, keep braces balanced, remember `multi` and `rec`, and never wrap it in a
sentence. A model calling `next_steps(options=[...])` passes a JSON array: the
arguments are validated on the way in, nothing needs escaping, and the chips are
registered for the reply that is about to be written. The `transform_llm_output`
hook, which already rewrites the reply for the accent and carry settings, appends
the directive from that registration, so the model's prose stays prose.

The text directive still wins when both arrive: a model that wrote one clearly meant
it, and two chip blocks under one reply would be a puzzle.
"""

from __future__ import annotations

import re
import threading
import time

try:  # the plugin loads this as a package; the test suite imports it top-level
    from .offers import (
    DRAWS,
    DIRECTIVE_RE,
    alternate_attribute,
    directive,
    merge_alternates,
    parse_subtitles,
)
except ImportError:
    from offers import (
    DRAWS,
    DIRECTIVE_RE,
    alternate_attribute,
    directive,
    merge_alternates,
    parse_subtitles,
)

# The prompt asks for 2 to 5; the classifier payload takes up to 6. A chip row past
# six is a menu, and a menu under every reply is noise.
MAX_OPTIONS = 6
# One chip label. The renderer wraps long labels inside the pill, so this is a
# readability limit rather than a layout one: past 120 characters nobody reads it.
MAX_OPTION_CHARS = 120
# A registration belongs to the reply being written right now. If the turn dies
# before the hook runs, the entry is dropped instead of surfacing a turn later.
PENDING_TTL_SECONDS = 900.0

_WHITESPACE = re.compile(r"\s+")


def clean(options: object) -> list[str]:
    """Normalised option labels, or ValueError naming what is wrong.

    Accepts the tool's array or the newline-separated string a model sometimes sends.
    Order is preserved, blanks and case-insensitive duplicates are dropped, and every
    label is collapsed to single spaces so a fresh registration cannot smuggle a
    newline into the directive.
    """
    if isinstance(options, str):
        options = options.splitlines()
    if not isinstance(options, (list, tuple)):
        raise ValueError("options must be an array of 2 to 6 strings")
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in options:
        if not isinstance(raw, str):
            continue
        label = _WHITESPACE.sub(" ", raw).strip()
        if not label:
            continue
        if len(label) > MAX_OPTION_CHARS:
            label = label[: MAX_OPTION_CHARS - 1].rstrip() + "\u2026"
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(label)
    if len(cleaned) < 2:
        raise ValueError("a chip block needs at least 2 distinct non-empty options")
    return cleaned[:MAX_OPTIONS]


def implied_alternates(options: list[str]) -> list[list[int]]:
    """The groups a decision implies on its own, without a classifier."""
    try:
        from .recommend import alternate_groups
    except ImportError:  # loaded as a flat module in tests
        from recommend import alternate_groups
    return alternate_groups(options)


def rec_attribute(numbers: object, count: int) -> str:
    """The rec attribute from the classifier's numbers, ignoring anything out of range."""
    if not isinstance(numbers, (list, tuple)):
        return ""
    kept: list[int] = []
    for value in numbers:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 1 <= number <= count and number not in kept:
            kept.append(number)
    return ",".join(str(number) for number in kept)


class Pending:
    """One registration per session, consumed by the reply it belongs to.

    Session-keyed rather than global because the gateway serves several chats at
    once: a chip call in one session must never decorate a reply in another.
    """

    def __init__(self, ttl: float = PENDING_TTL_SECONDS, clock=time.monotonic) -> None:
        self._ttl = ttl
        self._clock = clock
        self._lock = threading.Lock()
        self._entries: dict[str, tuple[float, list[str], bool | None, str, str, str]] = {}

    def put(
        self,
        session_id: str,
        options: list[str],
        multi: bool | None = None,
        rec: str = "",
        alt: str = "",
        risky: str = "",
        subs: object = (),
    ) -> None:
        key = str(session_id or "")
        with self._lock:
            options = list(options)
            self._entries[key] = (
                self._clock(),
                options,
                multi,
                rec,
                alt,
                risky,
                parse_subtitles(subs, len(options)),
            )

    def has(self, session_id: str) -> bool:
        return self._fresh(session_id) is not None

    def take(self, session_id: str) -> tuple[list[str], bool | None, str, str, str, list[str]] | None:
        """Pop the registration, or None when there is none or it has expired."""
        key = str(session_id or "")
        with self._lock:
            entry = self._entries.pop(key, None)
        if entry is None:
            return None
        created, options, multi, rec, alt, risky, subs = entry
        if self._clock() - created > self._ttl:
            return None
        return options, multi, rec, alt, risky, subs

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._entries.pop(str(session_id or ""), None)

    def _fresh(self, session_id: str) -> tuple[float, list[str], bool | None, str, str, str, list[str]] | None:
        key = str(session_id or "")
        with self._lock:
            entry = self._entries.get(key)
        if entry is None or self._clock() - entry[0] > self._ttl:
            return None
        return entry


PENDING = Pending()


def attach(text: str, session_id: str, platform: str = "", pending: Pending | None = None) -> str | None:
    """The reply with its registered chips appended, or None to leave it alone.

    Returns None off Hermes Desktop (the directive would arrive as raw text), when
    the reply already carries a directive of its own, and when nothing is registered.
    A registration is consumed either way, so a stale one cannot ride the next reply.
    """
    store = pending if pending is not None else PENDING
    if not isinstance(text, str) or not text:
        store.forget(session_id)
        return None
    if str(platform or "").strip().lower() not in DRAWS:
        store.forget(session_id)
        return None
    if DIRECTIVE_RE.search(text):
        store.forget(session_id)
        return None
    entry = store.take(session_id)
    if entry is None:
        return None
    options, multi, rec, alt, risky, subs = entry
    return text.rstrip() + "\n\n" + directive(
        options, multi=multi, rec=rec, alt=alt, risky=risky, subs=subs
    )


NEXT_STEPS_SCHEMA = {
    "name": "next_steps",
    "description": (
        "Register the Next Steps for the reply you are about to write. The chips "
        "attach to that reply automatically, so write the prose and do not also write a "
        "::nextsteps directive. Pass 2 to 6 imperative options under 120 characters each, "
        "most likely first: the user clicks one and it becomes their next message. Set "
        "multi=true when several can be done together; leave it false when choosing one "
        "rules out the others, and pass alternates for the pairs that exclude each other "
        "while the rest can still be combined. With recommend=true the decision classifier marks the "
        "options worth taking now, so recommend only options you would be happy for the "
        "user to send as they stand."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": MAX_OPTIONS,
                "description": "The chip labels in display order, imperative and specific.",
            },
            "subtitles": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": MAX_OPTIONS,
                "description": (
                    "One short line per option, in the same order, and only where the label "
                    "alone would mislead or be ambiguous: what the step actually touches, "
                    "or the consequence a bare verb hides. Pass an empty string where an "
                    "option needs none. Never restate the label, never sell the option, and "
                    "keep it under a hundred characters; it renders dim under the label and "
                    "is clipped to two lines."
                ),
            },
            "multi": {
                "type": "boolean",
                "description": (
                    "True when more than one option can be done together, false when they "
                    "are exclusive. Defaults to true for two or more options."
                ),
            },
            "alternates": {
                "type": "array",
                "description": (
                    "Groups of options that exclude each other, as 1-based numbers: [[1, 3]] "
                    "means chips 1 and 3 cannot both be picked, and one click clears the "
                    "other. Use one group per conflict, so [[1, 3], [2, 3]] says 3 is "
                    "opposed to both. An option that means 'leave it as it is' or 'do "
                    "nothing' is opposed to every action; that pairing is applied even "
                    "when this is omitted."
                ),
                "items": {"type": "array", "items": {"type": "integer"}, "minItems": 2},
                "maxItems": 6,
            },
            "risky": {
                "type": "boolean",
                "description": (
                    "Ask the classifier which of these options could damage something and "
                    "mark them. Defaults to the plugin's Mark Risky Options setting, which "
                    "is off; without a classifier nothing is marked."
                ),
            },
            "recommend": {
                "type": "boolean",
                "description": (
                    "Ask the classifier which options are worth taking now. Defaults to the "
                    "plugin's Auto Recommend setting; without a classifier nothing is marked."
                ),
            },
            "context": {
                "type": "string",
                "description": (
                    "One line on what the user asked for, used only when recommend is on."
                ),
            },
        },
        "required": ["options"],
    },
}


def handler(
    store: Pending,
    dispatch=None,
    recommend_picks=None,
    wants_recommend=None,
    risk_picks=None,
    wants_risk=None,
):
    """The tool handler: validate, optionally classify, register, answer the model."""

    def next_steps(params: dict, session_id: str = "", **kwargs) -> str:
        del kwargs
        params = params if isinstance(params, dict) else {}
        try:
            options = clean(params.get("options"))
        except ValueError as exc:
            return "Chips not registered: %s. Nothing was drawn for this reply." % exc
        multi = params.get("multi")
        if not isinstance(multi, bool):
            multi = None
        rec = ""
        wanted = params.get("recommend")
        if not isinstance(wanted, bool):
            wanted = bool(wants_recommend()) if callable(wants_recommend) else True
        if wanted:
            numbers = []
            if callable(recommend_picks):
                try:
                    numbers = recommend_picks(options, str(params.get("context") or ""))
                except Exception:  # a classifier failure must not cost the chips
                    numbers = []
            rec = rec_attribute(numbers, len(options))
        # Pairs the model declared, plus the one rule a model too often misses: an
        # option meaning "take none of these" cannot be sent beside an action.
        groups = merge_alternates(params.get("alternates"), implied_alternates(options), len(options))
        alt = alternate_attribute(groups, len(options))
        risky = ""
        declared = params.get("risky")
        if isinstance(declared, bool):
            want_risk = declared
        else:
            want_risk = bool(wants_risk()) if callable(wants_risk) else False
        if want_risk and callable(risk_picks):
            try:
                numbers = risk_picks(options, str(params.get("context") or ""))
            except Exception:  # no classifier, no pill; the chips are unaffected
                numbers = []
            risky = rec_attribute(numbers, len(options))
        subs = parse_subtitles(params.get("subtitles"), len(options))
        store.put(session_id, options, multi, rec, alt, risky, subs)
        shape = "multi" if multi is not False else "one choice"
        detail = "%d options (%s)" % (len(options), shape)
        if alt:
            detail += ", alternates %s" % alt
        if risky:
            detail += ", risky %s" % risky
        if rec:
            detail += ", recommended %s" % rec
        elif wanted:
            detail += ", nothing cleared the bar"
        return (
            "Chips registered: %s. They render under this reply; do not also write a "
            "::nextsteps line." % detail
        )

    return next_steps
