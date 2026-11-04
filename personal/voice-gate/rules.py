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


def gate_findings(result: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> List[str]:
    """The tells worth asking for another pass over.

    A single hit is ordinary writing. Each family fires at the density where a
    reader starts to notice the pattern rather than the words.
    """
    merged = merge(profile)
    thresholds = merged["thresholds"]
    tells = result.get("tells") or {}
    words = int(result.get("words") or 0)
    found: List[str] = []

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
            found.append(f"{label} {count(key)}{tail}")

    if count("verdict_openers"):
        found.append(f"verdict opener {count('verdict_openers')}")
    if count("cliche_openers"):
        found.append(f"cliche opener {count('cliche_openers')}")
    if count("conclusion_signposts") >= int(thresholds["conclusion_signposts"]):
        found.append(f"conclusion signpost {count('conclusion_signposts')}")
    if count("negation_triads") >= int(thresholds["negation_triads"]):
        found.append(f"negation triad {count('negation_triads')}")
    if count("bold_pseudo_headings") >= int(thresholds["bold_pseudo_headings"]):
        found.append(f"bold pseudo-heading {count('bold_pseudo_headings')}")

    bold = tells.get("bold_lead_bullets") or {}
    if int(bold.get("count") or 0) >= int(thresholds["bold_lead_bullets"]) and \
            float(bold.get("ratio") or 0) >= float(thresholds["bold_lead_ratio"]):
        found.append(f"bold lead-in bullets {bold.get('count')}")

    buzz_threshold = max(int(thresholds["buzzwords_floor"]),
                         int(words / 150 * float(thresholds["buzzwords_per_150_words"])))
    if count("buzzwords") >= buzz_threshold:
        found.append(f"AI vocabulary {count('buzzwords')} ({samples('buzzwords')})")
    if count("marketing_adjectives") >= max(3, int(words / 400)):
        found.append(f"promotional adjective {count('marketing_adjectives')} ({samples('marketing_adjectives')})")
    if count("banned_words"):
        found.append(f"banned word {count('banned_words')} ({samples('banned_words')})")
    if merged["preferences"].get("no_em_dash") and count("em_dashes"):
        found.append(f"em dash {count('em_dashes')}")
    elif count("em_dashes") >= int(thresholds["em_dashes"]):
        found.append(f"em dash cluster {count('em_dashes')}")

    return found
