# Reasoning Switch

Rotate the focused session's reasoning effort straight from the status bar.

## What you get

- **Status bar word + gear**: the word shows the active reasoning level for the focused chat. Click it to cycle through the levels you checked; the gear opens the setup dialog.
- **Standardized levels**: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra` — the same vocabulary the backend validates (`VALID_REASONING_EFFORTS`).
- **Per-level color** from a theme-aware palette, applied to the level word in the dialog.
- **Rotation checkboxes**: pick which levels a click cycles through.
- **Prompt limits**: cap any level to N user prompts. When the limit is spent, Reasoning Switch automatically demotes to the next lower level in your rotation — for example, High for 3 prompts, then back to Medium.

## How it works

The click and the dialog use the same session-scoped gateway call the app's own model menu makes (`config.set`, key `reasoning`). The global profile default is never touched, so you can run one chat hot while the rest of your setup stays put. The prompt counter rides the "awaiting response" signal of the focused session.

## Install

Install the plugin pack (see the [repo README](../../README.md)) or copy this directory into your Hermes plugins folder and run:

```bash
hermes plugins enable reasoning-switch --no-allow-tool-override
```

## License

[MIT](../../LICENSE)
