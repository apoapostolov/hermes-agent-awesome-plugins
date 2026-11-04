<div align="center">
  <h1>Voice Gate, personal edition</h1>
  <strong>A prose gate that learns how one person writes.</strong>
  <p>Same checks as the public build, driven by a profile document instead of one fixed rule set.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

## What the edition adds

The public build carries one list of generic tells. This edition carries the same list plus a loader for profiles: small YAML or JSON files where a person writes down the openings they refuse, the offers they never make, the vocabulary they avoid, and the thresholds that match their writing. With no profile set, it behaves exactly like the public build.

It also ships three tools and a skill, so an agent can work the gate on purpose rather than waiting for a turn to end.

| Tool | What it does |
| --- | --- |
| `voice_gate_check` | Runs the active profile over text or Markdown files and returns the findings and the raw counts. Use it before sending something long, or to explain an objection. |
| `voice_gate_profile` | Shows the active profile with its rule counts and thresholds, lists the profiles on disk, or validates one. |
| `voice_gate_learn` | Reads a corpus of somebody's writing and returns a draft profile with measured habits and candidate openings and closings. With `save`, it writes the draft for editing. |

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

## Settings

Settings → Plugins → Voice Gate.

| Setting | What it does |
| --- | --- |
| Mode | `warn` asks once per turn, `improve` keeps asking inside the host's nudge budget, `skip` turns the gate off. |
| Profile | Name in `HERMES_HOME/voice-profiles` or a path. Empty uses the generic rules. |
| Minimum words overrides | 0 uses the profile's floor. A positive number overrides it for every profile. |

## What it checks

Markdown only: `.md`, `.markdown`, `.mdx`. Paths under `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build` and `__pycache__` are skipped. The tell list, the thresholds and the wording of the objection all come from the active profile, so two people running this plugin get two different gates.

## This edition ships with no personal data

The profile that makes the gate personal lives in `HERMES_HOME/voice-profiles/`, outside the plugin tree. The repository carries the loader, the template, and the skill; it never carries anybody's profile. That is what makes this edition publishable.

## Limits

- The checks are heuristics in English, tuned by a profile rather than proven by one.
- It reads only what a turn changed, never a whole repository, and never runs on commit.
- It cannot rewrite anything. The next pass belongs to the agent.
- A profile that fires on the person's own good writing is too tight; loosen a threshold rather than adding an exception.
