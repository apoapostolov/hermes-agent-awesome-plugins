"""Rule engine for voice-gate, parameterised by a writing profile.

Base lists below are the generic shapes every reader recognises. A profile
document (YAML or JSON, see ``profile.py``) replaces or extends any list and
adjusts the thresholds, which is how a personal voice is carried without the
plugin knowing anything about the person who wrote it.
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
_WHOLE_LINE_BOLD = re.compile(r"(?m)^\s*\*\*[^*\n]{2,80}\*\*\s*:?\s*$")
_BOLD_LEAD_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\*\*[^*\n]{2,60}\*\*\s*:?")
_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\S")
_EM_DASH = re.compile(r"[\u2014]")

BASE_RULES: Dict[str, List[str]] = {
    "verdict_openers": [
        "the real question", "the honest headline", "the honest answer",
        "the truth is", "the bottom line", "let's be clear", "make no mistake",
        "here's the thing", "the short answer", "the key takeaway",
    ],
    "closing_offers": [
        "let me know if", "would you like me to", "i hope this helps",
        "happy to help", "feel free to ask", "say the word",
    ],
    "cliche_openers": [
        "in today's", "in the ever-evolving", "let's dive in", "let's unpack",
        "it's worth noting", "in the fast-paced", "we live in a world",
    ],
    "conclusion_signposts": [
        "in conclusion", "to sum up", "all in all", "at the end of the day",
        "in summary", "to wrap up",
    ],
    "buzzwords": [
        "leverage", "seamless", "seamlessly", "robust", "delve", "tapestry",
        "testament", "realm", "unlock", "empower", "elevate", "foster",
        "myriad", "pivotal", "meticulous", "comprehensive", "game-changing",
        "cutting-edge", "world-class", "best-in-class", "paradigm", "synergy",
        "holistic",
    ],
    "banned_words": [],
    "marketing_adjectives": [],
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
}


def merge(profile: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Base rules with a profile laid over them.

    Lists in a profile replace the base list, because a person who lists their
    own openings does not want to inherit the generic ones. ``banned_words``
    and ``marketing_adjectives`` start empty and come only from a profile.
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


def _present(haystack: str, needles: Iterable[str]) -> List[str]:
    return [needle for needle in needles if needle and needle in haystack]


def _starts_with(haystack: str, needles: Iterable[str]) -> List[str]:
    return [needle for needle in needles if needle and haystack.startswith(needle)]


def _prose(text: str) -> str:
    """Code is not prose.

    A document may quote the phrases it forbids, and a profile file may list
    them; fences and inline spans are removed before anything is counted, so
    documentation about a rule never trips that rule.
    """
    return _INLINE_CODE.sub(" ", _FENCED_CODE.sub(" ", text))


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
    buzz = sum(low.count(word) for word in rules["buzzwords"])
    banned = [word for word in rules["banned_words"] if re.search(rf"\b{re.escape(word)}\b", low)]
    marketing = [word for word in rules["marketing_adjectives"] if re.search(rf"\b{re.escape(word)}\b", low)]

    tells = {
        "verdict_openers": {"count": 1 if _present(opening, rules["verdict_openers"]) else 0,
                            "samples": _present(opening, rules["verdict_openers"])},
        "closing_offers": {"count": len(_present(low, rules["closing_offers"])),
                           "samples": _present(low, rules["closing_offers"])},
        "cliche_openers": {"count": 1 if _starts_with(first_line, rules["cliche_openers"]) else 0,
                           "samples": _starts_with(first_line, rules["cliche_openers"])},
        "conclusion_signposts": {"count": len(signposts), "samples": signposts[:3]},
        "buzzwords": {"count": buzz, "samples": [w for w in rules["buzzwords"] if w in low][:6]},
        "banned_words": {"count": len(banned), "samples": banned[:6]},
        "marketing_adjectives": {"count": len(marketing), "samples": marketing[:6]},
        "negation_triads": {"count": len(_NEGATION_TRIAD.findall(text)), "samples": []},
        "bold_pseudo_headings": {"count": len(_WHOLE_LINE_BOLD.findall(text)), "samples": []},
        "bold_lead_bullets": {"count": len(bold_bullets), "ratio": round(ratio, 2), "samples": []},
        "em_dashes": {"count": len(_EM_DASH.findall(text)), "samples": []},
    }
    return {"words": words, "profile": merged["name"], "tells": tells}


def gate_findings(result: Dict[str, Any], profile: Optional[Dict[str, Any]] = None) -> List[str]:
    merged = merge(profile)
    thresholds = merged["thresholds"]
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
        found.append(f"AI buzzword {count('buzzwords')}")

    if count("banned_words"):
        found.append(f"banned word {count('banned_words')} ({', '.join((tells['banned_words'].get('samples') or [])[:3])})")
    if count("marketing_adjectives"):
        found.append(f"marketing adjective {count('marketing_adjectives')} "
                     f"({', '.join((tells['marketing_adjectives'].get('samples') or [])[:3])})")
    if merged["preferences"].get("no_em_dash") and count("em_dashes"):
        found.append(f"em dash {count('em_dashes')}")

    return found
