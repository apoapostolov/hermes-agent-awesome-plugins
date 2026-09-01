# Hermes Agent Awesome Plugins

A Hermes Agent plugin pack. Seven plugins, pinned to exact SHAs in `hermes-pack.yaml`. Install the pack, not a GitHub Release.

Requires Hermes Agent **0.21.0** or newer (shareable plugin packs).

## What's New in 1.5.0

**Opaque Composer** keeps the desktop composer solid while you scroll, so earlier message text stays readable.

**Scroll on Switch** lands at the newest message when you switch sessions, including newly mounted sessions, and never reacts to new messages or AI streaming.

See [CHANGELOG.md](CHANGELOG.md) for the notes.

## Plugins

| Plugin | What it does |
| --- | --- |
| [provider‑status](plugins/provider-status/README.md) | Unified multi-provider quota usage tracking in the status bar, with support for OAuth, color-based warnings, and multiple accounts per provider with Hermes key rotation on exhaust. |
| [tool‑break](plugins/tool-break/README.md) | Never let a stalled tool call force you to cancel a long task. Abort an in-flight call with `/break`, instruct with `/break {message}`, or force it to repeat with `/again`. |
| [better‑colors](plugins/better-colors/README.md) | Improve your session list with full name color, bolding, and a Codicon icon when a session is idle. |
| [drag‑to‑pin‑session](plugins/drag-to-pin-session/README.md) | Reorganize your pinned sessions with drag-and-drop. Drag a session into the Pinned section to pin it, or drag it out to unpin it. |
| [opaque‑composer](plugins/opaque-composer/README.md) | Keep the desktop composer solid while scrolling so conversation text stays readable. |
| [scroll‑on‑switch](plugins/scroll-on-switch/README.md) | Keep the active session transcript at the bottom when switching sessions. |
| [busy‑shortcuts](plugins/busy-shortcuts/README.md) | Add `/i` for interrupt mode, `/q` for queue mode, and `/s` for steer mode. Prompt arguments retain Hermes' built-in queue and steer behavior. |

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) `>= 0.21.0`.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Each plugin still gets its own capability consent. Packs do not bulk-grant. Secrets are `requires_env` at install, not in the pack.

Verify:

```bash
hermes plugins list
hermes plugins pack show https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

From a Hermes session that can see this repo, you can also ask it to read `hermes-pack.yaml` and run that pack install.

## How It Works

`hermes-pack.yaml` is the source of truth: `repo` + `subdir` + 40-char `ref` per plugin. `hermes plugins pack install` fans out to ordinary pinned installs.

Each plugin lives under `plugins/<name>/` with its own `plugin.yaml` and desktop entry. `better-colors`, `drag-to-pin-session`, `opaque-composer`, and `scroll-on-switch` are desktop-only.

## Requirements

- Hermes Agent `>= 0.21.0` (plugin packs)
- Windows / macOS / Linux. `tool-break` uses `taskkill /F /T` on Windows and `kill -9` on POSIX. `better-colors`, `drag-to-pin-session`, `opaque-composer`, and `scroll-on-switch` are desktop-only.

## Documentation

- [provider-status](plugins/provider-status/README.md)
- [tool-break](plugins/tool-break/README.md)
- [better-colors](plugins/better-colors/README.md)
- [drag-to-pin-session](plugins/drag-to-pin-session/README.md)
- [opaque-composer](plugins/opaque-composer/README.md)
- [scroll-on-switch](plugins/scroll-on-switch/README.md)
- [busy-shortcuts](plugins/busy-shortcuts/README.md)
- [hermes-awesome-plugins-sync](skills/hermes-awesome-plugins-sync/SKILL.md) — maintainer skill to mirror live plugin dirs into this repo and repin `hermes-pack.yaml`

## Support

Support, feedback, and feature ideas: [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov
