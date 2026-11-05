# Humanizer comparison and implementation

Compared Voice Gate 1.3.5 with the installed humanizer 1.11.0 skill and all nine references. Voice Gate 1.4.0 contains 75 mechanical families, the complete 110-pattern review catalog, and an optional contextual classifier through Hermes’s own model. A mechanical hit is an indicator; most patterns require reading their pass conditions and carve-outs.

## Findings corrected

- Substring matching counted `begin` inside `beginning` and counted overlapping forms twice. Phrase matching now uses word boundaries, longest alternatives, and whitespace-aware phrases.
- Vocabulary was one undifferentiated list. Tier 1A markers and Tier 1B clarity now remain separate; Tier 2 requires a paragraph-local cluster, and Tier 3 uses repetition of one word or the documented phrase-cluster rule.
- Contextual patterns were phrased as mandatory defects. Reports now carry severity, samples, positions where available, and an explicit review requirement. Meaning, evidence, narrative, and voice checks can run through the opt-in model review.
- Code examples leaked from AsciiDoc and Org blocks; Markdown fence kinds were interchangeable. The extractor now retains paragraph boundaries and handles matching fences, frontmatter, quotes, inline code, and protected tables.
- Markdown-wide dash exceptions also hid prose punctuation. A prose-only policy now retains bullet label separators and standalone empty table cells, and survives generic register relaxation.
- Vale could reintroduce a disabled family or an excepted file. Turn advisories now filter by each file’s active policy and matched phrases. Standalone Vale remains a generic pack, rather than a claim of profile parity.
- Profiles accepted poisoned thresholds, rejected supported keys, and learned bans from absent punctuation. Validation now rejects nonfinite or malformed values, and draft learning does not turn absence or frequent signatures into prohibitions.
- Profile names could escape the destination folder and existing profiles could be overwritten. Names are restricted and an existing draft is retained.
- Repeated improve requests did not check preservation or stop after two opportunities. The gate now compares protected-span fingerprints, accepts reasoned content-specific reviews, and stops after two passes including repairs.

## Complete catalog map

Every row has a contextual implementation in `model_review.py`, using the full source guidance. The model review is off by default; turn on **Review meaning and structure** to use it. `voice_gate_review(action="plan", pattern_ids=[...])` returns the exact rule, repair, and carve-outs for a manual review. No parser can certify that a statement is supported, an objection is real, or an emotion belongs to the writer.

| Pattern | Before 1.4.0 | Mechanical indicator in 1.4.0 | Contextual check |
| --- | --- | --- | --- |
| 1. Significance inflation | Surface matcher only | `significance_inflation` | claims |
| 2. Genre-register drift | No executable contextual review | Contextual review only | voice |
| 3. Corporate and motivational register | Surface matcher only | `tier1a`, `tier1b`, `tier2` | claims |
| 4. Imported psychological vocabulary | No executable contextual review | Contextual review only | voice |
| 5. Promotional language | Surface matcher only | `marketing_adjectives` | claims |
| 6. Abstract noun preference | No executable contextual review | Contextual review only | claims |
| 7. Em-dash cluster | Surface matcher only | `em_dashes` | movement |
| 8. Rule-of-three padding | Surface matcher only | `rule_of_three` | movement |
| 9. Negative-then-positive clarification | Surface matcher only | `negation_positive` | movement |
| 10. Copula avoidance | Surface matcher only | `copula_avoidance` | movement |
| 11. Elegant variation and repeated openings | Surface matcher only | `same_openers` | movement |
| 12. Hedging stack | Surface matcher only | `hedges`, `hedge_stacked` | movement |
| 13. Gerund opening | Surface matcher only | `gerund_openings` | movement |
| 14. Balanced compound conclusion | No executable contextual review | Contextual review only | movement |
| 15. Trailing qualifier | Surface matcher only | `trailing_qualifiers` | movement |
| 16. Not-just-X-but-Y construction | Surface matcher only | `negation_triads` | movement |
| 17. Topic-sentence paragraph | No executable contextual review | Contextual review only | movement |
| 18. Continuity bridge sentence | Surface matcher only | `transitions` | movement |
| 19. Thematic restatement ending | No executable contextual review | Contextual review only | movement |
| 20. Even-rhythm paragraph | No executable contextual review | Contextual review only | movement |
| 21. Signposting sentence | Surface matcher only | `signposting` | movement |
| 22. Backstory dump on first mention | No executable contextual review | Contextual review only | narrative |
| 23. Emotion announcement | No executable contextual review | Contextual review only | narrative |
| 24. Sympathetic narrator insert | No executable contextual review | Contextual review only | narrative |
| 25. Over-explained motivation | No executable contextual review | Contextual review only | narrative |
| 26. Analytical self-awareness | No executable contextual review | Contextual review only | narrative |
| 27. Explanatory memory flashback | No executable contextual review | Contextual review only | narrative |
| 28. Expressive dialogue tag | No executable contextual review | Contextual review only | narrative |
| 29. Dialogue that explains shared backstory | No executable contextual review | Contextual review only | narrative |
| 30. Perfect grammar in all speech | No executable contextual review | Contextual review only | narrative |
| 31. Dialogue tags used for emotion | No executable contextual review | Contextual review only | narrative |
| 32. Character who summarizes for the reader | No executable contextual review | Contextual review only | narrative |
| 33. Generic atmospheric opener | No executable contextual review | Contextual review only | narrative |
| 34. Over-complete information | No executable contextual review | Contextual review only | reader |
| 35. Culture or belief as flavor | No executable contextual review | Contextual review only | narrative |
| 36. Monster as obstacle | No executable contextual review | Contextual review only | narrative |
| 37. Setting as protagonist service | No executable contextual review | Contextual review only | narrative |
| 38. Problem framed as content invitation | No executable contextual review | Contextual review only | claims |
| 39. Sentimental resolution | No executable contextual review | Contextual review only | narrative |
| 40. Editorial narrative close | No executable contextual review | Contextual review only | narrative |
| 41. Repeated weather openings | No executable contextual review | Contextual review only | narrative |
| 42. Parallel opening-and-ending echo | No executable contextual review | Contextual review only | narrative |
| 43. Lesson stated directly | No executable contextual review | Contextual review only | narrative |
| 44. Flat comma chain | No executable contextual review | Contextual review only | movement |
| 45. Adjective barrage | No executable contextual review | Contextual review only | movement |
| 46. Pseudo-inventory | No executable contextual review | Contextual review only | movement |
| 47. Category drift | No executable contextual review | Contextual review only | movement |
| 48. Unordered causal pile | No executable contextual review | Contextual review only | movement |
| 49. Example dump | No executable contextual review | Contextual review only | movement |
| 50. Headless modifier train | No executable contextual review | Contextual review only | movement |
| 51. Serial verb chain | No executable contextual review | Contextual review only | movement |
| 52. Decorative and-chain | No executable contextual review | Contextual review only | movement |
| 53. Parenthetical list inflation | No executable contextual review | Contextual review only | movement |
| 54. List as paragraph substitute | No executable contextual review | Contextual review only | movement |
| 55. False completeness | No executable contextual review | Contextual review only | claims |
| 56. Hedge-stacked prediction | Surface matcher only | `hedge_stacked` | movement |
| 57. Real or actual adjective inflation | Surface matcher only | `real_actual` | claims |
| 58. Moral-adjective category error | Missing indicator | `moral_category` | claims |
| 59. Invented contrast-pair mirror | No executable contextual review | Contextual review only | claims |
| 60. Generic future-narrative closer | Surface matcher only | `future_narrative` | claims |
| 61. Lingering-attention claim | Missing indicator | `lingering_attention` | claims |
| 62. Hashtag stuffing | Surface matcher only | `hashtag_stuffing` | movement |
| 63. Bare noun-phrase bullet list | Surface matcher only | `bare_bullet_runs` | movement |
| 64. Vague third-party validation | Surface matcher only | `vague_authority` | claims |
| 65. Self-labeling significance | Missing indicator | `self_labeling_significance` | claims |
| 66. Parenthetical hedge aside | Surface matcher only | `parenthetical_hedge` | movement |
| 67. Numbered-list inflation | Surface matcher only | `number_inflation` | movement |
| 68. Title-case subhead habit | Missing indicator | `title_case_headings` | movement |
| 69. Historical analogy stack | No executable contextual review | Contextual review only | claims |
| 70. Paragraph-reshuffle immunity | No executable contextual review | Contextual review only | movement |
| 71. Treadmill restatement | No executable contextual review | Contextual review only | reader |
| 72. Load-bearing metaphor | Missing indicator | `load_bearing_metaphor` | claims |
| 73. Narrated candor | Surface matcher only | `candor_frames` | claims |
| 74. False agency | No executable contextual review | Contextual review only | claims |
| 75. Wh- opener crutch | Surface matcher only | `wh_openers` | movement |
| 76. Negative-listing buildup | Surface matcher only | `negative_listing` | movement |
| 77. Staccato fragmentation | Surface matcher only | `staccato_runs` | movement |
| 78. Unnecessary hyphenation | Missing indicator | `unnecessary_hyphenation` | movement |
| 79. Shadowboxing objections | Surface matcher only | `objection_frames` | claims |
| 80. Editorial scar tissue | Missing indicator | `scar_tissue` | claims |
| 81. Rhetorical setup | Surface matcher only | `rhetorical_setup` | movement |
| 82. Narrator from a distance | No executable contextual review | Contextual review only | reader |
| 83. Announced significance | Missing indicator | `announced_significance` | claims |
| 84. Additive hedge escalation | Surface matcher only | `negation_triads` | movement |
| 85. Template narrative arc | No executable contextual review | Contextual review only | movement |
| 86. Performed insight | Surface matcher only | `rhetorical_setup` | movement |
| 87. Negation chain | Missing indicator | `negation_chain` | movement |
| 88. Dev-blog boilerplate | Surface matcher only | `dev_slogans` | movement |
| 89. Stacked rhetorical questions | Surface matcher only | `question_runs` | movement |
| 90. Same-opener sentence runs | Surface matcher only | `same_openers` | movement |
| 91. Stranded auxiliary contrast | Missing indicator | `stranded_auxiliary` | movement |
| 92. Colon into a triple | Missing indicator | `colon_triples` | movement |
| 93. Launch-copy dramatic introductions | Surface matcher only | `launch_copy` | movement |
| 94. Fake-casual register | Missing indicator | `fake_casual_props` | movement |
| 95. Dramatized contrast against the crowd | Missing indicator | `crowd_contrast` | claims |
| 96. Transformation crutch | No executable contextual review | Contextual review only | claims |
| 97. Consequence-free restatement | No executable contextual review | Contextual review only | claims |
| 98. Repeated empty concessions | No executable contextual review | Contextual review only | movement |
| 99. Repeated setup/reversal punchlines | No executable contextual review | Contextual review only | movement |
| 100. Vague association | No executable contextual review | Contextual review only | claims |
| 101. Empty concession sandwich | Missing indicator | `empty_concession` | claims |
| 102. Significance-adverb density | Missing indicator | `significance_adverbs` | movement |
| 103. Parallel reason chains | Missing indicator | `parallel_reasons` | movement |
| 104. Intensifier / diminisher opposition | Missing indicator | `intensifier_opposition` | movement |
| 105. Participial reframe | Missing indicator | `participial_reframe` | movement |
| 106. Hedged-enumeration openers | Missing indicator | `hedged_enumeration` | movement |
| 107. Re-explaining what the reader knows | No executable contextual review | Contextual review only | reader |
| 108. Mannered prose | No executable contextual review | Contextual review only | voice |
| 109. Over-compression | Surface matcher only | `over_compression` | movement |
| 110. Stock reaction frame | Missing indicator | `stock_reaction_frame` | voice |

## References beyond the numbered catalog

| Source | Implementation |
| --- | --- |
| `SKILL.md` | Brief hierarchy, protected material, justified no-op, two-pass limit, and no manufactured personality. |
| `apo-voice-profile.md` | Generic approved-profile binding in the distributable snapshot. Private profile and corpus content are never bundled. |
| `humanizing-text.md` | Reader priority, meaning, voice, coherence, narrative and delivery in the contextual classifier and review plan. |
| `pattern-catalog.md` | All 110 entries above, including pass conditions and carve-outs. |
| `vocabulary-tiers.md` | Separate lexical bands, local clusters, inflections and density; domain meaning still needs review. |
| `ai-ism-audit.md` | P0/P1/P2 severity, context, source-faithful repairs and protected content. |
| `required-checks.md` | Meaning, reader priority, coherence, stance, development and over-correction review. |
| `long-form-diagnostics.md` | Optional contextual checks; no sentence-length or variation score target. |
| `provenance.md` | Signals and reviewer judgments never become authorship proof. |
| `examples.md` | Calibration contrasts supplied to the contextual reviewer; example facts are never copied into a repair. |

## Practical limits

The stop hook runs only when Hermes reports changed files. It does not intercept ordinary chat replies or prove what a writing skill did earlier in the conversation. The manual tools can check supplied text.

Optional model review uses the selected Hermes model and its normal provider, including sending the supplied documents to that provider. It accepts at most six complete documents and 80,000 characters per batch, reports skipped files, validates quoted findings against the input, and has a 45-second request timeout. It can still make an incorrect editorial judgment. No findings is not a factual or stylistic certification.

Mechanical preservation covers recognized Markdown spans and quantity changes. It cannot prove semantic equivalence or fully protect every markup dialect. The PDF reader covers simple text streams, not scans, complex font mappings, layout reconstruction, or OCR.

This snapshot is a versioned comparison target. Update it explicitly with `scripts/sync_humanizer.py`, then regenerate styles, settings, and this map and rerun the regression suites. Original source hashes and the generic profile-binding adaptation are recorded in `references/humanizer/SOURCE.json`.
