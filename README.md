# Hermes Agent Awesome Plugins

A Hermes Agent plugin pack. Four plugins, pinned to exact SHAs in `hermes-pack.yaml`. Install the pack, not a GitHub Release.

## What's New in 1.1.0

`drag-to-pin-session` makes the **Pinned** section of the Sessions sidebar a drag container. Drag a session in to pin it, drag a pinned row out to unpin it. No rebuild, no restart.

See [CHANGELOG.md](CHANGELOG.md) for the notes.

## Plugins

| Plugin | What it does |
| --- | --- |
| [provider-status](plugins/provider-status/README.md) | Quota chips across providers (`↑ used` / `↓ remaining`). Grok and Codex OAuth. Key-pool rotation when remaining is low. Reset-day rotation per key. |
| [hermes-break](plugins/hermes-break/README.md) | `/break` and `/again` kill a hung spawn tree and leave the turn running. `/again` reissues the call once. |
| [better-colors](plugins/better-colors/README.md) | Session list appearance: color and bold titles, extra Appearance colors, idle-bullet glyphs. |
| [drag-to-pin-session](plugins/drag-to-pin-session/README.md) | Drag sessions into the Pinned section to pin, drag them out to unpin. Desktop-only, hot-reloads. |

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) `>= 0.3`.

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

Each plugin lives under `plugins/<name>/` with its own `plugin.yaml` and desktop entry. `better-colors` and `drag-to-pin-session` are desktop-only (session list overlays).

## Requirements

- Hermes Agent `>= 0.3` (plugins + packs)
- Windows / macOS / Linux. `hermes-break` uses `taskkill /F /T` on Windows and `kill -9` on POSIX. `better-colors` and `drag-to-pin-session` are desktop-only (session list overlays).

## Documentation

- [provider-status](plugins/provider-status/README.md)
- [hermes-break](plugins/hermes-break/README.md)
- [better-colors](plugins/better-colors/README.md)
- [drag-to-pin-session](plugins/drag-to-pin-session/README.md)
- [hermes-awesome-plugins-sync](skills/hermes-awesome-plugins-sync/SKILL.md) — maintainer skill to mirror live plugin dirs into this repo and repin `hermes-pack.yaml`

## Support

Support, feedback, and feature ideas: [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov
