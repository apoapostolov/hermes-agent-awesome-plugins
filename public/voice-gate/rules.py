"""Rule engine for voice-gate, parameterised by a writing profile.

The base lists below are the generic, checkable families distilled from the
humanizer references: the pattern catalog (words, sentence movement, paragraph
shape, lists, openings and closings), the extended audit tells, and the
vocabulary tiers. They are edits, not an authorship test. A hit is a prompt to
look, and a profile replaces any list it wants with the words its owner avoids.

Two kinds of family live here. Lexical families are phrase lists, matched
case-insensitively and counted by occurrence. Shape families are patterns: a
regex, a run of sentences, a paragraph statistic. Shape families fire at the
density where a reader starts to notice the pattern rather than the words, which
is why every one of them carries a threshold in BASE_THRESHOLDS.

Context matters, so CONTEXT_RELAXED names the families a register tolerates. A
docs page may keep bold lead-in labels and arrows; a blog post may not. The
names follow the humanizer context profiles: docs, technical-blog, blog, casual,
linkedin, investor-email.

docs/HUMANIZER-COVERAGE.md maps every catalog pattern to the family that carries
it, or to the reason it needs a reader instead of a rule.
"""

from __future__ import annotations

import re
from fnmatch import fnmatchcase
from typing import Any, Dict, Iterable, List, Optional, Tuple

_MD_EMPHASIS = re.compile(r"[*_`]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"\b[\w'-]+\b")
_FENCED_CODE = re.compile(r"(?ms)^\s*```.*?^\s*```[^\n]*$")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n")

_NEGATION_TRIAD = re.compile(r"\bnot (?:just|only)\b[^.!?]{0,90}\bbut\b", re.I)
_NEG_POSITIVE = re.compile(
    r"\b(?:is|was)\s+not\s+(?:about|the)\b[^.!?]{0,60}[.;]\s*(?:it|this|that)\s+(?:is|was|means)\b",
    re.I,
)
_WHOLE_LINE_BOLD = re.compile(r"(?m)^\s*\*\*[^*\n]{2,80}\*\*\s*:?\s*$")
_BOLD_LEAD_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\*\*[^*\n]{2,60}\*\*")
_BULLET = re.compile(r"(?m)^\s*[-*+]\s+\S")
_EM_DASH = re.compile(r"[\u2014]")
_GERUND_OPENING = re.compile(
    r"(?m)^\s*(?:Having|Knowing|Feeling|Realising|Realizing|Understanding|Recognising|"
    r"Recognizing|Being|Wanting|Trying)\b"
)

# --- shape patterns: a sentence skeleton, not a word -----------------------

_WH_OPENER = re.compile(r"(?im)(?:^|[.!?]\s+)\s*(?:what|why|how)\b[^.!?\n]{0,60}\b(?:is|was|are)\b")
_HEDGE_STACKED = re.compile(
    r"\b(?:could|may|might|would|can)\s+(?:potentially|possibly|eventually|ultimately|conceivably)\b"
    r"|\b(?:potentially|possibly)\s+(?:could|may|might|would)\b",
    re.I,
)
_PARENTHETICAL_HEDGE = re.compile(
    r"\([^)\n]{0,60}\b(?:increasingly|arguably|to some extent|as ever|in some ways)\b[^)\n]{0,30}\)",
    re.I,
)
_FUTURE_NARRATIVE = re.compile(
    r"\b(?:will|would|could|is set to|are set to)\s+(?:become|be|remain)\s+(?:one of\s+)?"
    r"the (?:most|next|defining)\s+(?:important|significant|influential|defining|transformative|critical)\b",
    re.I,
)
_NEG_LISTING = re.compile(
    r"(?im)(?:^|[.!?]\s+|^[-*+>]\s+)(?:not\s+(?:a|an|the|just|only|about)\b"
    r"|it\s+(?:wasn't|isn't|was not|is not)\b)",
)
_NUMBER_INFLATION = re.compile(
    r"\b(?:three|four|five|six|seven|eight|nine|ten)\s+(?:key\s+|main\s+|simple\s+|little\s+)?"
    r"(?:things|ways|takeaways|lessons|steps|reasons|tips|rules|habits|signs|mistakes|questions|secrets)\b",
    re.I,
)
_HASHTAG = re.compile(r"(?<![\w#])#[A-Za-z][A-Za-z0-9_]{1,30}\b")
_OVER_COMPRESSION = re.compile(r"\u2192|=>")
_TOOL_FINGERPRINT = re.compile(
    r"(?:[?&]utm_source=(?:chatgpt|openai|claude|perplexity|gemini|copilot)"
    r"|[?&]referrer=(?:gpt|claude|ai|chatgpt)"
    r"|[?&]utm_medium=ai)\b",
    re.I,
)
_TEMPLATE_RESIDUE = re.compile(
    r"\[(?:insert|your|name|company|topic|add|xx)[^\]\n]{0,40}\]"
    r"|\b[Tt][Bb][Dd]\b"
    r"|\blorem ipsum\b"
    r"|<(?:placeholder|your[-_ ]name|insert[^>\n]{0,30})>"
    r"|\bxxx+\b",
)
# A three-item series of short, parallel items: 'fast, cheap and safe'.
_RULE_OF_THREE = re.compile(
    r"\b[\w'-]+(?:\s+[\w'-]+)?\s*,\s*[\w'-]+(?:\s+[\w'-]+)?\s*,?\s+and\s+[\w'-]+(?:\s+[\w'-]+)?\b",
    re.I,
)
_ASSISTANT_RESIDUE = re.compile(
    r"\b(?:as an ai|as a language model|i'm just an ai|my knowledge cutoff|"
    r"as of my last (?:update|training)|i cannot browse|i don't have access to real-time|"
    r"great question|you're absolutely right|i hope this helps|let me know if you)\b",
    re.I,
)
_LAUNCH_COPY = re.compile(
    r"\b(?:say hello to|meet [A-Z][\w-]*,? your new|think [A-Z][\w-]* meets [A-Z][\w-]*)\b",
    re.I,
)
_VAGUE_AUTHORITY = re.compile(
    r"\b(?:experts (?:say|agree|believe)|critics (?:argue|say)|analysts (?:agree|say|predict)|"
    r"reports suggest|studies (?:show|suggest|confirm)|research (?:shows|suggests)|"
    r"it is widely (?:believed|known)|many (?:believe|argue)|industry experts|"
    r"independent testing confirms)\b",
    re.I,
)
_REAL_ACTUAL = re.compile(
    r"\b(?:real|actual|genuine|true)\s+(?:utility|value|impact|difference|problem|work|cost|risk|change|story)\b",
    re.I,
)
_ENDORSEMENT_CLOSER = re.compile(
    r"\b(?:worth your time|bookmark this|don't miss this|thank me later|you won't regret it|"
    r"trust me on this|save this for later|give it a read)\b",
    re.I,
)

_STACCATO_MAX_WORDS = 5
_SAME_OPENER_RUN = 3
_QUESTION_RUN = 2
_BARE_BULLET_RUN = 5

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
        "is more than just", "marks a significant", "cements its",
        "solidifies its", "ushering in", "paving the way",
    ],
    # "serves as", "boasts", "offers" where "is" or "has" would do.
    "copula_avoidance": [
        "serves as a", "serves as the", "stands as a", "stands as the",
        "functions as a", "functions as the", "represents a", "represents the",
        "boasts a", "boasts an", "offers a", "offers an", "presents a",
        "presents an", "features a", "features an",
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
        "let me walk you through", "i want to explore", "the rest of this essay",
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
    # Announcing the disclosure instead of disclosing (catalog 73).
    "candor_frames": [
        "to be fully transparent", "to be completely honest", "i want to be upfront",
        "let's be honest", "let's be real", "real talk", "if i'm being honest",
        "to be candid", "i'll say it plainly", "rather than bury this",
        "being honest about the limitations", "i would rather flag",
        "i could have left this out", "two caveats i would rather",
    ],
    # Answering an objection nobody raised (catalog 79).
    "objection_frames": [
        "this isn't mainly about", "this is not mainly about", "i'm not arguing that",
        "i am not arguing that", "don't get me wrong", "some might say",
        "you might think", "you could argue", "one could argue", "critics might say",
        "it might seem like", "it would be easy to think",
    ],
    # Scaffolding that stages a point instead of making it (catalog 81, 86).
    "rhetorical_setup": [
        "here's what i mean", "think about it", "and that's okay",
        "the catch is", "plot twist", "let that sink in", "full stop",
        "that's not nothing", "sit with that", "that's the whole point",
        "the punchline is", "worth naming", "don't take my word for it",
        "that's the part nobody mentions", "the only metric that matters",
    ],
    # Empty emphasis and announcement phrases (tier notes, throat clearing).
    "emphasis_crutches": [
        "this matters because", "here's why that matters",
        "i promise", "is a feature, not a bug", "dressed up as",
        "the stakes are high", "the consequences are real",
        "the implications are significant", "the reasons are structural",
        "this is the deepest problem",
    ],
    # Slogans that substitute for a demonstrable property (catalog 88).
    "dev_slogans": [
        "batteries included", "it just works", "zero config", "sane defaults",
        "small enough to fit in your head", "works out of the box",
    ],
    # Slot-fill template phrases from the vocabulary tiers.
    "template_phrases": [
        "a step towards", "a step toward", "a step forward for",
        "whether you're a", "i recently had the pleasure",
        "the world of", "in the world of",
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
    "copula_avoidance": 2,
    "hedges": 4,
    "signposting": 1,
    "filler": 3,
    "transitions": 3,
    "trailing_qualifiers": 2,
    "gerund_openings": 2,
    "em_dashes": 4,
    "candor_frames": 1,
    "objection_frames": 1,
    "rhetorical_setup": 2,
    "emphasis_crutches": 2,
    "dev_slogans": 2,
    "template_phrases": 2,
    "wh_openers": 2,
    "hedge_stacked": 2,
    "parenthetical_hedge": 2,
    "future_narrative": 1,
    "negative_listing": 3,
    "number_inflation": 1,
    "hashtag_stuffing": 6,
    "over_compression": 6,
    "rule_of_three": 10,
    "same_openers": 1,
    "staccato_runs": 1,
    "question_runs": 1,
    "bare_bullet_runs": 1,
    "vague_authority": 1,
    "real_actual": 2,
    "endorsement_closers": 1,
    "launch_copy": 1,
    "assistant_residue": 1,
    "template_residue": 1,
    "tool_fingerprints": 1,
}

# Registers where a family is a house convention rather than a tell.
CONTEXT_RELAXED: Dict[str, Tuple[str, ...]] = {
    "docs": (
        "bold_lead_bullets", "bold_pseudo_headings", "em_dashes", "over_compression",
        "rule_of_three", "staccato_runs", "number_inflation", "template_phrases",
        "dev_slogans", "launch_copy",
    ),
    "technical-blog": (
        "bold_lead_bullets", "em_dashes", "over_compression", "rule_of_three",
        "number_inflation", "dev_slogans",
    ),
    "blog": (),
    "casual": (
        "bold_lead_bullets", "bold_pseudo_headings", "em_dashes", "over_compression",
        "rule_of_three", "staccato_runs", "question_runs", "same_openers",
        "wh_openers", "rhetorical_setup", "number_inflation", "template_phrases",
        "transitions", "signposting",
    ),
    "linkedin": (
        "em_dashes", "staccato_runs", "bold_lead_bullets", "rule_of_three",
        "hashtag_stuffing",
    ),
    "investor-email": (),
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
        "context": str(profile.get("context") or "").strip().lower(),
        "name": str(profile.get("name") or "base"),
    }


def sentences(text: str) -> List[str]:
    return [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]


def paragraphs(text: str) -> List[str]:
    return [part.strip() for part in _PARAGRAPH_SPLIT.split(text) if part.strip()]


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


def _runs(items: List[Any], same: Any, least: int) -> int:
    """How many runs of ``least``-or-more consecutive items pass ``same``."""
    count = 0
    run = 1
    for previous, current in zip(items, items[1:]):
        if same(previous, current):
            run += 1
            if run == least:
                count += 1
        else:
            run = 1
    return count


def _word_count(sentence: str) -> int:
    return len(_WORD.findall(_MD_EMPHASIS.sub("", sentence)))


_OPENER_STOPWORDS = {
    "a", "an", "the", "it", "its", "it's", "this", "that", "these", "those", "there",
    "and", "but", "so", "if", "or", "not", "no", "in", "on", "at", "by", "for", "to",
    "of", "with", "from", "as", "we", "you", "they", "i", "he", "she", "is", "was",
}


def _opener(sentence: str) -> str:
    """The word a sentence opens on, ignoring the ones every sentence uses."""
    words = _WORD.findall(_MD_EMPHASIS.sub("", sentence).lower())
    if not words or words[0] in _OPENER_STOPWORDS:
        return ""
    return words[0]


def _shape_tells(text: str) -> Dict[str, Dict[str, Any]]:
    """The families that read a paragraph's shape rather than its words.

    Lists are not paragraphs. A run of short bullet lines and a run of short
    sentences look the same to a counter but read nothing alike, so a block that
    is mostly bullets is skipped: prose repeated that way is the tell, a table of
    field labels is not.
    """
    question_runs = 0
    same_opener_runs = 0
    staccato_runs = 0
    for paragraph in paragraphs(text):
        if paragraph.lstrip().startswith(("|", "#", ">")):
            continue
        lines = [line for line in paragraph.splitlines() if line.strip()]
        if any(_BULLET.match(line) for line in lines):
            continue
        parts = [s for s in sentences(_MD_EMPHASIS.sub("", paragraph)) if s]
        if len(parts) < 2:
            continue
        questions = [s.rstrip().endswith("?") for s in parts]
        question_runs += _runs(questions, lambda a, b: a and b, _QUESTION_RUN)
        if len(parts) < 3:
            continue
        openers = [_opener(s) for s in parts]
        same_opener_runs += _runs(openers, lambda a, b: bool(a) and a == b, _SAME_OPENER_RUN)
        shorts = [_word_count(s) <= _STACCATO_MAX_WORDS for s in parts]
        staccato_runs += _runs(shorts, lambda a, b: a and b, 3)

    bare_runs = 0
    run = 0
    for line in text.splitlines():
        if not _BULLET.match(line):
            run = 0
            continue
        body = re.sub(r"^[-*+]\s+", "", line.strip())
        short = _word_count(body) <= 4 and not body.rstrip().endswith(".")
        if short:
            run += 1
            if run == _BARE_BULLET_RUN:
                bare_runs += 1
        else:
            run = 0

    return {
        "question_runs": {"count": question_runs, "samples": []},
        "same_openers": {"count": same_opener_runs, "samples": []},
        "staccato_runs": {"count": staccato_runs, "samples": []},
        "bare_bullet_runs": {"count": bare_runs, "samples": []},
    }


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

    def shaped(pattern: Any) -> Dict[str, Any]:
        hits = pattern.findall(text)
        samples = [h if isinstance(h, str) else h[0] for h in hits][:6]
        return {"count": len(hits), "samples": samples}

    hashtags = _HASHTAG.findall(text)

    tells: Dict[str, Dict[str, Any]] = {
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
        "copula_avoidance": counted("copula_avoidance"),
        "hedges": counted("hedges"),
        "signposting": counted("signposting"),
        "filler": counted("filler"),
        "transitions": counted("transitions"),
        "trailing_qualifiers": counted("trailing_qualifiers"),
        "candor_frames": counted("candor_frames"),
        "objection_frames": counted("objection_frames"),
        "rhetorical_setup": counted("rhetorical_setup"),
        "emphasis_crutches": counted("emphasis_crutches"),
        "dev_slogans": counted("dev_slogans"),
        "template_phrases": counted("template_phrases"),
        "negation_triads": {"count": len(_NEGATION_TRIAD.findall(text)), "samples": []},
        "negation_positive": {"count": len(_NEG_POSITIVE.findall(text)), "samples": []},
        "gerund_openings": {"count": len(_GERUND_OPENING.findall(text)), "samples": []},
        "bold_pseudo_headings": {"count": len(_WHOLE_LINE_BOLD.findall(text)), "samples": []},
        "bold_lead_bullets": {"count": len(bold_bullets), "ratio": round(ratio, 2), "samples": []},
        "em_dashes": {"count": len(_EM_DASH.findall(text)), "samples": []},
        "wh_openers": shaped(_WH_OPENER),
        "hedge_stacked": shaped(_HEDGE_STACKED),
        "parenthetical_hedge": shaped(_PARENTHETICAL_HEDGE),
        "future_narrative": shaped(_FUTURE_NARRATIVE),
        "negative_listing": shaped(_NEG_LISTING),
        "number_inflation": shaped(_NUMBER_INFLATION),
        "over_compression": shaped(_OVER_COMPRESSION),
        "tool_fingerprints": shaped(_TOOL_FINGERPRINT),
        "template_residue": shaped(_TEMPLATE_RESIDUE),
        "rule_of_three": shaped(_RULE_OF_THREE),
        "assistant_residue": shaped(_ASSISTANT_RESIDUE),
        "launch_copy": shaped(_LAUNCH_COPY),
        "vague_authority": shaped(_VAGUE_AUTHORITY),
        "real_actual": shaped(_REAL_ACTUAL),
        "endorsement_closers": shaped(_ENDORSEMENT_CLOSER),
        "hashtag_stuffing": {"count": len(hashtags), "samples": hashtags[:8]},
    }
    tells.update(_shape_tells(text))
    return {"words": words, "profile": merged["name"], "tells": tells}


TELL_KEYS = (
    "closing_offers",
    "significance_inflation",
    "copula_avoidance",
    "hedges",
    "signposting",
    "filler",
    "transitions",
    "trailing_qualifiers",
    "gerund_openings",
    "negation_positive",
    "negation_triads",
    "verdict_openers",
    "cliche_openers",
    "conclusion_signposts",
    "bold_pseudo_headings",
    "bold_lead_bullets",
    "buzzwords",
    "marketing_adjectives",
    "banned_words",
    "em_dashes",
    "candor_frames",
    "objection_frames",
    "rhetorical_setup",
    "emphasis_crutches",
    "dev_slogans",
    "template_phrases",
    "wh_openers",
    "hedge_stacked",
    "parenthetical_hedge",
    "future_narrative",
    "negative_listing",
    "number_inflation",
    "hashtag_stuffing",
    "over_compression",
    "rule_of_three",
    "same_openers",
    "staccato_runs",
    "question_runs",
    "bare_bullet_runs",
    "vague_authority",
    "real_actual",
    "endorsement_closers",
    "launch_copy",
    "assistant_residue",
    "template_residue",
    "tool_fingerprints",
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
    "copula": "copula_avoidance",
    "copula_substitute": "copula_avoidance",
    "candor": "candor_frames",
    "narrated_candor": "candor_frames",
    "objection": "objection_frames",
    "shadowboxing": "objection_frames",
    "rhetorical": "rhetorical_setup",
    "setup": "rhetorical_setup",
    "emphasis": "emphasis_crutches",
    "crutch": "emphasis_crutches",
    "dev_slogan": "dev_slogans",
    "slogan": "dev_slogans",
    "template_phrase": "template_phrases",
    "wh_opener": "wh_openers",
    "hedge_stacking": "hedge_stacked",
    "parenthetical": "parenthetical_hedge",
    "future_narrative_closer": "future_narrative",
    "negative_list": "negative_listing",
    "numbered_list": "number_inflation",
    "hashtags": "hashtag_stuffing",
    "compression": "over_compression",
    "rhythm": "staccato_runs",
    "same_opener": "same_openers",
    "staccato": "staccato_runs",
    "question_run": "question_runs",
    "bare_bullets": "bare_bullet_runs",
    "bare_noun_bullets": "bare_bullet_runs",
    "vague_attribution": "vague_authority",
    "authority": "vague_authority",
    "real_actual_inflation": "real_actual",
    "endorsement": "endorsement_closers",
    "launch": "launch_copy",
    "assistant": "assistant_residue",
    "chatbot": "assistant_residue",
    "residue": "template_residue",
    "tool_fingerprint": "tool_fingerprints",
    "url_parameters": "tool_fingerprints",
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


def relaxed(context: str) -> Tuple[str, ...]:
    """Families a register treats as convention, so the gate stays quiet."""
    return CONTEXT_RELAXED.get(str(context or "").strip().lower(), ())


_DOC_BASENAMES = {
    "readme.md", "readme.markdown", "agents.md", "changelog.md", "contributing.md",
    "limitations.md", "audit.md", "proposal.md", "security.md", "code_of_conduct.md",
    "skill.md", "index.md",
}
_DOC_PARTS = {"docs", "doc", "documentation", "guides", "guide", "manual", ".github"}


def context_for_path(path: Any) -> str:
    """The register a file's kind implies, when the profile names none.

    A README, an audit or a skill page is documentation: bold field labels and
    arrows are its house conventions, and judging them by a blog post's rules
    produces noise instead of signal. Chat text has no path and keeps the strict
    rules, which is where the interesting tells live.
    """
    if not path:
        return ""
    posix = str(path).replace("\\", "/").lower()
    parts = posix.split("/")
    base = parts[-1]
    if base in _DOC_BASENAMES:
        return "docs"
    if any(part in _DOC_PARTS for part in parts[:-1]):
        return "docs"
    return ""


def gate_findings(
    result: Dict[str, Any],
    profile: Optional[Dict[str, Any]] = None,
    path: Any = None,
    disabled: Optional[Iterable[str]] = None,
) -> List[str]:
    """The tells worth asking for another pass over.

    A single hit is ordinary writing. Each family fires at the density where a
    reader starts to notice the pattern rather than the words. ``path`` lets a
    profile exempt a family for a kind of file without weakening it everywhere,
    and the profile's ``context`` relaxes the families its register tolerates.
    """
    merged = merge(profile)
    thresholds = merged["thresholds"]
    tells = result.get("tells") or {}
    words = int(result.get("words") or 0)
    found: List[str] = []
    register = merged["context"] or context_for_path(path)
    skip = set(suppressed(profile, path)) | set(relaxed(register)) | set(disabled or ())

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
        ("copula_avoidance", "copula avoidance", int(thresholds["copula_avoidance"])),
        ("hedges", "hedge", int(thresholds["hedges"])),
        ("signposting", "signposting", int(thresholds["signposting"])),
        ("filler", "wordy construction", int(thresholds["filler"])),
        ("transitions", "chained transition", int(thresholds["transitions"])),
        ("trailing_qualifiers", "trailing qualifier", int(thresholds["trailing_qualifiers"])),
        ("gerund_openings", "gerund opening", int(thresholds["gerund_openings"])),
        ("negation_positive", "negation-then-positive", 1),
        ("candor_frames", "narrated candor", int(thresholds["candor_frames"])),
        ("objection_frames", "objection nobody raised", int(thresholds["objection_frames"])),
        ("rhetorical_setup", "rhetorical setup", int(thresholds["rhetorical_setup"])),
        ("emphasis_crutches", "emphasis crutch", int(thresholds["emphasis_crutches"])),
        ("dev_slogans", "slogan instead of a property", int(thresholds["dev_slogans"])),
        ("template_phrases", "template phrase", int(thresholds["template_phrases"])),
        ("wh_openers", "wh- opener", int(thresholds["wh_openers"])),
        ("hedge_stacked", "stacked hedge", int(thresholds["hedge_stacked"])),
        ("parenthetical_hedge", "parenthetical hedge", int(thresholds["parenthetical_hedge"])),
        ("future_narrative", "future-narrative closer", int(thresholds["future_narrative"])),
        ("negative_listing", "negative listing", int(thresholds["negative_listing"])),
        ("number_inflation", "numbered-list inflation", int(thresholds["number_inflation"])),
        ("hashtag_stuffing", "hashtag block", int(thresholds["hashtag_stuffing"])),
        ("over_compression", "over-compressed shorthand",
         max(int(thresholds["over_compression"]), int(words / 400))),
        ("vague_authority", "vague attribution", int(thresholds["vague_authority"])),
        ("real_actual", "real/actual inflation", int(thresholds["real_actual"])),
        ("endorsement_closers", "endorsement closer", int(thresholds["endorsement_closers"])),
        ("launch_copy", "launch-copy introduction", int(thresholds["launch_copy"])),
        ("assistant_residue", "assistant residue", int(thresholds["assistant_residue"])),
        ("template_residue", "template residue", int(thresholds["template_residue"])),
        ("tool_fingerprints", "tool fingerprint in a URL", int(thresholds["tool_fingerprints"])),
        ("question_runs", "stacked questions", int(thresholds["question_runs"])),
        ("same_openers", "same-opener run", int(thresholds["same_openers"])),
        ("staccato_runs", "staccato run", int(thresholds["staccato_runs"])),
        ("bare_bullet_runs", "bare noun-phrase bullets", int(thresholds["bare_bullet_runs"])),
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

    triads = count("rule_of_three")
    if triads >= max(int(thresholds["rule_of_three"]), int(words / 120)):
        emit("rule_of_three", f"rule-of-three series {triads}")

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
