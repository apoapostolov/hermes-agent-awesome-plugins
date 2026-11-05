"""Narrow, inspectable humanizer checks; contextual matches still need review."""
from __future__ import annotations
import math
import re
from functools import lru_cache
from pathlib import Path

# key: (catalog patterns, severity, pattern, minimum occurrences, repair)
SPECS = {
    'citation_residue': ((), 'P0', r'(?:cite|filecite|filenav|i)[^\n]*?|\b(?:cite)?turn\d+(?:search|view|file)\d+\b|\b(?:oaicite|contentReference)\[[^\]\n]+\]|【\d+†[^】\n]+】', 1, 'Replace internal tokens with a verifiable reference; do not invent a citation.'),
    'reasoning_residue': ((), 'P0', r'\b(?:let me think (?:this through|step by step)|let us think step by step|my chain of thought|i need to (?:analyze|analyse) this step by step)\b', 1, 'Remove exposed reasoning scaffolding from published prose.'),
    'load_bearing_metaphor': ((72,), 'P1', r'\bload-bearing\s+(?:assumptions?|claims?|invariants?|premises?|constraints?|dependencies|dependency|arguments?|abstractions?)\b', 1, 'Name the dependency; keep literal structural terminology.'),
    'unnecessary_hyphenation': ((78,), 'P2', r'\b(?:code-base|data-set|web-site)s?\b|\bin real-time\b', 1, 'Use the established spelling; retain correct attributive technical compounds.'),
    'fake_casual_props': ((94,), 'P1', r'\b(?:checks notes|chef.s kiss|mic drop|record scratch|narrator voice|spoiler alert)\b|\((?:yes, really|yes, seriously|no, really|let that sink in)\)', 1, 'Remove imposed stage business; keep a supported playful voice.'),
    'crowd_contrast': ((95,), 'P1', r'\bwhile (?:everyone else|the (?:industry|world)) (?:was |were )?still (?:debating|arguing|writing|talking)\b|\bwhile (?:everyone else|the industry) (?:wrote think-pieces|played catch-up)\b', 1, 'Name the actual comparison or retain the supported fact alone.'),
    'participial_reframe': ((105,), 'P2', r'(?m)^(?:laid out that way|seen this way|put differently)\b', 1, 'Start at the claim unless the reframe supplies a real distinction.'),
    'hedged_enumeration': ((106,), 'P2', r'\b(?:there are several ways to|a few things to consider|it is generally a good idea to)\b', 1, 'Answer first; keep actual scope and alternatives.'),
    'significance_adverbs': ((102,), 'P2', r'\b(?:notably|interestingly|importantly|significantly)\b', 3, 'Review the density; retain a qualification or distinction that carries meaning.'),
    'scar_tissue': ((80,), 'P1', r'\b(?:a tempting approach would be|one might be tempted to|an obvious approach would be|it would be easy to just|some would suggest)\b', 2, 'Keep real alternatives; remove rejected drafting options that add no information.'),
    'lingering_attention': ((61,), 'P1', r'\b(?:the line i keep coming back to|can.t stop thinking about this|i keep returning to)\b', 1, 'Keep the claim only if its reason and speaker perspective are supported.'),
    'moral_category': ((58,), 'P1', r'\b(?:honest (?:shape|architecture|abstraction|interface)|flagged honestly)\b', 1, 'Name the concrete property rather than a moral quality.'),
    'announced_significance': ((83,), 'P1', r'\b(?:this is genuinely hard|this is what [^.!?\n]{1,45} actually looks like|actually matters)\b', 2, 'Show the supplied difficulty or consequence; do not invent evidence.'),
    'parallel_reasons': ((103,), 'P2', None, 1, 'Review three consecutive because/when constructions; preserve the actual causal relationships.'),
    'title_case_headings': ((68,), 'P2', None, 2, 'Match the surrounding heading style; keep proper titles and explicit house style.'),
    'decorative_headers': ((), 'P1', r'(?m)^\s*(?:#{1,6}\s+|[-*+]\s+)?[🚀💡✅🔥🎯🌟✨📌]\s*(?:\*\*)?[^\n]+', 2, 'Use useful structure in formal prose; sparse social decoration can be deliberate.'),
    'label_periods': ((), 'P2', r'(?m)^\s*[-*+]\s+\*\*[^*.\n]{1,35}\.\*\*\s+\S', 2, 'Inspect the label punctuation; do not change full-sentence bullets.'),
    'stranded_auxiliary': ((91,), 'P2', r'[,;]\s+(?:the [\w-]+|it|they|we|you)\s+(?:didn.t|doesn.t|wasn.t|isn.t|can.t|won.t)\s*[.!?]', 2, 'Keep deliberate contrast; review a repeated clipped auxiliary rhythm.'),
    'colon_triples': ((92,), 'P2', r':\s+[^,:.!?\n]+,\s+[^,:.!?\n]+,?\s+and\s+[^,:.!?\n]+', 3, 'Audit whether the three items form a real set; do not alter true technical lists.'),
    'self_labeling_significance': ((65,), 'P1', r'\bthat last (?:move|point|step) is (?:the )?(?:contrarian|clever|real story)\b', 1, 'Let the supported consequence carry importance instead of labeling it.'),
    'negation_chain': ((87,), 'P2', r'\bno fluff,?\s+no filler,?\s+(?:and )?no jargon\b', 1, 'Keep factual constraint inventories; inspect a rhetorical negation drumroll.'),
    'empty_concession': ((101,), 'P2', r'\bwhile [^.!?\n]{1,80}\b(?:impressive|promising|remarkable),[^.!?\n]{1,80}\bremains? a challenge\b', 2, 'Retain both supplied assessments; ask for missing scope instead of inventing a failure.'),
    'intensifier_opposition': ((104,), 'P2', r'\bobsessively\b[^.!?\n]{0,100}\bbarely at all\b', 1, 'State the supported difference without manufactured poles.'),
    'stock_reaction_frame': ((110,), 'P2', r'\b(?:what surprised me most was|the most interesting part|what i love about this is)\b', 2, 'Preserve the stated reaction, preference, and ranking; never invent its reason.'),
}


@lru_cache(maxsize=1)
def vocabulary():
    source = (Path(__file__).parent / 'references/humanizer/references/vocabulary-tiers.md').read_text(encoding='utf-8')
    tiers = {}
    for tier, start, end in [('tier1a', '## Tier 1A', '## Tier 1B'), ('tier1b', '## Tier 1B', '## Tier 2'), ('tier2', '## Tier 2', '## Tier 3')]:
        block = source.split(start, 1)[1].split(end, 1)[0]
        values = []
        for line in block.splitlines():
            if not line.startswith('| ') or line.startswith(('| Prefer', '| ---')): continue
            cell = line.split('|')[1].strip()
            cell = re.sub(r'\([^)]*\)', '', cell).strip()
            for phrase in cell.split(' / '):
                phrase = phrase.strip()
                if phrase and '…' not in phrase and '[' not in phrase:
                    values.append(phrase)
        expanded = set(values)
        for word in values:
            if not re.fullmatch(r'[a-z]+', word): continue
            if word.endswith('ies'):
                expanded.add(word[:-3] + 'y')
            elif word.endswith('s') and not word.endswith(('ss', 'ness', 'is')):
                expanded.add(word[:-1])
            elif word.endswith('e'):
                expanded.update((word + 's', word + 'd', word[:-1] + 'ing'))
            elif word.endswith('y'):
                expanded.update((word[:-1] + 'ies', word[:-1] + 'ied', word + 'ing'))
            else:
                expanded.update((word + 's', word + 'ed', word + 'ing'))
        tiers[tier] = tuple(sorted(expanded))
    tiers['tier3'] = tuple('significant significantly innovative innovation effective effectively dynamic dynamics scalable scalability compelling unprecedented exceptional exceptionally remarkable remarkably sophisticated instrumental world-class state-of-the-art best-in-class verbatim'.split())
    return tiers


def phrase_matches(text, phrases):
    if not phrases: return []
    escaped = [re.escape(phrase).replace(r'\ ', r'\s+') for phrase in sorted(set(phrases), key=len, reverse=True) if phrase]
    if not escaped: return []
    return list(re.finditer(r'(?<!\w)(?:' + '|'.join(escaped) + r')(?!\w)', text.replace('’', "'"), re.I))


def detail(text, matches):
    return {'count': len(matches), 'samples': [match[0] for match in matches[:6]],
            'positions': [{'line': text.count('\n', 0, match.start()) + 1,
                           'column': match.start() - text.rfind('\n', 0, match.start()), 'match': match[0]} for match in matches[:20]]}


def lint(text, headings, context=''):
    out = {}
    for key, (_, _, pattern, _, _) in SPECS.items():
        if pattern:
            out[key] = detail(text, list(re.finditer(pattern, text, re.I | re.M)))
    heading_hits = []
    for match in re.finditer(r'^#{1,6}\s+(.+)$', headings, re.M):
        words = re.findall(r"[A-Za-z][A-Za-z'-]*", match[1])
        if len(words) >= 4 and words[0] != 'The' and all(word[0].isupper() for word in words) and any(word in {'And', 'Of', 'For', 'To', 'With'} for word in words[1:-1]):
            heading_hits.append(match)
    out['title_case_headings'] = detail(headings, heading_hits)
    sentences = re.split(r'(?<=[.!?])\s+', text)
    run, samples = 0, []
    for sentence in sentences:
        run = run + 1 if re.search(r'\b(?:because|when)\b', sentence, re.I) else 0
        if run == 3: samples.append(sentence)
    out['parallel_reasons'] = {'count': len(samples), 'samples': samples[:6]}
    for tier, terms in vocabulary().items():
        if context in ('docs', 'technical-blog'):
            terms = [term for term in terms if term not in {'robust', 'comprehensive', 'seamless', 'ecosystem', 'leverage', 'facilitate', 'underpin', 'streamline', 'verbatim'}]
        matches = phrase_matches(text, terms)
        if tier == 'tier2':
            # Two occurrences in one paragraph, never a document-wide tally.
            matches = []
            positions = []
            for paragraph in re.finditer(r'\S[\s\S]*?(?=\n\s*\n|\Z)', text):
                local = phrase_matches(paragraph[0], terms)
                if len(local) >= 2:
                    matches.extend(local)
                    for match in local[:20]:
                        start = paragraph.start() + match.start()
                        positions.append({'line': text.count('\n', 0, start) + 1, 'column': start - text.rfind('\n', 0, start), 'match': match[0]})
            out[tier] = {'count': len(matches), 'samples': [match[0] for match in matches[:6]], 'positions': positions[:20]}
        elif tier == 'tier3':
            floor = max(3, math.floor(len(text.split()) * .03))
            accepted = [term for term in terms if len(phrase_matches(text, [term])) >= floor]
            out[tier] = detail(text, phrase_matches(text, accepted))
        else:
            out[tier] = detail(text, matches)
    phrase_patterns = [r'\bemerging (?:sector|space|category)\b', r'\bthe (?:integration|intersection) of [^.!?\n]{1,70}? (?:with|and) [^.!?\n]{1,40}', r'\bcommunity-driven\b', r'\blong-term sustainability\b', r'\buser engagement\b', r'\bdecentralized compute\b', r'\b(?:sustainable )?reward emissions\b', r'\btokenized incentive structures\b', r'\bdesigned for long-term [\w-]+']
    groups = [list(re.finditer(pattern, text, re.I)) for pattern in phrase_patterns]
    distinct = {m[0].lower() for group in groups for m in group}
    repeated = {phrase for phrase in distinct if sum(m[0].lower() == phrase for group in groups for m in group) >= 2}
    selected = [m for group in groups for m in group if len(distinct) >= 3 or m[0].lower() in repeated]
    out['tier3_phrases'] = detail(text, sorted(selected, key=lambda m: m.start()))
    return out
