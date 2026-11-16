"""Turn a reply that offers next steps in prose into a ::nextsteps directive.

Hermes Desktop draws chips for a `::nextsteps{q1="…"}` paragraph; the plugin asks
the model to end a choice with that directive (see prompt_section.py). When a
model writes the offer as text anyway — "say the word and I'll push the branch",
"want me to run the tests?" — this module moves it into the directive so the
reply gets a card instead of a sentence nobody can click.

Pure text in, text out: no network, no model call, no state, and nothing happens
off Hermes Desktop. A reply that does not read as a closing offer is returned
untouched (None), never rewritten on a guess.
"""

from __future__ import annotations

import hashlib
import re

# Surfaces that draw transcript directives: the Desktop app and its local session.
DRAWS = frozenset({"local", "desktop"})

DIRECTIVE_RE = re.compile(r"::nextsteps\s*\{")

# Split a directive into its opening, its attributes and its closing brace, so a
# stamp can add one attribute and leave everything else exactly as written.
_DIRECTIVE_BODY_RE = re.compile(r"(::nextsteps\s*\{)([^}]*)(\})")

# The closing-offer vocabulary. Deliberately narrow: a bare "I'll …" is a
# statement of intent, not an offer, so it stays out of this list (it is only
# stripped from an option once a real trigger has matched).
TRIGGER_RE = re.compile(
    r"(?:\b(?:say|just say|give me|need)\s+the\s+(?:word|go-ahead|go)\b"
    r"|\bjust say (?:go|yes|when)\b"
    r"|\b(?:if|once) you say (?:the word|go|yes)\b"
    r"|\b(?:on|at) your (?:word|say|go|go-ahead)\b"
    r"|\b(?:do )?you want me to\b"
    r"|\bwould you like me to\b"
    r"|\bwant me to\b"
    r"|\bshall i\b"
    r"|\bshould i\b"
    r"|\bi (?:can|could) also\b"
    r"|\bi(?:'d| would) be (?:happy|glad) to\b"
    r"|\b(?:happy|glad) to\b"
    r"|\blet me know if you(?:'d| would)? (?:want|like|need)\b"
    r"|\bif you(?:'d| would)? (?:want|like)\b)",
    re.IGNORECASE,
)

# Leading filler removed when a whole sentence becomes one option.
LEADINS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"say the word and i(?:'ll| will)\s+",
        r"just say (?:the word|go|yes)(?: and i(?:'ll| will)\s+)?",
        r"(?:give me|need) the (?:word|go-ahead|go) and i(?:'ll| will)\s+",
        r"(?:if|once) you say (?:the word|go|yes),? and i(?:'ll| will)\s+",
        r"(?:do )?you want me to\s+",
        r"would you like me to\s+",
        r"want me to\s+",
        r"shall i\s+",
        r"should i\s+",
        r"i (?:can|could) also\s+",
        r"i(?:'d| would) be (?:happy|glad) to\s+",
        r"(?:happy|glad) to\s+",
        r"let me know if you(?:'d| would)? (?:want|like|need)(?: me to)?\s+",
        r"i(?:'ll| will)\s+",
    )
)

# Trailing qualifiers that read as the offer, not the work.
TRAILERS = re.compile(
    r"(?:[\s,]+(?:if|when|once|whenever)\s+(?:you(?:'d| would)? (?:like|want|prefer|say so)"
    r"|you(?:'re| are) ready|you say (?:the word|go|yes))"
    r"|[\s,]+on your (?:word|say|go)"
    r"|[\s,]+at your (?:word|say|go)"
    r"|[\s,]+any ?time)[.?!]*$",
    re.IGNORECASE,
)

BULLET_RE = re.compile(r"^\s*(?:[-*•·]|\d{1,2}[.)])\s+(.+?)\s*$")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[\"'“(\[]?[A-Z0-9])")

MAX_OPTIONS = 6
MIN_OPTION_CHARS = 3
MAX_OPTION_CHARS = 120
MAX_SENTENCE_CHARS = 220


def _sane(text: str) -> str:
    """One option, safe to put inside a directive attribute: no quotes, braces or
    line breaks, single-spaced."""
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    cleaned = cleaned.replace('"', "'").replace("{", "(").replace("}", ")")
    return cleaned


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _strip_option(sentence: str) -> str | None:
    """'Want me to run the tests?' → 'Run the tests'. None when nothing matched."""
    original = sentence.strip()
    text = original
    stripped = False
    changed = True
    while changed:
        changed = False
        for lead in LEADINS:
            match = lead.match(text)
            if match:
                text = text[match.end():]
                changed = stripped = True
    trimmed = TRAILERS.sub("", text)
    if trimmed != text:
        text = trimmed
        stripped = True
    text = text.strip().strip("\"'“”‘’").strip()
    text = text.rstrip(".?!:;, ")
    if not stripped or not text:
        return None
    text = text[0].upper() + text[1:]
    if not any(ch.isalpha() for ch in text):
        return None
    if len(text) < MIN_OPTION_CHARS or len(text) > MAX_OPTION_CHARS:
        return None
    return text


def _clean(options: list[str]) -> list[str]:
    """Sane, de-duplicated options in order, capped; keeps the list usable or drops it."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in options:
        option = _sane(raw)
        if not option:
            continue
        if len(option) > MAX_OPTION_CHARS:
            option = option[: MAX_OPTION_CHARS - 1].rstrip(" ,;:") + "…"
        key = option.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(option)
    return out[:MAX_OPTIONS]


def _drop_trigger_sentences(text: str) -> str:
    """The block's prose with the lead-in sentences ("Want me to pick one?") gone."""
    kept = [s for s in _sentences(text) if not TRIGGER_RE.search(s)]
    return " ".join(kept).strip()


def _parse_block(block: str) -> tuple[list[str], str] | None:
    """(options, leftover text) for the closing block, or None when it is not an offer."""
    if not TRIGGER_RE.search(block):
        return None
    lines = block.split("\n")
    bullets: list[str] = []
    prose: list[str] = []
    for line in lines:
        match = BULLET_RE.match(line)
        if match:
            bullets.append(match.group(1))
        else:
            prose.append(line)
    prose_text = "\n".join(prose).strip()

    if bullets:
        options = _clean(bullets)
        if options:
            return options, _drop_trigger_sentences(prose_text)

    if not prose_text:
        return None
    sentences = _sentences(prose_text)
    at = None
    for i in range(len(sentences) - 1, -1, -1):
        if TRIGGER_RE.search(sentences[i]):
            at = i
            break
    if at is None or len(sentences[at]) > MAX_SENTENCE_CHARS:
        return None
    option = _strip_option(sentences[at])
    if not option:
        return None
    kept = " ".join(sentences[:at] + sentences[at + 1:]).strip()
    return _clean([option]), kept


def plan(text: str) -> tuple[str, list[str]] | None:
    """(reply without the offer, the offer's options) or None when there is no offer.

    Only the last paragraph is considered: an offer in the middle of a reply is
    prose the author meant, not a closing prompt.
    "Done.\\n\\nWant me to push it?" → ("Done.", ["Push it"])
    """
    if not isinstance(text, str) or not text.strip():
        return None
    if DIRECTIVE_RE.search(text):
        return None
    blocks = text.split("\n\n")
    last = None
    for i in range(len(blocks) - 1, -1, -1):
        if blocks[i].strip():
            last = i
            break
    if last is None:
        return None
    parsed = _parse_block(blocks[last])
    if not parsed:
        return None
    options, leftover = parsed
    if not options:
        return None
    head = [b for b in blocks[:last] if b.strip()]
    if leftover:
        head.append(leftover)
    return "\n\n".join(head).strip(), options


Q_ATTR_RE = re.compile(r"\bq(\d+)\s*=\s*\"([^\"]*)\"")


def directive_options(text: str) -> list[str]:
    """The ``qN`` labels of the reply's directive, in printed order."""
    if not isinstance(text, str) or not text:
        return []
    match = _DIRECTIVE_BODY_RE.search(text)
    if not match:
        return []
    found = [(int(number), value) for number, value in Q_ATTR_RE.findall(match.group(2))]
    found.sort(key=lambda pair: pair[0])
    return [value for _, value in found]


D_ATTR_RE = re.compile(r"\bd(\d+)\s*=\s*\"([^\"]*)\"")
MAX_SUBTITLE = 160


def normalize_subtitle(value: object) -> str:
    """One line of plain text: the renderer wraps it and clips at two wrapped lines."""
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    return text[:MAX_SUBTITLE].rstrip()


def parse_subtitles(value: object, count: int) -> list[str]:
    """Subtitles for the chips, from ``dN`` attributes or a tool list.

    A subtitle exists to make an option understandable when its label alone is not,
    so a missing or empty entry is normal rather than an error: the row renders a
    label without a second line, and the model is never obliged to describe
    something that already says what it does.
    """
    out = [""] * max(count, 0)
    if isinstance(value, str):
        for number, text in D_ATTR_RE.findall(value):
            index = int(number) - 1
            if 0 <= index < len(out):
                out[index] = normalize_subtitle(text)
        return out
    if isinstance(value, (list, tuple)):
        for index, text in enumerate(value[: len(out)]):
            out[index] = normalize_subtitle(text)
    return out


def subtitle_attribute(subs: list[str]) -> str:
    """``d1="…" d3="…"`` for the entries that have one, in chip order."""
    parts = [
        'd{}="{}"'.format(index, _sane(text))
        for index, text in enumerate(_clean_subs(subs), start=1)
        if text
    ]
    return " ".join(parts)


def _clean_subs(subs: object) -> list[str]:
    if not isinstance(subs, (list, tuple)):
        return []
    return [normalize_subtitle(text) for text in subs]


ALT_GROUP_RE = re.compile(r"alt\s*=\s*\"([^\"]*)\"")
_MAX_ALT_GROUPS = 6


def parse_alternates(value: object, count: int) -> list[list[int]]:
    """Alternate groups from an ``alt`` attribute or a tool argument.

    Groups are separated by ``|`` and members by commas, 1-based to match the
    ``qN`` names the model already writes: ``"1,3|2"`` means chip 1 and chip 3
    exclude each other, and chip 2 is exclusive with nobody. A group needs two
    distinct members to mean anything, out-of-range numbers are dropped, and the
    members come back sorted so the same decision always renders the same way.
    """
    raw = value
    if isinstance(raw, str):
        raw = raw.split("|")
    if not isinstance(raw, (list, tuple)):
        return []
    groups: list[list[int]] = []
    for item in raw:
        members = item.split(",") if isinstance(item, str) else item
        if not isinstance(members, (list, tuple)):
            continue
        kept: list[int] = []
        for member in members:
            try:
                number = int(str(member).strip())
            except (TypeError, ValueError):
                continue
            if 1 <= number <= count and number not in kept:
                kept.append(number)
        kept.sort()
        if len(kept) < 2:
            continue
        if kept not in groups:
            groups.append(kept)
    return groups[:_MAX_ALT_GROUPS]


def alternate_attribute(groups: object, count: int) -> str:
    """The ``alt`` attribute text, or "" when no group means anything."""
    parsed = parse_alternates(groups, count)
    return "|".join(",".join(str(n) for n in group) for group in parsed)


def merge_alternates(given: object, enforced: object, count: int) -> list[list[int]]:
    """The model's groups, plus anything the policy insists on.

    A group a model already wrote is kept exactly; an enforced group is added
    unless it is already present, so calling this twice changes nothing.
    """
    groups = parse_alternates(given, count)
    for group in parse_alternates(enforced, count):
        if group not in groups:
            groups.append(group)
    return groups[:_MAX_ALT_GROUPS]


def directive(
    options: list[str],
    multi: bool | None = None,
    rec: str = "",
    alt: str = "",
    risky: str = "",
    subs: object = (),
) -> str:
    """The paragraph the renderer reads.

    Two or more chips are pickable, so the user can send them as one turn, and that
    is the default: ``multi=None`` means pickable whenever there is more than one
    option. A caller that knows better passes True or False, because a tool call can
    register three exclusive options and a directive that guessed from the count
    would let the user send two contradicting steps as one turn. ``multi=False`` is
    the opt-out, and a single chip carries no attribute because there is nothing to
    pick.

    ``rec`` is already-validated digits ("1,3") and rides the same brace as an attribute.

    ["Push it", "Open the PR"] -> '::nextsteps{multi="1" q1="Push it" q2="Open the PR"}'
    """
    attrs = " ".join(
        'q{}=\"{}\"'.format(i + 1, _sane(option)) for i, option in enumerate(options)
    )
    if multi is None:
        multi = len(options) > 1
    if len(options) < 2:
        head = ""
    elif multi:
        head = 'multi="1" '
    else:
        head = 'multi="0" '
    if rec:
        head += 'rec="{}" '.format(rec)
    if alt:
        head += 'alt="{}" '.format(alt)
    if risky:
        head += 'risky="{}" '.format(risky)
    detail = subtitle_attribute(_clean_subs(subs))
    if detail:
        attrs += " " + detail
    return "::nextsteps{" + head + attrs + "}"


# One directive paragraph, balanced-ish: the renderer takes it to the closing brace.
_DIRECTIVE_BODY_RE = re.compile(r"(::nextsteps\s*\{)([^}]*)(\})")


def stamp_accent(text: str, value: str = "0") -> str:
    """Put ``accent="<value>"`` into every directive that has no accent attribute.

    The renderer reads the accent as a per-directive preference, because a desktop
    plugin cannot read its own settings (the SDK exposes no settings surface to
    renderer code). The agent half knows the setting, so it stamps the off case and
    leaves the default alone: nothing is added unless the owner turned it off.

    Idempotent, and it never touches prose: no directive means the text comes back
    unchanged.
    """
    if not isinstance(text, str) or not text or not DIRECTIVE_RE.search(text):
        return text
    # A whitelist rather than _sane: _sane swaps quotes for apostrophes, which is
    # fine inside an option but leaves a broken attribute value.
    safe = re.sub(r"[^0-9a-zA-Z._-]", "", str(value))[:16] or "0"
    try:
        return _DIRECTIVE_BODY_RE.sub(
            lambda m: m.group(1) + m.group(2) + m.group(3)
            if re.search(r"\baccent\s*=", m.group(2))
            else m.group(1) + 'accent="{}" '.format(safe) + m.group(2) + m.group(3),
            text,
        )
    except Exception:  # a hook must never break a reply
        return text


def session_fingerprint(session: str) -> str:
    """A short, stable id for one chat, safe to write into the transcript.

    The queue is stored per session, so the block has to know which one it belongs
    to. The render prop can be empty, and an empty key used to mean one shared
    bucket that every chat wrote into; this fingerprint removes the guess. Twelve
    hex characters keep the raw session id out of the reply while still separating
    chats, and hashing is stable across restarts.
    """
    raw = str(session or "").strip()
    if not raw:
        return ""
    try:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    except Exception:  # a hook must never break a reply
        return ""


# The leading space goes with it, so stripping leaves one space between neighbours.
RISKY_ATTR_RE = re.compile(r"\s*risky\s*=\s*\"[^\"]*\"")


def strip_risky(text: str) -> str:
    """Remove the risky attribute, for when the setting that draws the pill is off.

    The pill is opt-in, so a reply must not carry the mark because a model wrote it:
    the renderer cannot read settings, and a warning the user switched off would
    otherwise show up on every chip a model felt unsure about.
    """
    if not isinstance(text, str) or "risky" not in text:
        return text
    try:
        return _DIRECTIVE_BODY_RE.sub(lambda m: _without_risky(m), text, count=1)
    except Exception:
        return text


def _without_risky(match: "re.Match[str]") -> str:
    body = RISKY_ATTR_RE.sub("", match.group(2))
    # A mark that opened the directive leaves the space that followed it.
    if body.startswith(" "):
        body = body[1:]
    return match.group(1) + body + match.group(3)


ALT_NUMBER_ATTRS = ("rec", "risky")
Q_ATTR_VALUE_RE = re.compile(r"\bq(\d+)\s*=\s*\"[^\"]*\"")


def _clusters(groups: list[list[int]], count: int, universal: set[int]) -> list[list[int]]:
    """Chips joined by any alternate group, as lists of 1-based numbers.

    The universal alternate is left out of the joins: it is paired with everything, so
    letting it merge would put every chip in one cluster and change nothing.
    """
    parent = list(range(count + 1))

    def find(n: int) -> int:
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    for group in groups:
        members = [n for n in group if n not in universal]
        for other in members[1:]:
            union(members[0], other)

    out: dict[int, list[int]] = {}
    for n in range(1, count + 1):
        if n in universal:
            continue
        out.setdefault(find(n), []).append(n)
    return [sorted(members) for members in out.values()]


def alternate_order(
    groups: list[list[int]], count: int, deferrals: object = ()
) -> list[int]:
    """The order that puts alternates next to each other, 1-based.

    Chips that exclude each other belong together on the row: a reader who sees "force-push"
    and then "add a note" has to hunt for the route it replaces. Clusters keep the order their
    first member had, so the model's sense of what matters most survives inside each block, and
    an option that is the alternate to all the others, usually "leave it as it is", goes last.
    """
    if count < 2 or not groups:
        return list(range(1, count + 1))
    # An option that means "take none of these" closes the row whether or not the model
    # paired it with everything, and so does one its groups make the alternate of all.
    last = {int(n) for n in deferrals if str(n).isdigit() or isinstance(n, int)}
    last = {n for n in last if 1 <= n <= count}
    # With three or more options left, one chip paired with all of them is the "take none"
    # option even when its label does not say so. With two, both are alternates of each
    # other and the test says nothing, so only the deferral phrasing counts.
    actions = [n for n in range(1, count + 1) if n not in last]
    covers_all = {
        n
        for n in actions
        if len(actions) >= 3
        and all(
            any(other in group for group in groups if n in group)
            for other in actions
            if other != n
        )
    }
    universal = last | covers_all
    clusters = _clusters(groups, count, universal)
    order: list[int] = []
    placed: set[int] = set()
    seen: set[int] = set()
    for cluster in clusters:
        members = sorted(cluster)
        for member in members:
            if member in placed:
                continue
            chain = next((c for c in clusters if member in c), [member])
            for n in sorted(chain):
                if n not in placed:
                    order.append(n)
                    placed.add(n)
    for n in range(1, count + 1):
        if n not in placed and n not in universal:
            order.append(n)
            placed.add(n)
    # The universal alternate (or alternates) closes the row.
    order.extend(sorted(universal))
    return order


def reorder_alternates(text: str, deferrals: object = ()) -> str:
    """Rewrite a directive so alternates sit together and the do-nothing option comes last.

    Labels keep their slots; only the values move, so the rest of the directive is untouched.
    """
    if not isinstance(text, str) or "alt" not in text:
        return text
    try:
        return _DIRECTIVE_BODY_RE.sub(lambda m: _reordered_body(m, deferrals), text, count=1)
    except Exception:  # a hook must never break a reply
        return text


def _reordered_body(match: "re.Match[str]", deferrals: object = ()) -> str:
    body = match.group(2)
    labels = [value for _, value in sorted(
        ((int(n), v) for n, v in Q_ATTR_RE.findall(body)), key=lambda pair: pair[0]
    )]
    if len(labels) < 2:
        return match.group(0)
    groups = parse_alternates(ALT_GROUP_RE.search(body).group(1) if ALT_GROUP_RE.search(body) else "", len(labels))
    order = alternate_order(groups, len(labels), deferrals)
    if order == list(range(1, len(labels) + 1)):
        return match.group(0)

    moved = {old: new for new, old in enumerate(order, start=1)}
    details = dict((int(n), text) for n, text in D_ATTR_RE.findall(body))
    new_body = body
    for slot, old in enumerate(order, start=1):
        new_body = re.sub(
            r"\bq%d\s*=\s*\"[^\"]*\"" % slot,
            lambda m, value=labels[old - 1]: 'q%d="%s"' % (slot, value),
            new_body,
            count=1,
        )

    if details:
        # A subtitle describes the chip it was written for, so it travels with it.
        new_body = re.sub(r"\s{2,}", " ", D_ATTR_RE.sub("", new_body)).strip()
        moved_details = sorted(
            (moved[old], text) for old, text in details.items() if old in moved and text
        )
        if moved_details:
            new_body = new_body.rstrip() + " " + " ".join(
                'd{}="{}"'.format(number, text) for number, text in moved_details
            )
    for attribute in ALT_NUMBER_ATTRS:
        new_body = _remap_numbers(new_body, attribute, moved)
    moved_groups = []
    for group in groups:
        members = sorted({moved[n] for n in group})
        if len(members) >= 2 and members not in moved_groups:
            moved_groups.append(members)
    attr = alternate_attribute(moved_groups, len(labels))
    if attr:
        new_body = ALT_GROUP_RE.sub('alt="%s"' % attr, new_body, count=1)
    else:
        new_body = ALT_GROUP_RE.sub("", new_body, count=1)
    return match.group(1) + new_body + match.group(3)


def _remap_numbers(body: str, attribute: str, moved: dict[int, int]) -> str:
    pattern = re.compile(r"\s*%s\s*=\s*\"([^\"]*)\"" % attribute)
    found = pattern.search(body)
    if not found:
        return body
    numbers = []
    for piece in found.group(1).split(","):
        try:
            number = int(piece.strip())
        except ValueError:
            continue
        if number in moved and moved[number] not in numbers:
            numbers.append(moved[number])
    numbers.sort()
    return pattern.sub(' %s="%s"' % (attribute, ",".join(str(n) for n in numbers)) if numbers else "", body, count=1)


def stamp_alternates(text: str, groups: object, count: int) -> str:
    """Add alternate groups to the reply's directive without dropping its own.

    The model decides which options exclude each other, but the policy adds one
    rule it must not lose: an option that means "take none of these" is the
    alternative to every action, so it cannot sit ticked beside one. Groups the
    reply already carries are kept, and only missing groups are appended, which
    makes a second pass a no-op.
    """
    if not isinstance(text, str) or not text:
        return text
    try:
        return _DIRECTIVE_BODY_RE.sub(lambda m: _alt_in_body(m, groups, count), text, count=1)
    except Exception:  # a hook must never break a reply
        return text


def _alt_in_body(match: "re.Match[str]", groups: object, count: int) -> str:
    body = match.group(2)
    existing = ALT_GROUP_RE.search(body)
    merged = merge_alternates(
        existing.group(1) if existing else "",
        groups,
        count,
    )
    attr = alternate_attribute(merged, count)
    if not attr:
        return match.group(0)
    if existing:
        body = body[: existing.start()] + 'alt="%s"' % attr + body[existing.end() :]
    else:
        body = 'alt="%s" ' % attr + body
    return match.group(1) + body + match.group(3)


def stamp_steer(text: str) -> str:
    """Mark the block's chips as steering the live turn.

    The renderer cannot read plugin settings, so the setting travels as an attribute.
    Only meaningful on the chip row itself: a steer needs text to deliver, and the
    empty block carry adds has none, so it is left untouched.
    """
    if not isinstance(text, str) or not text or not DIRECTIVE_RE.search(text):
        return text

    def one(match: "re.Match[str]") -> str:
        body = match.group(2)
        if re.search(r"\bsteer\s*=", body):
            return match.group(0)
        if len(re.findall(r"\bq\d+\s*=", body)) < 1:
            return match.group(0)
        return match.group(1) + 'steer="1" ' + body + match.group(3)

    try:
        return _DIRECTIVE_BODY_RE.sub(one, text)
    except Exception:  # a hook must never break a reply
        return text


def stamp_multi(text: str) -> str:
    """Make two or more chips pickable unless the directive already says otherwise.

    The renderer defaults to pickable for a multi-option block, but writing the
    attribute means a renderer from before that rule agrees with a new one. A
    directive that already carries a `multi` (including the opt-out) is left as it
    is, and a single chip gets nothing because there is nothing to pick. Idempotent,
    and it never touches prose: no directive means the text comes back unchanged.
    """
    if not isinstance(text, str) or not text or not DIRECTIVE_RE.search(text):
        return text

    def one(match: "re.Match[str]") -> str:
        body = match.group(2)
        if re.search(r"\bmulti\s*=", body):
            return match.group(0)
        if len(re.findall(r"\bq\d+\s*=", body)) < 2:
            return match.group(0)
        return match.group(1) + 'multi="1" ' + body + match.group(3)

    try:
        return _DIRECTIVE_BODY_RE.sub(one, text)
    except Exception:  # a hook must never break a reply
        return text


def stamp_session(text: str, session: str = "") -> str:
    """Name the chat in the directive, so carried chips cannot cross chats.

    Applied to every directive this plugin emits, with or without chips: the block
    that carries proposals is the one that also records them. Idempotent, and it
    leaves the text alone when there is no session to name, because a made-up key
    is exactly the leak this prevents.
    """
    fingerprint = session_fingerprint(session)
    if not fingerprint or not isinstance(text, str) or not text:
        return text
    if not DIRECTIVE_RE.search(text):
        return text

    def one(match: "re.Match[str]") -> str:
        if re.search(r"\bsid\s*=", match.group(2)):
            return match.group(0)
        return match.group(1) + 'sid="' + fingerprint + '" ' + match.group(2) + match.group(3)

    try:
        return _DIRECTIVE_BODY_RE.sub(one, text)
    except Exception:  # a hook must never break a reply
        return text


def stamp_carry(text: str, platform: str = "") -> str:
    """Mark the reply's chips as carry-over, or add one empty block where there is none.

    The renderer cannot read plugin settings, so the agent half decides and stamps
    the attribute. Two shapes matter:

    - a reply that proposes something keeps its own chips and gets ``carry="1"``, so
      the block also draws whatever earlier replies left unanswered;
    - a reply that proposes nothing gets one empty block, because the directive slot
      is the only place a desktop plugin can draw. That empty block is what lets a
      chip-less response 2 still show the three proposals response 1 left alone.

    Desktop only: on another surface the directive line would arrive as raw text.
    Idempotent, and it never touches prose beyond appending that one line.
    """
    if not isinstance(text, str) or not text:
        return text
    if str(platform or "").strip().lower() not in DRAWS:
        return text
    try:
        if DIRECTIVE_RE.search(text):
            if re.search(r"\bcarry\s*=", text):
                return text
            return _DIRECTIVE_BODY_RE.sub(
                lambda m: m.group(1) + 'carry="1" ' + m.group(2) + m.group(3), text, count=1
            )
        return text.rstrip() + '\n\n::nextsteps{carry="1"}'
    except Exception:  # a hook must never break a reply
        return text


def rewrite(text: str, platform: str = "") -> str | None:
    """The hint's own hook: the reply with its closing offer drawn as chips.

    None (leave the reply as it is) off Hermes Desktop, on a reply that already
    carries a directive, on a reply with no closing offer, and on any error.
    """
    if str(platform or "").strip().lower() not in DRAWS:
        return None
    try:
        planned = plan(text)
    except Exception:  # a hook must never break a reply
        return None
    if not planned:
        return None
    body, options = planned
    line = directive(options)
    out = (body + "\n\n" + line).strip() if body else line
    return out if out and out != text else None
