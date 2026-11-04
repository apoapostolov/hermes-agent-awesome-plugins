<div align="center">
  <h1>Voice Gate, personal edition</h1>
  <strong>Finds the AI tells in Markdown, measured against your own writing.</strong>
  <p>Same checks as the public build, driven by a profile document instead of one fixed rule set.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Voice Gate, personal edition" />
</div>

## What the edition adds

The public build carries one list of generic tells. This edition carries the same list plus a loader for profiles: small YAML or JSON files where a person writes down the openings they refuse, the offers they never make, the vocabulary they avoid, and the thresholds that match their writing. With no profile set, it behaves exactly like the public build.

It also ships four tools and a skill, so an agent can work the gate on purpose rather than waiting for a turn to end.

| Tool | What it does |
| --- | --- |
| `voice_gate_check` | Runs the active profile over text or Markdown files and returns the findings and the raw counts. Use it before sending something long, or to explain an objection. |
| `voice_gate_profile` | Shows the active profile with its rule counts and thresholds, lists the profiles on disk, or validates one. |
| `voice_gate_learn` | Reads a corpus of somebody's writing and returns a draft profile with measured habits and candidate openings and closings. With `save`, it writes the draft for editing. |
| `voice_gate_vale` | Installs and runs [Vale](https://vale.sh) on Markdown you name. The release is pinned, the sha256 is checked before unpacking, the copy lives under `HERMES_HOME/plugin-data/voice-gate/`, and the install goes to the approval prompt because it downloads and runs a binary. |

The `voice-profile-builder` skill walks the whole procedure: what to collect, how to read the measurements, which candidates to keep, and how to check the result against writing the person is happy with.

## Install

```bash
hermes plugins install https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/personal/voice-gate
hermes plugins enable voice-gate
```

## Profiles

A profile is looked up by name in `HERMES_HOME/voice-profiles/`, most specific first, then in the plugin's own `profiles/` directory. A path also works. `profiles/example.yaml` is a commented template.

```yaml
name: my-voice
applies_to: [default]
thresholds:
  min_words: 200
preferences:
  no_em_dash: true
rules:
  verdict_openers: [the real question, the honest headline]
  closing_offers: [let me know if, i hope this helps]
  banned_words: [synergy]
```

A list you leave out keeps the generic rules, so a profile can be three lines or three hundred. `applies_to` limits the gate to named Hermes profiles; leave it out to run wherever the plugin is enabled.

## Build a profile from your own writing

```
voice_gate_learn(name="my-voice", paths=["D:/exports/chats", "D:/mail/sent"], save=true)
voice_gate_profile(action="validate", profile="my-voice")
voice_gate_check(text="<a paragraph you wrote>", profile="my-voice")
```

The learning pass measures sentence length, em dashes, semicolons, bold lines, contractions, and exclamations, then lists the opening and closing phrases that repeat. Repetition is evidence of a habit; a single sample is not. The skill covers the rest, including the rule that a profile stores shapes, never the person's own sentences.

`hermes plugins doctor` resolves its argument as a directory slug, so the spaced display name does not address it; pass the path instead: `hermes plugins doctor ~/.hermes/plugins/voice-gate` (on Windows, `%LOCALAPPDATA%\hermes\plugins\voice-gate`).

## Settings

Settings → Plugins → Voice Gate.

| Setting | What it does |
| --- | --- |
| Mode | `warn` asks once per turn, `improve` keeps asking inside the host's nudge budget, `skip` turns the gate off. |
| Hermes, Herald, Keeper, Steward, Tinker | boolean, default on | Which bots run the gate. Unticking one leaves that profile alone; the boxes live in the default profile's config, so one set covers the install. |
| Profile | Name in `HERMES_HOME/voice-profiles` or a path. Empty uses the generic rules. |
| Minimum words overrides | 0 uses the profile's floor. A positive number overrides it for every profile. |
| Vale second opinion | `advisory` runs Vale over the same changed files and appends one line when it reports at least the minimum number of alerts; `off` leaves it out. |
| Vale minimum alerts | The threshold Vale has to reach before the gate mentions it. Three by default. |
| Vale binary | Path to a Vale binary. Empty uses the plugin's copy, then `PATH`. |

## What it checks

Markdown only: `.md`, `.markdown`, `.mdx`. Paths under `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build` and `__pycache__` are skipped. The tell list, the thresholds and the wording of the objection all come from the active profile, so two people running this plugin get two different gates.

## Vale

`voice_gate_vale` installs and runs [Vale](https://vale.sh), the prose linter, on Markdown you name. The release is pinned, the sha256 is checked against the digest in `vale.py` before anything is unpacked, and the copy lives under `HERMES_HOME/plugin-data/voice-gate/`. The install call goes to the approval prompt, because it downloads and runs a binary.

```text
voice_gate_vale(action="status")
voice_gate_vale(action="install")
voice_gate_vale(action="check", paths=["docs/release-notes.md"])
```

Status resolves an existing binary from the `Vale binary` setting, then the plugin's own copy, then `PATH`, so a Vale you already installed is used as-is. Checks return Vale's own report and a count per severity.

### The style pack

`styles/VoiceGate/` holds the rules Vale runs. Every file in it is generated from `rules.py` by `scripts/gen_style_pack.py`, so the pack cannot describe a different list than the engine; `scripts/check_style_pack.py` exits nonzero when the two drift, which makes it usable in CI.

```text
python scripts/check_style_pack.py
```

Nine rules: `Terms`, `Marketing`, `Significance`, `Signposts`, `Openers`, `Hedges`, `Filler`, `Transitions` and `NegationTriad`. The first five alert at `warning` and the rest at `suggestion`, and `.vale.ini` sets `MinAlertLevel = warning`, so the nudge is driven by the rules that matter.

The pack is portable. Copy `.vale.ini` and `styles/` into a repository and Vale, the VS Code extension and any pre-commit hook judge the same prose by the same list.

### A second opinion in the turn

`Vale second opinion` has two states. `off`, the default, leaves Vale out of the turn entirely. `advisory` runs it over the same changed Markdown the engine read and appends one line to the nudge:

```text
voice-gate improve: fix 1 file(s) before this turn ends. notes.md: AI vocabulary 5 (delve, tapestry). Vale reports 6 alert(s) in 1 file(s) (Terms 3, Significance 2, Signposts 1); first at line 5: In conclusion.
```

It speaks only when Vale reports at least `Vale minimum alerts` warnings, three by default, and only when a binary resolves. An alert below that threshold, a missing binary, or a report that fails to parse leaves the nudge exactly as the engine wrote it. Vale runs on the files the engine already accepted by word count, at most six of them.

The engine and the pack catch the same generic families, so the line Vale adds is position and a per-rule breakdown rather than new words. Profile-specific lists belong to the engine, which is where a person's own vocabulary is enforced without regenerating a style.

## Tests

```text
python tests/test_voice_gate.py
```

The same twenty-one checks the public edition runs, plus the profile path.

## This edition ships with no personal data

The profile that makes the gate personal lives in `HERMES_HOME/voice-profiles/`, outside the plugin tree. The repository carries the loader, the template, and the skill; it never carries anybody's profile. That is what makes this edition publishable.

## Limits

- The checks are heuristics in English, tuned by a profile rather than proven by one.
- It reads only what a turn changed, never a whole repository, and never runs on commit.
- It cannot rewrite anything. The next pass belongs to the agent.
- A profile that fires on the person's own good writing is too tight; loosen a threshold rather than adding an exception.
