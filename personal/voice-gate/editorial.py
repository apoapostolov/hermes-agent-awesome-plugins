"""Humanizer's editorial contract and inspectable catalog, without an AI verdict."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SOURCE = Path(__file__).parent / 'references' / 'humanizer'
REVIEW_CHECKS = {
    'meaning': 'Preserve claims, attribution, quantities, dates, ranges, conditions, causality, negation, uncertainty, and obligation strength. Do not invent facts, sources, actors, memories, or reactions.',
    'reader': 'Lead with the needed capability, decision, or consequence. Keep consequential limits and exhaustive coverage when required; omit immaterial inventory.',
    'voice': 'Apply the explicit brief, approved profile, reader and genre, then tone. Preserve supported warmth, stance, dialect, deliberate rhetoric, and stable technical terms.',
    'claims': 'Check evidence strength, vague authority, false completeness, novelty, speculative gap filling, borrowed prestige, and inflated significance against the source.',
    'movement': 'Inspect contrasts, causal order, modifier trains, lists, sentence continuity, and paragraph dependency. Keep real distinctions and inventories.',
    'narrative': 'For fiction and dialogue, check plausible knowledge, motivation, emotion, distinct speech, backstory, setting autonomy, and earned endings. Invent only when fiction is the brief.',
    'delivery': 'Resolve real placeholders, unfinished lists, citation/attachment residue, cutoff text, response chatter, voice shifts, and accidental hard wraps. Preserve functional URLs and syntax.',
    'overcorrection': 'Do not manufacture first person, specifics, slang, typos, contrarianism, stakes, short fragments, cadence variation, or detector-score targets. Prefer a justified no-op.',
    'preservation': 'Do not rewrite code, frontmatter, quotations, attributed excerpts, tables, URLs, paths, identifiers, or headings during ordinary cleanup. Flag protected issues separately.',
    'completion': 'Use at most two editing passes including preservation repairs. After a failed repair stop and report residuals. Never treat a scan as proof of quality, truth, voice fidelity, or authorship.',
}


def catalog(ids: list[int] | None = None) -> list[dict[str, Any]]:
    entries = json.loads((SOURCE / 'catalog.json').read_text(encoding='utf-8'))
    return [entry for entry in entries if not ids or entry['id'] in ids]


def review_plan(ids: list[int] | None = None) -> dict[str, Any]:
    return {'interpretation': 'editorial_review_required', 'source': str(SOURCE / 'SKILL.md'),
            'checks': REVIEW_CHECKS, 'patterns': catalog(ids),
            'instruction': 'Apply pass conditions and carve-outs. A lexical match alone does not authorize editing. The current user brief wins over a generic catalog preference.'}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def protected(text: str) -> dict[str, list[str]]:
    """Exact protected spans for ordinary cleanup; this cannot prove semantics."""
    from .sanitize import protected_spans
    return protected_spans(text)


def preservation(before: str, after: str) -> dict[str, Any]:
    old, new = protected(before), protected(after)
    errors = [name for name in old if old[name] != new[name]]
    # Quantities are review warnings: spelling out a number can be legitimate.
    numbers = lambda text: re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?:%|\b)', text)
    warnings = ['quantities changed; compare meaning and both range bounds'] if numbers(before) != numbers(after) else []
    return {'ok': not errors, 'errors': errors, 'warnings': warnings,
            'semantic_review_required': True, 'interpretation': 'mechanical_preservation_only'}


def signature(text: str) -> dict[str, Any]:
    return {'protected': {key: [digest(span) for span in spans] for key, spans in protected(text).items()},
            'quantities': re.findall(r'(?<!\w)\d+(?:[.,]\d+)*(?:%|\b)', text)}


def compare_signatures(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    errors = [key for key in before['protected'] if before['protected'][key] != after['protected'][key]]
    return {'ok': not errors, 'errors': errors,
            'warnings': ['Quantities changed; verify meaning and range bounds.'] if before['quantities'] != after['quantities'] else [],
            'semantic_review_required': True}
