# Humanizer coverage

Voice Gate implements the mechanics of the humanizer references that can be
decided from a text alone. This page records what is covered, what is only
partly covered, and what each remaining pattern would need before a rule could
decide it without guessing.

Sources: `pattern-catalog.md` (110 patterns), `ai-ism-audit.md` (extended
tells and contexts), `vocabulary-tiers.md` (word and phrase tiers).

## Implemented

A pattern listed here fires from `rules.py` and, where the pattern is a phrase
list, from the Vale style pack as well.

| Family | Patterns |
| --- | --- |
| `significance_inflation` | 1, 65, 83 |
| `marketing_adjectives`, `buzzwords` | 3, 5, 45 |
| `em_dashes` | 7 |
| `rule_of_three` | 8, 92 |
| `negation_positive` | 9, 13 |
| `copula_avoidance` | 10 |
| `hedge_stacked` | 12, 56, 84 |
| `trailing_qualifiers` | 15 |
| `negation_triads` | 16, 87 |
| `signposting` | 18, 21 |
| `gerund_openings` | 13 |
| `filler` | 51, 52 |
| `transitions` | 18 |
| `candor_frames` | 73, 80 |
| `objection_frames` | 79 |
| `rhetorical_setup` | 81, 86, 99 |
| `emphasis_crutches` | 65, 83, 86 |
| `dev_slogans` | 88 |
| `template_phrases` | 93, 106 |
| `wh_openers` | 75 |
| `parenthetical_hedge` | 66 |
| `future_narrative` | 60 |
| `negative_listing` | 76 |
| `number_inflation` | 67 |
| `hashtag_stuffing` | 62 |
| `bare_bullet_runs` | 63 |
| `vague_authority` | 64 |
| `real_actual` | 57, 104 |
| `endorsement_closers` | 61, 110 |
| `launch_copy` | 93 |
| `assistant_residue`, `template_residue`, `tool_fingerprints` | audit tells, not catalog |
| `question_runs` | 89 |
| `same_openers` | 90, 11 |
| `staccato_runs` | 77 |
| `over_compression` | 109 |
| `bold_pseudo_headings`, `bold_lead_bullets` | tier notes |
| `banned_words` | profile-supplied |

## Partly covered

The family catches the phrase form, and misses the structural form.

| Pattern | What is caught | What is missed |
| --- | --- | --- |
| 2 genre-register drift | A profile can set a register, and a path infers docs | Drift between sections of one document |
| 4 imported psychological vocabulary | Tier words that already appear in `buzzwords` | The wider vocabulary, which varies by field |
| 6 abstract noun preference | Copula substitutes and filler | Noun-class analysis that would need a parser |
| 17 topic-sentence paragraphs | Nothing | Paragraph-level first-sentence analysis |
| 19 thematic restatement endings | Conclusion signposts | Restatement that uses no signpost |
| 20 even-rhythm paragraphs | Staccato runs | Sentence-length variance over a paragraph |
| 24, 26 sympathetic narrator, self-analysis | Nothing | Fiction context |
| 38 problem framed as content invitation | Signposting phrases | The framing itself |
| 44 flat comma chains | Rule-of-three density | Four-plus items with no conjunction |
| 46, 53, 54 pseudo-inventory, parenthetical lists | Bare bullet runs | List semantics beyond shape |
| 50 headless modifier trains | Nothing | Clause parsing |
| 61 lingering-attention claims | Endorsement closers | The claim form without the catchphrase |
| 95 dramatized contrast against the crowd | Objection frames | The "everyone says X, but" shape |
| 102 significance-adverb density | Buzzword density | Adverb frequency over a document |
| 103 parallel reason chains | Rule-of-three | Repeated clause templates |
| 106 hedged-enumeration openers | Numbered-list inflation | The hedge in front of the list |

## Not implemented, and what would unlock each

Each group names the capability a rule would need. None of these can be decided
by matching words, and shipping them as phrases would produce noise instead of
signal, which is why they are planned rather than guessed.

### A. Clause parsing

Patterns 44, 46, 48, 49, 50, 51, 52, 53, 58, 74, 91.

A dependency-lite parse of each sentence: subject, verb, objects, and whether an
item list has a head noun. Enough to say "this list has four items and no verb",
or "this sentence has no agent". A small hand-written tagger over English
function words is enough; no model is required.

Phase: 1.5.

### B. Paragraph and document statistics

Patterns 17, 19, 20, 70, 71, 97, 103, 107, 108.

Sentence-length variance per paragraph, first-sentence-to-body ratio, similarity
between sentences (token overlap), and how much of a document restates what an
earlier paragraph said. All measurable with counters, no model.

Phase: 1.5, once A gives the sentence boundaries it needs.

### C. Cross-document memory

Patterns 11, 70, 71, 99.

Elegant variation, treadmill restatement and reused punchlines are only tells
across documents. Needs a small local store of the shapes seen in recent
documents, per profile, with the same fail-open discipline as the rest.

Phase: 1.6.

### D. Destination and house style

Patterns 68, 78, 2.

Title-case subheads and unnecessary hyphenation are wrong only against a house
style, which differs per project. A profile can already name a register; this
needs per-project overrides keyed by path, plus a dictionary for compounds.

Phase: 1.6.

### E. Claim and evidence comparison

Patterns 55, 64, 100, and the audit's evidence-strength drift.

Deciding whether a claim is supported means reading the thing it refers to.
Possible only for files the turn also changed, where the rule can compare a
claim against the source it cites. Otherwise it is a reader's job.

Phase: 2.0, limited to same-turn sources.

### F. Narrated and fictional registers

Patterns 22 to 43, 59, 82, 85, 94, 96, 98, 101, 105.

Scene narration, dialogue tags and sentimental resolution are conventions of
fiction, and the same lines are defects in a technical document. A rule would
need the register and the scene, so these belong to a fiction profile with its
own rules, not to the generic file gate.

Deliberately out of scope for the generic gate.

### G. Judgment patterns

Patterns 14, 59, 69, 72, 80, 86, 95, 108.

"Balanced compound conclusion", "load-bearing metaphor" and "mannered prose"
describe an effect a reader feels. A deterministic gate can flag the surface
that usually carries them, which it does, and cannot decide the effect itself.

Left to the editorial pass, by design.

## Rules for adding a family

1. The pattern must be decidable from the text, path or profile alone.
2. A single hit must not fire; density decides, and the threshold goes in
   `BASE_THRESHOLDS`.
3. Code, tables and list blocks are removed before shape families run.
4. Every new family gets a check in `tests/test_voice_gate.py` that fires it and
   a silent case beside it.
5. Every new family is measured against the real corpus in this repository. A
   family that flags ordinary documentation is a defect in the family, not in
   the documentation.
