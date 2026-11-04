"""Profile documents: where they live, how they load, and how a draft is built.

A profile is a small YAML or JSON file. It carries a name, the rule lists that
replace the generic ones, optional thresholds, and optional preferences such as
"no em dashes". Nothing in it is code, so anyone can write one by hand, and the
bundled skill can build one from a corpus of somebody's writing.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROFILE_SUFFIXES = (".yaml", ".yml", ".json")
TOP_LEVEL_KEYS = {"name", "description", "applies_to", "rules", "thresholds", "preferences"}
RULE_KEYS = {"verdict_openers", "closing_offers", "cliche_openers", "conclusion_signposts",
             "buzzwords", "banned_words", "marketing_adjectives"}

_WORD = re.compile(r"\b[\w'-]+\b")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_EM_DASH = re.compile(r"[\u2014]")

_STOP = set("""the a an and or but if then than that this these those to of in on for with as at by
from is are was were be been being it its i you he she they we not no do does did have has had will
would can could should may might must about into over under again very just so too also more most
such only own same other some any each few both all out up down off our your their my me us them
him her one two get got like want need know think really thing things way""".split())


def plugin_dir() -> Path:
    return Path(__file__).resolve().parent


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def search_dirs() -> List[Path]:
    """Where a bare profile name is looked up, most specific first."""
    return [hermes_home() / "voice-profiles", plugin_dir() / "profiles"]


def resolve(target: str) -> Optional[Path]:
    """A profile path for a name or an explicit path, or None."""
    if not target:
        return None
    candidate = Path(os.path.expandvars(os.path.expanduser(str(target))))
    looks_like_path = any(sep in str(target) for sep in ("/", "\\")) or candidate.suffix in PROFILE_SUFFIXES
    if looks_like_path:
        try:
            return candidate.resolve() if candidate.is_file() else None
        except OSError:
            return None
    for directory in search_dirs():
        for suffix in PROFILE_SUFFIXES:
            path = directory / f"{target}{suffix}"
            if path.is_file():
                return path
    return None


def _parse(text: str) -> Dict[str, Any]:
    try:
        import yaml  # type: ignore

        data = yaml.safe_load(text)
    except Exception:
        data = json.loads(text)
    return data if isinstance(data, dict) else {}


def load(target: str) -> Tuple[Dict[str, Any], Optional[Path], List[str]]:
    """``(profile, path, issues)``. A missing or unreadable profile is not fatal."""
    path = resolve(target)
    if path is None:
        return {}, None, [f"profile {target!r} not found"]
    try:
        data = _parse(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {}, path, [f"{path.name}: {exc}"]
    issues = validate(data)
    return data, path, issues


def validate(profile: Dict[str, Any]) -> List[str]:
    """Problems a reader can fix. Unknown keys are reported, never fatal."""
    issues: List[str] = []
    if not isinstance(profile, dict):
        return ["profile must be a mapping"]
    for key in profile:
        if key not in TOP_LEVEL_KEYS:
            issues.append(f"unknown key {key!r}")
    if not profile.get("name"):
        issues.append("missing name")
    applies = profile.get("applies_to")
    if applies is not None and not isinstance(applies, (list, tuple)):
        issues.append("applies_to must be a list of profile names")
    rules = profile.get("rules")
    if rules is not None:
        if not isinstance(rules, dict):
            issues.append("rules must be a mapping")
        else:
            for key, value in rules.items():
                if key not in RULE_KEYS:
                    issues.append(f"unknown rule list {key!r}")
                elif not isinstance(value, (list, tuple)):
                    issues.append(f"rule list {key!r} must be a list")
    thresholds = profile.get("thresholds")
    if thresholds is not None and not isinstance(thresholds, dict):
        issues.append("thresholds must be a mapping")
    return issues


def stats(samples: List[str]) -> Dict[str, Any]:
    """Measured habits across a corpus. Numbers only, no judgement."""
    joined = "\n\n".join(samples)
    words = _WORD.findall(joined)
    sentences = [s for s in _SENTENCE.split(joined) if s.strip()]
    lengths = [len(_WORD.findall(s)) for s in sentences] or [0]
    return {
        "samples": len(samples),
        "words": len(words),
        "sentences": len(sentences),
        "avg_sentence_words": round(sum(lengths) / max(len(lengths), 1), 1),
        "em_dashes": len(_EM_DASH.findall(joined)),
        "semicolons": joined.count(";"),
        "bold_lines": sum(1 for line in joined.splitlines() if line.strip().startswith("**")),
        "contractions": len(re.findall(r"\b\w+'(?:s|t|re|ve|ll|d|m)\b", joined, re.I)),
        "exclamation_marks": joined.count("!"),
    }


def _phrase_counts(samples: List[str], take_first: int, words: int) -> Counter:
    counts: Counter = Counter()
    for sample in samples:
        for sentence in _SENTENCE.split(sample):
            clean = re.sub(r"[*_`#>]+", " ", sentence).strip()
            tokens = _WORD.findall(clean)
            if len(tokens) < 3:
                continue
            chunk = tokens[:words] if take_first else tokens[-words:]
            counts[" ".join(chunk).lower()] += 1
    return counts


def _content_words(samples: List[str], limit: int = 40) -> List[str]:
    words = [w.lower() for w in _WORD.findall("\n".join(samples))]
    return [word for word, _ in Counter(w for w in words if w not in _STOP and len(w) > 3).most_common(limit)]


def draft(samples: List[str], name: str = "my-voice") -> Dict[str, Any]:
    """A starting profile from a corpus.

    Openers and closers repeat in real writing, which is what makes them useful
    signatures. Everything here is a candidate: the skill asks the reader to
    keep what is genuinely theirs and delete the rest.
    """
    samples = [s for s in samples if s and s.strip()]
    measured = stats(samples)
    needed = max(2, len(samples) // 10)
    openers = [p for p, count in _phrase_counts(samples, True, 3).most_common(12) if count >= needed]
    closers = [p for p, count in _phrase_counts(samples, False, 6).most_common(12) if count >= needed]
    return {
        "name": name,
        "description": "Draft built from %d sample(s) and %d words. Curate before use."
                       % (measured["samples"], measured["words"]),
        "applies_to": ["default"],
        "thresholds": {"min_words": 200},
        "preferences": {
            "no_em_dash": measured["em_dashes"] == 0,
            "no_semicolon": measured["semicolons"] == 0,
        },
        "rules": {
            "verdict_openers": [],
            "closing_offers": [],
            "cliche_openers": [],
            "conclusion_signposts": [],
            "buzzwords": [],
            "banned_words": [],
            "marketing_adjectives": [],
        },
        "measured": measured,
        "candidates": {
            "openers": openers,
            "closers": closers,
            "frequent_words": _content_words(samples),
        },
    }
