<div align="center">
  <h1>Voice Gate</h1>
  <strong>Lints the Markdown a turn wrote before that turn can finish.</strong>
  <p>Names the tells in the prose an agent just changed, and asks for one more pass.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

## What it does

Hermes runs a `pre_verify` hook once per turn when files were edited, and a hook may answer with a message that sends the agent back for another pass. Voice Gate uses that moment to read the Markdown the turn changed and report the shapes that make writing sound machine made: a verdict opener in the first line, a closing offer at the end, a run of bold pseudo-headings, a wall of AI vocabulary.

It reports and asks. It never edits your files, never blocks a turn it cannot explain, and never runs when the file is too short to judge.

## Install

Requires Hermes Agent 0.22.0 or newer.

```bash
hermes plugins install https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/voice-gate
hermes plugins enable voice-gate
```

Once the plugin is in the catalog, `hermes plugins install voice-gate` is enough.

## Settings

Settings → Plugins → Voice Gate.

| Setting | Values | What it does |
| --- | --- | --- |
| Mode | `warn`, `improve`, `skip` | `warn` asks once per turn. `improve` keeps asking until the tells are gone or the host's nudge budget for the turn runs out. `skip` turns the gate off. |
| Minimum words | number, default 200 | Documents shorter than this are ignored, so a stub note does not trigger a review. |

## What it checks

Only Markdown: `.md`, `.markdown`, `.mdx`. Paths under `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build` and `__pycache__` are skipped.

A finding turns into a nudge when one of these crosses its threshold:

| Tell | Fires when |
| --- | --- |
| Verdict opener | The opening prose starts a sentence with a verdict phrase such as `The real question` or `The honest headline` |
| Closing offer | The text offers more work: `let me know if`, `would you like me to`, `I hope this helps` |
| Cliche opener | The first line starts with `In today's`, `Let's dive in`, or `It's worth noting` |
| Conclusion signpost | Two or more sentences open with `In conclusion`, `To sum up`, or `At the end of the day` |
| Negation triad | Two or more `not just X, but Y` constructions |
| Bold pseudo-heading | Two or more lines that are nothing but bold text |
| Bold lead-in bullets | Three or more bullets that open with a bold label, at 60% or more of the list |
| AI buzzword | Five or more, or one per 150 words in a longer document: `leverage`, `seamless`, `robust`, `delve`, `tapestry`, `testament`, `realm`, `unlock`, `empower`, and the rest of the list in `rules.py` |

One bold heading or one buzzword is normal writing, which is why the thresholds are set where a pattern starts rather than where a single word appears.

## Limits

- The checks are heuristics in English. They catch shapes that repeat, not every dull paragraph.
- It reads only what a turn changed. It does not scan a repository, and it does not run on commit.
- It cannot rewrite anything. The next pass belongs to the agent.
- A finding is a prompt to look, not proof of anything.

## Uninstall

```bash
hermes plugins disable voice-gate
hermes plugins remove voice-gate
```
