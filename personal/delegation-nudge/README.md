<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Delegation Nudge</h1>
  <strong>A live reminder that a turn is spending its own context on work a subagent should carry.</strong>
  <p>Counts a turn's own loop iterations and, past a threshold with no dispatch, names the routes once.</p>
</div>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.1-blue" alt="Version 1.1.1" />
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT" />
</p>

## What it does

A long turn is usually one decision away from being cheaper. Hermes can hand reading, sweeping and independent items to a subagent on a free or cheap route, but nothing in a busy thread notices when that hand-off should have happened. This plugin notices, once, and says so in a sentence the model can act on.

It watches each outbound provider request. When a turn has run ten loop iterations without a `delegate_task`, it appends one short note to that turn's user message naming the routes: `scan` for sweeps and lookups, `research` for many pages, `deep` for judgment, `code` for edits and tests. The note also says when to ignore it, so a turn that genuinely needs the thread's own context, or a caller waiting on an answer, is never argued with.

Nothing renders in the app. The reminder reaches the model, not the window, which is why this plugin has no screenshot.

## How it decides

| Step | Behaviour |
| --- | --- |
| Count | Uses the turn's own loop counter, so a session with hundreds of older tool results still measures only the current turn |
| Threshold | Ten iterations, configurable |
| Dispatch | One `delegate_task` in the turn silences the rest of it |
| Subagents | Silent inside a subagent, where `delegate_task` is not available |
| Repeat | Once per turn by default, or every N further iterations if you set it |
| Failure | A middleware that raises is logged and skipped by the runtime, so a request is never broken |

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| Enable the reminder | on | Turns the whole plugin off without uninstalling it |
| Loop iterations before a reminder | 10 | How far a turn may run before the note appears |
| Remind again every N further iterations | 0 | 0 means once per turn; a positive number re-arms it |

Settings live in `config.yaml` under `plugins.entries.delegation-nudge.settings`.

## What the agent sees

```text
[delegation check] 10 steps into this turn, none of them delegate_task. If what is left is
reading, sweeping, or independent items, dispatch now and route it: scan (free, file sweeps
and lookups), research (free, many pages), deep (cheap, judgment and debugging), code (cheap,
edits and tests). If the work genuinely needs this thread's context, or the caller needs an
answer mid-task, ignore this note and continue.
```

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/delegation-nudge
```

Single plugin from the catalog path:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins#personal/delegation-nudge
```

Then enable it once:

```bash
hermes plugins enable delegation-nudge
```

Enabling reloads the plugin set, so the middleware goes live in a running gateway. A turn already in flight fires at its first request after the reload, which is why the first log lines can carry a number larger than your threshold.

## Requirements and limits

- No UI, no tools, no network. It is one `llm_request` middleware and three small hooks.
- It changes the request it is asked to change and nothing else: no tool result is rewritten, and the system prompt is untouched.
- The reminder is a hint, not a gate. A turn that decides to keep working inline is allowed to, and that is deliberate: the alternative is a plugin arguing with context it cannot see.
- Proof it is running: `grep "delegation-nudge: reminder" %LOCALAPPDATA%/hermes/logs/agent.log`.
- Turn it off with `hermes plugins disable delegation-nudge`.

## Tests

```bash
python -m unittest discover -s personal/delegation-nudge/tests -t .
```

The suite drives the middleware with a fake context and covers both payload shapes, the threshold, dispatch silence, subagent silence, the disabled switch and `repeat_after`.

## License

[MIT](../../LICENSE)
