"""Rule engine for voice-gate, parameterised by a writing profile.

The base lists below are the generic, checkable families distilled from the
humanizer pattern catalog and its vocabulary tiers: significance inflation,
copula avoidance, promotional register, hedges, signposting, filler, chained
transitions, meta verdicts, service tails, and the structural tells around
bold text, negation and dashes.

They are edits, not an authorship test. A hit is a prompt to look, and a
profile replaces any list it wants with the words its owner actually avoids.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from typing import Any, Dict, Iterable, List, Optional

_MD_EMPHASIS = re.compile(r"[*_`]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\b[\w'-]+\b")
_FENCED_CODE = re.compile(r"(?ms)^\s*```.*?^\s*```[^\n]*$")
_INLINE_CODE = re.compile(r"`[^`\n]*`")

_NEGATION_TRIAD = re.compile(r"\bnot (?:just|only)\b[^.!?]{0,90}\bbut\b", re.I)
_NEG_POSITIVE = re.compile(
    r"\b(?:is|was)\s+not\s+(?:about|the)\b[^.!?]{0,60}[.;]\s*(?:it|this|that)\s+(?:is|was|means)\b",
    re.I,
)
_WHOLE_LINE_BOLD = re.compile(r"(?m)^\s*\*\*[^*\n]{2,80}\*\*\s*:?\s*$")
_BOLD_LEAD_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\*\*[^*\n]{2,60}\*\*\s*:?")
_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\S")
_EM_DASH = re.compile(r"[\u2014]")
_GERUND_OPENING = re.compile(
    r"(?m)^\s*(?:Having|Knowing|Feeling|Realising|Realizing|Understanding|Recognising|Recognizing|Being|Wanting|Trying)\b"
)

BASE_RULES: Dict[str, List[str]] = {
    # A reply that announces its own verdict before the subject.
    "verdict_openers": [
        "the real question", "the honest headline", "the honest answer",
        "the truth is", "the bottom line", "let's be clear", "make no mistake",
        "here's the thing", "the short answer", "the key takeaway",
        "what nobody tells you", "the uncomfortable truth", "the hard truth",
        "the good news is", "the bad news is", "spoiler alert",
    ],
    # A reply that ends by offering more work.
    "closing_offers": [
        "let me know if", "would you like me to", "i hope this helps",
        "happy to help", "feel free to ask", "say the word",
        "i can also", "just let me know", "hope this helps",
        "don't hesitate to", "reach out if",
    ],
    "cliche_openers": [
        "in today's", "in the ever-evolving", "let's dive in", "let's unpack",
        "it's worth noting", "in the fast-paced", "we live in a world",
        "in an era of", "in recent years", "in the realm of",
        "when it comes to", "as we all know", "it goes without saying",
    ],
    "conclusion_signposts": [
        "in conclusion", "to sum up", "all in all", "at the end of the day",
        "in summary", "to wrap up", "the bottom line is",
        "ultimately,", "overall,", "in the end,", "to conclude",
    ],
    # Vocabulary tiers 1A and 2: metaphors and inflators that carry no content.
    "buzzwords": [
        "delve", "tapestry", "testament", "realm", "pivotal", "underscore",
        "underscores", "underscoring", "meticulous", "meticulously", "seamless",
        "seamlessly", "game-changer", "game-changing", "watershed", "nestled",
        "bustling", "intricate", "intricacies", "ever-evolving", "holistic",
        "impactful", "learnings", "thought leader", "synergy", "myriad",
        "plethora", "multifaceted", "transformative", "cornerstone",
        "paramount", "burgeoning", "nascent", "quintessential", "overarching",
        "catalyze", "catalyse", "galvanize", "galvanise", "revolutionize",
        "revolutionise", "elucidate", "juxtapose", "reimagine", "paradigm",
        "embark", "beacon", "navigate", "navigating", "foster", "elevate",
        "unleash", "streamline", "empower", "bolster", "spearhead",
        "resonate", "facilitate", "underpin", "underpinnings", "nuanced",
        "ecosystem", "encompass", "augment", "cultivate", "illuminate",
        "flywheel", "north star", "substrate", "nexus", "bedrock",
        "at its core", "lean into", "double down", "circle back",
        "deep dive", "unpack", "showcasing",
    ],
    "marketing_adjectives": [
        "robust", "cutting-edge", "world-class", "best-in-class",
        "revolutionary", "stunning", "groundbreaking", "renowned",
        "powerful", "vibrant", "thriving", "unmatched", "unparalleled",
        "effortless", "premium", "next-generation", "state-of-the-art",
        "future-proof", "game changing", "top-tier",
    ],
    "banned_words": [],
    # Language that inflates an ordinary detail into a turning point.
    "significance_inflation": [
        "plays a crucial role", "plays a pivotal role", "plays a vital role",
        "plays a key role", "pivotal moment", "turning point",
        "speaks volumes", "leaves a lasting", "a reminder that",
        "stands as a", "serves as a", "functions as a", "represents a",
        "is more than just", "marks a significant", "cements its",
        "solidifies its", "ushering in", "paving the way",
    ],
    # Uncertainty stacked until the sentence claims nothing.
    "hedges": [
        "perhaps", "arguably", "somewhat", "in some ways", "to an extent",
        "it could be argued", "may well", "presumably", "ostensibly",
        "seemingly", "it seems", "more or less", "fairly",
    ],
    # Throat clearing before the point arrives.
    "signposting": [
        "let's break", "here's what you need to know", "before we dive",
        "in this article", "in this section", "as we'll see",
        "let's explore", "let's take a look", "buckle up",
        "first things first", "without further ado", "let's get started",
    ],
    # Wordy constructions with a shorter honest form.
    "filler": [
        "in order to", "due to the fact that", "at this point in time",
        "it is important to note", "needless to say", "the fact that",
        "in terms of", "for the purpose of", "with regard to",
        "in the event that", "a number of", "in light of",
    ],
    # Transitions that announce structure instead of carrying it.
    "transitions": [
        "moreover", "furthermore", "additionally", "in addition",
        "that said,", "with that in mind", "on the other hand,",
        "having said that", "to that end",
    ],
    # Qualification tacked onto the end where it dilutes the claim.
    "trailing_qualifiers": [
        "for the most part", "to a degree", "where possible",
        "as best they could", "in many ways", "when possible",
        "as much as possible",
    ],
}

BASE_THRESHOLDS: Dict[str, float] = {
    "min_words": 200,
    "conclusion_signposts": 2,
    "negation_triads": 2,
    "bold_pseudo_headings": 2,
    "bold_lead_bullets": 3,
    "bold_lead_ratio": 0.6,
    "buzzwords_floor": 5,
    "buzzwords_per_150_words": 1,
    "significance_inflation": 2,
    "hedges": 4,
    "signposting": 1,
    "filler": 3,
    "transitions": 3,
    "trailing_qualifiers": 2,
    "gerund_openings": 2,
    "em_dashes": 4,
}


def merge(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Base rules with a profile laid over them.

    A profile's list replaces the base list for that family, because a person
    who writes down their own openings does not want the generic ones too.
    ``banned_words`` is empty by default and comes only from a profile.
    """
    profile = profile or {}
    rules = {key: list(value) for key, value in BASE_RULES.items()}
    for key, value in (profile.get("rules") or {}).items():
        if key in rules and isinstance(value, (list, tuple)):
            rules[key] = [str(item).lower() for item in value]
    thresholds = dict(BASE_THRESHOLDS)
    for key, value in (profile.get("thresholds") or {}).items():
        if key in thresholds:
            try:
                thresholds[key] = float(value)
            except (TypeError, ValueError):
                continue
    return {
        "rules": rules,
        "thresholds": thresholds,
        "preferences": dict(profile.get("preferences") or {}),
        "name": str(profile.get("name") or "base"),
    }


def sentences(text: str) -> List[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _first_body_sentences(text: str, limit: int = 2) -> List[str]:
    out: List[str] = []
    in_fence = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line or line.startswith("#") or line.startswith("|"):
            continue
        for sentence in sentences(_MD_EMPHASIS.sub("", line)):
            out.append(sentence)
            if len(out) >= limit:
                return out
    return out


def _prose(text: str) -> str:
    """Code is not prose.

    A document may quote the phrases it forbids, and a profile file may list
    them; fences and inline spans are removed before anything is counted, so
    documentation about a rule never trips that rule.
    """
    return _INLINE_CODE.sub(" ", _FENCED_CODE.sub(" ", text))


def _present(haystack: str, needles: Iterable[str]) -> List[str]:
    return [needle for needle in needles if needle and needle in haystack]


def _starts_with(haystack: str, needles: Iterable[str]) -> List[str]:
    return [needle for needle in needles if needle and haystack.startswith(needle)]


def lint(text: str, profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged = merge(profile)
    rules = merged["rules"]
    text = _prose(text)
    words = len(_WORD.findall(text))
    opening = " ".join(_first_body_sentences(text)).lower()
    first_line = (_first_body_sentences(text, limit=1) or [""])[0].lower()
    low = text.lower()

    all_sentences = [s.lower() for s in sentences(_MD_EMPHASIS.sub("", text))]
    signposts = [s for s in all_sentences
                 for needle in rules["conclusion_signposts"] if s.startswith(needle)]

    bullets = _BULLET.findall(text)
    bold_bullets = _BOLD_LEAD_BULLET.findall(text)
    ratio = (len(bold_bullets) / len(bullets)) if bullets else 0.0

    def counted(key: str) -> Dict[str, Any]:
        hits = _present(low, rules[key])
        total = sum(low.count(needle) for needle in hits)
        return {"count": total, "matches": len(hits), "samples": hits[:6]}

    tells = {
        "verdict_openers": {"count": 1 if _present(opening, rules["verdict_openers"]) else 0,
                            "samples": _present(opening, rules["verdict_openers"])},
        "closing_offers": {"count": len(_present(low, rules["closing_offers"])),
                           "samples": _present(low, rules["closing_offers"])},
        "cliche_openers": {"count": 1 if _starts_with(first_line, rules["cliche_openers"]) else 0,
                           "samples": _starts_with(first_line, rules["cliche_openers"])},
        "conclusion_signposts": {"count": len(signposts), "samples": signposts[:3]},
        "buzzwords": counted("buzzwords"),
        "marketing_adjectives": counted("marketing_adjectives"),
        "banned_words": counted("banned_words"),
        "significance_inflation": counted("significance_inflation"),
        "hedges": counted("hedges"),
        "signposting": counted("signposting"),
        "filler": counted("filler"),
        "transitions": counted("transitions"),
        "trailing_qualifiers": counted("trailing_qualifiers"),
        "negation_triads": {"count": len(_NEGATION_TRIAD.findall(text)), "samples": []},
        "negation_positive": {"count": len(_NEG_POSITIVE.findall(text)), "samples": []},
        "gerund_openings": {"count": len(_GERUND_OPENING.findall(text)), "samples": []},
        "bold_pseudo_headings": {"count": len(_WHOLE_LINE_BOLD.findall(text)), "samples": []},
        "bold_lead_bullets": {"count": len(bold_bullets), "ratio": round(ratio, 2), "samples": []},
        "em_dashes": {"count": len(_EM_DASH.findall(text)), "samples": []},
    }
    return {"words": words, "profile": merged["name"], "tells": tells}


TELL_KEYS = (
    "closing_offers",
    "significance_inflation",
    "hedges",
    "signposting",
    "filler",
    "transitions",
    "trailing_qualifiers",
    "gerund_openings",
    "negation_positive",
    "verdict_openers",
    "cliche_openers",
    "conclusion_signposts",
    "negation_triads",
    "bold_pseudo_headings",
    "bold_lead_bullets",
    "buzzwords",
    "marketing_adjectives",
    "banned_words",
    "em_dashes",
)

TELL_ALIASES = {
    "em_dash": "em_dashes",
    "emdash": "em_dashes",
    "em_dashes_in_documents": "em_dashes",
    "bold_lead": "bold_lead_bullets",
    "bold_lead_in": "bold_lead_bullets",
    "bold_lead_ins": "bold_lead_bullets",
    "bold_pseudo_heading": "bold_pseudo_headings",
    "bold_heading": "bold_pseudo_headings",
    "buzzword": "buzzwords",
    "ai_vocabulary": "buzzwords",
    "marketing_adjective": "marketing_adjectives",
    "promotional_adjective": "marketing_adjectives",
    "banned_word": "banned_words",
    "closing_offer": "closing_offers",
    "verdict_opener": "verdict_openers",
    "cliche_opener": "cliche_openers",
    "conclusion_signpost": "conclusion_signposts",
    "negation_triad": "negation_triads",
    "negation": "negation_positive",
    "significance": "significance_inflation",
    "hedge": "hedges",
    "transition": "transitions",
    "trailing_qualifier": "trailing_qualifiers",
    "gerund_opening": "gerund_openings",
}

_WILDCARD_TELLS = ("*", "all", "any", "everything")


def canonical_tell(name: Any) -> str:
    """A tell name in the spelling the counters use, or '' when unknown."""
    key = str(name or "").strip().lower().replace("-", "_").replace(" ", "_")
    if key in _WILDCARD_TELLS:
        return "*"
    if key in TELL_KEYS:
        return key
    if key in TELL_ALIASES:
        return TELL_ALIASES[key]
    if key + "s" in TELL_KEYS:
        return key + "s"
    if key.endswith("s") and key[:-1] in TELL_KEYS:
        return key[:-1]
    return ""


def normalise_exceptions(value: Any) -> Dict[str, List[str]]:
    """Exceptions in any accepted shape, as tell name to file globs.

    An exception belongs to the writer, not to the rules, so it arrives from a
    profile or from the plugin's own settings and can look like a mapping, a
    list of ``tell: glob, glob`` lines, or one such string::

        exceptions:
          em_dash: ["README.md", "*.md"]
          bold_lead_bullets: docs/**

        exceptions: ["signposting: *.generated.md"]
    """
    entries: List[Any] = []
    if isinstance(value, dict):
        entries = list(value.items())
    elif isinstance(value, (list, tuple)):
        for item in value:
            if isinstance(item, dict):
                entries.extend(item.items())
            else:
                entries.append(str(item))
    elif isinstance(value, str):
        entries = [line for line in value.splitlines() if line.strip()]
    out: Dict[str, List[str]] = {}
    for entry in entries:
        if isinstance(entry, tuple):
            tell, globs = entry
        else:
            tell, _, globs = str(entry).partition(":")
        if isinstance(globs, dict):
            globs = globs.get("globs") or globs.get("paths") or globs.get("files") or []
        if isinstance(globs, str):
            globs = globs.replace(";", ",").split(",")
        key = canonical_tell(tell)
        if not key:
            continue
        cleaned = [str(glob).strip().lower() for glob in (globs or []) if str(glob).strip()]
        if cleaned:
            out.setdefault(key, []).extend(cleaned)
    return out


def exceptions(*values: Any) -> Dict[str, List[str]]:
    """Every source merged, so settings and a profile can both add rows."""
    merged: Dict[str, List[str]] = {}
    for value in values:
        for tell, globs in normalise_exceptions(value).items():
            merged.setdefault(tell, []).extend(globs)
    return merged


def suppressed(profile: Optional[Dict[str, Any]], path: Any) -> List[str]:
    """The tell names the exceptions cover for this file.

    A glob is matched against the basename and the whole path, so ``README.md``
    matches anywhere and ``docs/**`` matches one tree. An exception with no path
    to test against applies to nothing: a check on bare text cannot know which
    file it is and must not quietly drop findings.
    """
    if not path:
        return []
    table = normalise_exceptions((profile or {}).get("exceptions"))
    if not table:
        return []
    posix = str(path).replace("\\", "/").lower()
    base = posix.rsplit("/", 1)[-1]
    hit: List[str] = []
    for tell, globs in table.items():
        for glob in globs:
            if glob in ("*", "**") or fnmatchcase(base, glob) or fnmatchcase(posix, glob):
                hit.append(tell)
                break
    if "*" in hit:
        return list(TELL_KEYS)
    return hit


def gate_findings(
    result: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
    path: Any = None,
) -> List[str]:
    """The tells worth asking for another pass over.

    A single hit is ordinary writing. Each family fires at the density where a
    reader starts to notice the pattern rather than the words. ``path`` lets a
    profile exempt a family for a kind of file without weakening it everywhere.
    """
    merged = merge(profile)
    thresholds = merged["thresholds"]
    tells = result.get("tells") or {}
    words = int(result.get("words") or 0)
    found: List[str] = []
    skip = set(suppressed(profile, path))

    def emit(key: str, text: str) -> None:
        if key not in skip:
            found.append(text)

    def count(key: str) -> int:
        return int((tells.get(key) or {}).get("count") or 0)

    def samples(key: str) -> str:
        return ", ".join((tells.get(key) or {}).get("samples") or [])[:80]

    simple = (
        ("closing_offers", "closing offer", 1),
        ("significance_inflation", "significance inflation", int(thresholds["significance_inflation"])),
        ("hedges", "hedge", int(thresholds["hedges"])),
        ("signposting", "signposting", int(thresholds["signposting"])),
        ("filler", "wordy construction", int(thresholds["filler"])),
        ("transitions", "chained transition", int(thresholds["transitions"])),
        ("trailing_qualifiers", "trailing qualifier", int(thresholds["trailing_qualifiers"])),
        ("gerund_openings", "gerund opening", int(thresholds["gerund_openings"])),
        ("negation_positive", "negation-then-positive", 1),
    )
    for key, label, floor in simple:
        if count(key) >= max(floor, 1):
            tail = f" ({samples(key)})" if samples(key) else ""
            emit(key, f"{label} {count(key)}{tail}")

    if count("verdict_openers"):
        emit("verdict_openers", f"verdict opener {count('verdict_openers')}")
    if count("cliche_openers"):
        emit("cliche_openers", f"cliche opener {count('cliche_openers')}")
    if count("conclusion_signposts") >= int(thresholds["conclusion_signposts"]):
        emit("conclusion_signposts", f"conclusion signpost {count('conclusion_signposts')}")
    if count("negation_triads") >= int(thresholds["negation_triads"]):
        emit("negation_triads", f"negation triad {count('negation_triads')}")
    if count("bold_pseudo_headings") >= int(thresholds["bold_pseudo_headings"]):
        emit("bold_pseudo_headings", f"bold pseudo-heading {count('bold_pseudo_headings')}")

    bold = tells.get("bold_lead_bullets") or {}
    if int(bold.get("count") or 0) >= int(thresholds["bold_lead_bullets"]) and \
            float(bold.get("ratio") or 0) >= float(thresholds["bold_lead_ratio"]):
        emit("bold_lead_bullets", f"bold lead-in bullets {bold.get('count')}")

    buzz_threshold = max(int(thresholds["buzzwords_floor"]),
                         int(words / 150 * float(thresholds["buzzwords_per_150_words"])))
    if count("buzzwords") >= buzz_threshold:
        emit("buzzwords", f"AI vocabulary {count('buzzwords')} ({samples('buzzwords')})")
    if count("marketing_adjectives") >= max(3, int(words / 400)):
        emit("marketing_adjectives",
             f"promotional adjective {count('marketing_adjectives')} ({samples('marketing_adjectives')})")
    if count("banned_words"):
        emit("banned_words", f"banned word {count('banned_words')} ({samples('banned_words')})")
    if merged["preferences"].get("no_em_dash") and count("em_dashes"):
        emit("em_dashes", f"em dash {count('em_dashes')}")
    elif count("em_dashes") >= int(thresholds["em_dashes"]):
        emit("em_dashes", f"em dash cluster {count('em_dashes')}")

    return found
