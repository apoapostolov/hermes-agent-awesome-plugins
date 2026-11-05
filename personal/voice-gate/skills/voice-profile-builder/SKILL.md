---
name: voice-profile-builder
description: Build a voice-gate writing profile from a corpus of somebody's own writing.
---

# Voice profile builder

A voice-gate profile is a small YAML file that says what a person's writing never does: which openings they refuse, which offers they never make, which words they avoid, how long a document has to be before a check is worth it. The plugin carries no personal data itself, so the profile is the whole difference between one user's gate and another's.

## Build one

1. Collect curated samples of the same person's writing. Use prose documents, notes, or JSON containing a list of strings under `samples`. Raw chat exports must be filtered by author and authorship context first; an account owner can also paste other people's words. Leave out copied, forwarded, co-written, heavily edited, or AI-suspect material. The output remains a draft, not approved voice evidence.
2. Run the learning pass:

   ```
   voice_gate_learn(name="my-voice", paths=["C:/path/to/samples"], save=true)
   ```

   It returns measured habits (word count, average sentence length, em dash and semicolon counts, bold lines, contractions), plus candidate openers (frequent first three words) and closers (frequent last six words), and frequent content words.
3. Curate the draft. Frequent openings and closers describe what the writer uses; they must never become forbidden phrases merely because they are recognizable. Add an avoidance rule only when the writer explicitly rejects it. Keep source context, counterexamples, and uncertainty with any proposed habit.
4. Fill the lists a machine cannot infer: words the person refuses, marketing adjectives they never use, closing offers they never make. These come from conversations about their writing, not from frequency.
5. Set `applies_to` to the Hermes profiles the gate should run in. Leave it out to run everywhere the plugin is enabled.
6. Validate and load:

   ```
   voice_gate_profile(action="validate", profile="my-voice")
   voice_gate_profile(action="show", profile="my-voice")
   ```

   Then set the plugin's `profile` setting to the name.

## Check the result

Run `voice_gate_check` over a piece the person actually wrote. A profile that fires on their own good writing is too tight; loosen the threshold or drop the rule. Run it over a piece they complained about: if nothing fires, the list is missing the shape they dislike.

## Rules that keep a profile honest

- One sample is not a habit. A rule needs either a measured repetition or an explicit statement from the person.
- Absence is not a prohibition. Do not infer a dash or semicolon ban, a sentence-length quota, or a persona from missing features.
- Do not promote mixed authorship, copied passages, instructions, or AI-suspect samples into approved voice evidence. Lasting learning uses the separate writing-voice workflow.
- Store phrases, not private text. A profile lists the shapes to avoid; it never contains their sentences.
- Measure before tightening. Lowering `min_words` or the bullet ratio without evidence turns the gate into noise.
- Keep the file in version control if the person wants history, but treat it as personal data: it describes how somebody writes.
