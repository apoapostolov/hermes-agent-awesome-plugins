<div align="center">
  <h1>Voice Gate</h1>
  <strong>Finds the AI tells in Markdown.</strong>
  <p>Names them, file by file, before the turn ends.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.3.1-2ea44f" alt="Version 1.3.1" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Voice Gate" />
</div>

## What it does

Hermes runs a `pre_verify` hook once per turn when files were edited, and a hook may answer with a message that sends the agent back for another pass. Voice Gate uses that moment to read the prose the turn changed and report the AI tells it finds: a verdict opener in the first line, a closing offer at the end, a run of bold pseudo-headings, a wall of AI vocabulary. Voice Gate reads the prose a turn changed, not only Markdown: plain text, reStructuredText, AsciiDoc, Org and LaTeX documents, HTML pages and PDFs are all judged, and a PDF is decoded here rather than through a library. Code inside a document is ignored, so a README that quotes a banned phrase is not flagged for quoting it, and a file that is mainly source code carries no prose to judge and is skipped.

It reports and asks. It never edits your files, never blocks a turn it cannot explain, and never runs when the file is too short to judge.

## Install

Requires Hermes Agent 0.22.0 or newer.

```bash
hermes plugins install https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/voice-gate
hermes plugins enable voice-gate
```

Once the plugin is in the catalog, `hermes plugins install voice-gate` is enough.

`hermes plugins doctor` resolves its argument as a directory slug, so the spaced display name does not address it; pass the path instead: `hermes plugins doctor ~/.hermes/plugins/voice-gate` (on Windows, `%LOCALAPPDATA%\hermes\plugins\voice-gate`).

## Settings

Settings → Plugins → Voice Gate.

| Setting | Values | What it does |
| --- | --- | --- |
| Mode | `warn`, `improve`, `skip` | `warn` asks once per turn. `improve` keeps asking until the tells are gone or the host's nudge budget for the turn runs out. `skip` turns the gate off. |
| Hermes, Herald, Keeper, Steward, Tinker | boolean, default on | Which bots run the gate. Unticking one leaves that profile alone; the boxes live in the default profile's config, so one set covers the install. |
| Minimum words | number, default 200 | Documents shorter than this are ignored, so a stub note does not trigger a review. |
| Vale binary | path | Path to a Vale binary. Empty uses the plugin's own copy under `HERMES_HOME/plugin-data`, then `PATH`. |
| Vale second opinion | `off`, `advisory` | `advisory` runs Vale over the same changed files and appends one line when it reports at least the minimum number of alerts. |
| Vale minimum alerts | number, default 3 | The threshold Vale has to reach before the gate mentions it. |

## What it checks

Only Markdown: `.md`, `.markdown`, `.mdx`. Paths under `.git`, `node_modules`, `.venv`, `venv`, `dist`, `build` and `__pycache__` are skipped.

A finding turns into a nudge when one of these crosses its threshold:

| Tell | Fires when |
| --- | --- |
| Verdict opener | The opening prose starts with a verdict phrase such as `The real question` or `The honest headline` |
| Closing offer | The text offers more work: `let me know if`, `would you like me to`, `I hope this helps` |
| Cliché opener | The first line starts with `In today's`, `Let's dive in`, or `It's worth noting` |
| Conclusion signpost | Two or more sentences open with `In conclusion`, `To sum up`, or `At the end of the day` |
| Significance inflation | Two or more phrases that inflate an ordinary detail: `plays a pivotal role`, `serves as a`, `a reminder that`, `turning point` |
| AI vocabulary | Five or more, or one per 150 words in a longer document: `delve`, `tapestry`, `testament`, `realm`, `underscore`, `meticulous`, `seamless`, `game-changer`, `intricacies`, `ever-evolving`, `synergy`, `myriad`, and the rest of the list in `rules.py` |
| Promotional adjective | Three or more: `robust`, `cutting-edge`, `world-class`, `revolutionary`, `stunning`, `groundbreaking`, `effortless`, `next-generation` |
| Hedge stack | Four or more: `perhaps`, `arguably`, `somewhat`, `in some ways`, `to an extent`, `it could be argued` |
| Signposting | One or more: `here's what you need to know`, `before we dive`, `in this article`, `let's break`, `buckle up` |
| Wordy construction | Three or more: `in order to`, `due to the fact that`, `it is important to note`, `a number of`, `with regard to` |
| Chained transition | Three or more: `moreover`, `furthermore`, `additionally`, `in addition`, `that said` |
| Trailing qualifier | Two or more: `for the most part`, `to a degree`, `where possible`, `in many ways` |
| Negation triad | Two or more `not just X, but Y` constructions, or a `is not about X. It is about Y` frame |
| Gerund opening | Two or more paragraphs opening on `Having`, `Knowing`, `Feeling`, `Realising` |
| Bold pseudo-heading | Two or more lines that are nothing but bold text |
| Bold lead-in bullets | Three or more bullets that open with a bold label, at 60% or more of the list |
| Em dash cluster | Four or more em dashes, unless a profile flags every one |

One bold heading or one buzzword is normal writing, which is why the thresholds are set where a pattern starts rather than where a single word appears.

## Tools

`voice_gate_check` runs the bundled rules over text or Markdown files and returns the findings with the counts behind them, so you can see what the gate would say without waiting for a turn to end.

```text
voice_gate_check(text="...")
voice_gate_check(paths=["docs/notes.md"])
```

`voice_gate_vale` is described under Vale below.

## Tests

```text
python tests/test_voice_gate.py
```

Twenty-one checks covering the rule families, the code-span exemption, the bot switches, the word floor, the tool registrations and the turn path. No dependencies and no test runner, because the host process carries neither PyYAML nor pytest for plugin code.

## Exceptions

A family can be wrong for a kind of file. A generated reference page repeats the same sentence on every page, and a template that leads every bullet with a bold label is doing its job. An exception silences one family for the files a glob matches and leaves the rule in force everywhere else.

```yaml
exceptions:
  signposting: docs/reference/**
  bold_lead_bullets: CHANGELOG.md, docs/api/*.md
```

The tell is any family name from the table above, in any spelling its aliases accept, or `all` to silence every family for those files. A glob is matched against the file name and against the whole path, so `README.md` matches in every directory and `docs/**` matches one tree. Write the block in the profile or in the plugin's Exceptions setting; both merge, and the profile is never modified by the setting.

An exception needs a path to test. Text passed to `voice_gate_check` without a `path` has none, so it is judged with the plain rules.

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
