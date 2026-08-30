# Hermes Agent Awesome Plugins

A Hermes Agent plugin pack. Two plugins, pinned to exact SHAs in `hermes-pack.yaml`. Install the pack, not a GitHub Release.

## What's New in 1.0.0

First pack. `provider-status` shows quota chips across providers, with Grok/Codex OAuth plus key-pool and reset-day rotation. `hermes-break` adds `/break` and `/again` so you can kill a hung spawn without aborting the turn.

See [CHANGELOG.md](CHANGELOG.md) for the notes.

## Plugins

| Plugin | What it does |
| --- | --- |
| [provider-status](plugins/provider-status/README.md) | Quota chips across providers (`↑ used` / `↓ remaining`). Grok and Codex OAuth. Key-pool rotation when remaining is low. Reset-day rotation per key. |
| [hermes-break](plugins/hermes-break/README.md) | `/break` and `/again` kill a hung spawn tree and leave the turn running. `/again` reissues the call once. |

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

Each plugin lives under `plugins/<name>/` with its own `plugin.yaml`, Python backend, and desktop entry.

## Requirements

- Hermes Agent `>= 0.3` (plugins + packs)
- Windows / macOS / Linux. `hermes-break` uses `taskkill /F /T` on Windows and `kill -9` on POSIX.

## Documentation

- [provider-status](plugins/provider-status/README.md)
- [hermes-break](plugins/hermes-break/README.md)
- [hermes-awesome-plugins-sync](skills/hermes-awesome-plugins-sync/SKILL.md) — maintainer skill to mirror live plugin dirs into this repo and repin `hermes-pack.yaml`

## Support

Support, feedback, and feature ideas: [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov
