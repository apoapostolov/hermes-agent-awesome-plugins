"""Generate the complete humanizer comparison from the shipped implementation map."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('vg_coverage', ROOT / '__init__.py', submodule_search_locations=[str(ROOT)])
    gate = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = gate
    spec.loader.exec_module(gate)
    added = {number for rule in gate.mechanics.SPECS.values() for number in rule[0]} if hasattr(gate, 'mechanics') else {number for rule in gate.rules.mechanics.SPECS.values() for number in rule[0]}
    rows = ['# Humanizer comparison and implementation', '',
            'Compared Voice Gate 1.3.5 with the installed humanizer 1.11.0 skill and all nine references. Voice Gate 1.4.0 contains 75 mechanical families, the complete 110-pattern review catalog, and an optional contextual classifier through Hermes’s own model. A mechanical hit is an indicator; most patterns require reading their pass conditions and carve-outs.', '',
            '## Findings corrected', '',
            '- Substring matching counted `begin` inside `beginning` and counted overlapping forms twice. Phrase matching now uses word boundaries, longest alternatives, and whitespace-aware phrases.',
            '- Vocabulary was one undifferentiated list. Tier 1A markers and Tier 1B clarity now remain separate; Tier 2 requires a paragraph-local cluster, and Tier 3 uses repetition of one word or the documented phrase-cluster rule.',
            '- Contextual patterns were phrased as mandatory defects. Reports now carry severity, samples, positions where available, and an explicit review requirement. Meaning, evidence, narrative, and voice checks can run through the opt-in model review.',
            '- Code examples leaked from AsciiDoc and Org blocks; Markdown fence kinds were interchangeable. The extractor now retains paragraph boundaries and handles matching fences, frontmatter, quotes, inline code, and protected tables.',
            '- Markdown-wide dash exceptions also hid prose punctuation. A prose-only policy now retains bullet label separators and standalone empty table cells, and survives generic register relaxation.',
            '- Vale could reintroduce a disabled family or an excepted file. Turn advisories now filter by each file’s active policy and matched phrases. Standalone Vale remains a generic pack, rather than a claim of profile parity.',
            '- Profiles accepted poisoned thresholds, rejected supported keys, and learned bans from absent punctuation. Validation now rejects nonfinite or malformed values, and draft learning does not turn absence or frequent signatures into prohibitions.',
            '- Profile names could escape the destination folder and existing profiles could be overwritten. Names are restricted and an existing draft is retained.',
            '- Repeated improve requests did not check preservation or stop after two opportunities. The gate now compares protected-span fingerprints, accepts reasoned content-specific reviews, and stops after two passes including repairs.', '',
            '## Complete catalog map', '',
            'Every row has a contextual implementation in `model_review.py`, using the full source guidance. The model review is off by default; turn on **Review meaning and structure** to use it. `voice_gate_review(action="plan", pattern_ids=[...])` returns the exact rule, repair, and carve-outs for a manual review. No parser can certify that a statement is supported, an objection is real, or an emotion belongs to the writer.', '',
            '| Pattern | Before 1.4.0 | Mechanical indicator in 1.4.0 | Contextual check |',
            '| --- | --- | --- | --- |']
    for entry in gate.editorial.catalog():
        number = entry['id']
        keys = gate.coverage.MECHANICAL.get(number, ())
        before = 'Missing indicator' if number in added else ('Surface matcher only' if keys else 'No executable contextual review')
        mechanical = ', '.join(f'`{key}`' for key in keys) or 'Contextual review only'
        rows.append(f"| {number}. {entry['title']} | {before} | {mechanical} | {gate.coverage.review_check(number)} |")
    rows.extend(['', '## References beyond the numbered catalog', '',
                 '| Source | Implementation |', '| --- | --- |',
                 '| `SKILL.md` | Brief hierarchy, protected material, justified no-op, two-pass limit, and no manufactured personality. |',
                 '| `apo-voice-profile.md` | Generic approved-profile binding in the distributable snapshot. Private profile and corpus content are never bundled. |',
                 '| `humanizing-text.md` | Reader priority, meaning, voice, coherence, narrative and delivery in the contextual classifier and review plan. |',
                 '| `pattern-catalog.md` | All 110 entries above, including pass conditions and carve-outs. |',
                 '| `vocabulary-tiers.md` | Separate lexical bands, local clusters, inflections and density; domain meaning still needs review. |',
                 '| `ai-ism-audit.md` | P0/P1/P2 severity, context, source-faithful repairs and protected content. |',
                 '| `required-checks.md` | Meaning, reader priority, coherence, stance, development and over-correction review. |',
                 '| `long-form-diagnostics.md` | Optional contextual checks; no sentence-length or variation score target. |',
                 '| `provenance.md` | Signals and reviewer judgments never become authorship proof. |',
                 '| `examples.md` | Calibration contrasts supplied to the contextual reviewer; example facts are never copied into a repair. |', '',
                 '## Practical limits', '',
                 'The stop hook runs only when Hermes reports changed files. It does not intercept ordinary chat replies or prove what a writing skill did earlier in the conversation. The manual tools can check supplied text.', '',
                 'Optional model review uses the selected Hermes model and its normal provider, including sending the supplied documents to that provider. It accepts at most six complete documents and 80,000 characters per batch, reports skipped files, validates quoted findings against the input, and has a 45-second request timeout. It can still make an incorrect editorial judgment. No findings is not a factual or stylistic certification.', '',
                 'Mechanical preservation covers recognized Markdown spans and quantity changes. It cannot prove semantic equivalence or fully protect every markup dialect. The PDF reader covers simple text streams, not scans, complex font mappings, layout reconstruction, or OCR.', '',
                 'This snapshot is a versioned comparison target. Update it explicitly with `scripts/sync_humanizer.py`, then regenerate styles, settings, and this map and rerun the regression suites. Original source hashes and the generic profile-binding adaptation are recorded in `references/humanizer/SOURCE.json`.', ''])
    target = ROOT / 'docs' / 'HUMANIZER-COVERAGE.md'
    target.parent.mkdir(exist_ok=True)
    target.write_text('\n'.join(rows), encoding='utf-8')
    print(f'Wrote coverage for {len(gate.editorial.catalog())} patterns and all references.')


if __name__ == '__main__': main()
