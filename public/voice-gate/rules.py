"""Bundled prose-tell rules for voice-gate.

The plugin has to stand alone: no writing skills, no vendor ruleset, no
network, no house style. Every check below is a shape readers reliably call
out, not a preference. A rule that fires on good prose costs more than a rule
that misses, so each list stays short and each threshold sits where a person
would actually notice the pattern.

``lint`` reports counts and samples; ``gate_findings`` picks the subset worth
interrupting a turn for.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List

_MD_EMPHASIS = re.compile(r"[*_`]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\b[\w'-]+\b")
_NEGATION_TRIAD = re.compile(r"\bnot (?:just|only)\b[^.!?]{0,90}\bbut\b", re.I)
_WHOLE_LINE_BOLD = re.compile(r"(?m)^\s*\*\*[^*\n]{2,80}\*\*\s*:?\s*$")
_BOLD_LEAD_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\*\*[^*\n]{2,60}\*\*\s*:?")
_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\S")

VERDICT_OPENERS = (
    "the real question",
    "the honest headline",
    "the honest answer",
    "the truth is",
    "the bottom line",
    "let's be clear",
    "make no mistake",
    "here's the thing",
    "the short answer",
    "the key takeaway",
)

CLOSING_OFFERS = (
    "let me know if",
    "would you like me to",
    "i hope this helps",
    "happy to help",
    "feel free to ask",
    "say the word",
)

CLICHE_OPENERS = (
    "in today's",
    "in the ever-evolving",
    "let's dive in",
    "let's unpack",
    "it's worth noting",
    "in the fast-paced",
    "we live in a world",
)

CONCLUSION_SIGNPOSTS = (
    "in conclusion",
    "to sum up",
    "all in all",
    "at the end of the day",
    "in summary",
    "to wrap up",
)

AI_BUZZWORDS = (
    "leverage",
    "seamless",
    "seamlessly",
    "robust",
    "delve",
    "tapestry",
    "testament",
    "realm",
    "unlock",
    "empower",
    "elevate",
    "foster",
    "myriad",
    "pivotal",
    "meticulous",
    "comprehensive",
    "game-changing",
    "cutting-edge",
    "world-class",
    "best-in-class",
    "paradigm",
    "synergy",
    "holistic",
)


def sentences(text: str) -> List[str]:
    """Rough sentence split, emphasis markers removed."""
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def _first_body_sentences(text: str, limit: int = 2) -> List[str]:
    """Leading prose sentences. Headings, tables, and code fences are skipped so
    a bold lead-in or a ``## Notes`` heading cannot hide the first real line."""
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


def _present(haystack: str, needles: tuple) -> List[str]:
    return [needle for needle in needles if needle in haystack]


def _starts_with(haystack: str, needles: tuple) -> List[str]:
    return [needle for needle in needles if haystack.startswith(needle)]


def lint(text: str) -> Dict[str, Any]:
    """Counts, samples, and word total for one document."""
    words = len(_WORD.findall(text))
    opening = " ".join(_first_body_sentences(text)).lower()
    first_line = (_first_body_sentences(text, limit=1) or [""])[0].lower()
    low = text.lower()

    all_sentences = [s.lower() for s in sentences(_MD_EMPHASIS.sub("", text))]
    signposts = [s for s in all_sentences for needle in CONCLUSION_SIGNPOSTS if s.startswith(needle)]

    bullets = _BULLET.findall(text)
    bold_bullets = _BOLD_LEAD_BULLET.findall(text)
    ratio = (len(bold_bullets) / len(bullets)) if bullets else 0.0

    buzz = sum(low.count(word) for word in AI_BUZZWORDS)

    tells = {
        "verdict_openers": {"count": 1 if _present(opening, VERDICT_OPENERS) else 0,
                            "samples": _present(opening, VERDICT_OPENERS)},
        "closing_offers": {"count": len(_present(low, CLOSING_OFFERS)),
                           "samples": _present(low, CLOSING_OFFERS)},
        "cliche_openers": {"count": 1 if _starts_with(first_line, CLICHE_OPENERS) else 0,
                           "samples": _starts_with(first_line, CLICHE_OPENERS)},
        "conclusion_signposts": {"count": len(signposts), "samples": signposts[:3]},
        "ai_buzzwords": {"count": buzz, "samples": [w for w in AI_BUZZWORDS if w in low][:6]},
        "negation_triads": {"count": len(_NEGATION_TRIAD.findall(text)), "samples": []},
        "bold_pseudo_headings": {"count": len(_WHOLE_LINE_BOLD.findall(text)), "samples": []},
        "bold_lead_bullets": {"count": len(bold_bullets), "ratio": round(ratio, 2), "samples": []},
    }
    return {"words": words, "tells": tells}


def gate_findings(result: Dict[str, Any]) -> List[str]:
    """The tells worth asking for another pass over.

    Thresholds are deliberately loose: one bold heading or one buzzword is
    normal writing, a run of them is the shape a reader complains about.
    """
    tells = result.get("tells") or {}
    words = int(result.get("words") or 0)
    found: List[str] = []

    def count(key: str) -> int:
        return int((tells.get(key) or {}).get("count") or 0)

    if count("verdict_openers"):
        found.append(f"verdict opener {count('verdict_openers')}")
    if count("closing_offers"):
        found.append(f"closing offer {count('closing_offers')}")
    if count("cliche_openers"):
        found.append(f"cliche opener {count('cliche_openers')}")
    if count("conclusion_signposts") >= 2:
        found.append(f"conclusion signpost {count('conclusion_signposts')}")
    if count("negation_triads") >= 2:
        found.append(f"negation triad {count('negation_triads')}")
    if count("bold_pseudo_headings") >= 2:
        found.append(f"bold pseudo-heading {count('bold_pseudo_headings')}")

    bold = tells.get("bold_lead_bullets") or {}
    if int(bold.get("count") or 0) >= 3 and float(bold.get("ratio") or 0) >= 0.6:
        found.append(f"bold lead-in bullets {bold.get('count')}")

    buzz = count("ai_buzzwords")
    threshold = max(5, words // 150)
    if buzz >= threshold:
        found.append(f"AI buzzword {buzz}")

    return found
