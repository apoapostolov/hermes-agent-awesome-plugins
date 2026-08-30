# hermes-agent-awesome-plugins

> **Show this repo to Hermes and it installs everything.**

Hand-picked, battle-tested Hermes plugins that earn their keep. One pack, one prompt.

## Just tell Hermes

Paste this into any Hermes session that can see this repo (local checkout `C:/git-public/hermes-agent-awesome-plugins` or the GitHub URL):

```
Install the awesome plugins from this repo — read hermes-pack.yaml and README.md
then run the install for me. Source: https://github.com/apoapostolov/hermes-agent-awesome-plugins
```

Hermes will:

1. Read `hermes-pack.yaml` (pinned SHAs → reproducible)
2. Run `hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml`
3. Walk you through capability consents + any `requires_env` prompts
4. Verify with `hermes plugins list` and `hermes plugins pack show <url>`

No Hermes? Do it manually:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
# or per-plugin
hermes plugins install github:apoapostolov/hermes-agent-awesome-plugins --ref <sha>  # subdir via pack only
```

## What's inside

| Plugin | What it does | Kind |
|---|---|---|
| [**provider-status**](plugins/provider-status/README.md) | Unified multi-provider quota/status bar — chips (`↑ used` / `↓ remaining`), setup dialog, OAuth (Grok/Codex), key-pool + reset-day auto-rotation. | native + desktop + dashboard |
| [**hermes-break**](plugins/hermes-break/README.md) | `/break` / `/again` — kill a hung tool spawn without aborting the turn. Composer strip with elapsed grades + auto-break. | native + desktop |

More plugins will be curated here over time. The pack always pins exact commits, never floating tags.

## How it works

- Each plugin lives in `plugins/<name>/` with its own `plugin.yaml`, Python backend, and `desktop/plugin.js`.
- `hermes-pack.yaml` pins `repo + subdir + ref` for every plugin — that file is the source of truth.
- `hermes plugins pack install <url>` fans out to ordinary pinned installs (`--ref <sha>`), then every plugin's declared capabilities go through the **same per-plugin consent** as a standalone install — packs never bulk-grant.
- Secrets never ride in the pack. Plugins declare `requires_env` and prompt for them at install.

## Local dev / sync

This repo mirrors the live installs at `C:/Users/theap/AppData/Local/hermes/plugins/{provider-status,hermes-break}`.

- Make changes in the live plugin dir, verify with `hermes plugins doctor <name>`.
- Then run the sync skill to mirror + bump + pin the pack:

```
# Tell Hermes:
Sync the awesome-plugins monorepo — copy live plugins into C:/git-public/hermes-agent-awesome-plugins, sanitize secrets, refresh README wiring, commit + push, then update hermes-pack.yaml refs to the new commit SHA.
```

Skill: [`skills/hermes-awesome-plugins-sync`](skills/hermes-awesome-plugins-sync/SKILL.md) — always keep the monorepo in sync when you touch these plugins.

## Requirements

- Hermes Agent `>= 0.3` (plugins + packs)
- Windows / macOS / Linux — both plugins are cross-platform; `hermes-break` uses `taskkill /F /T` on Windows and `kill -9` on POSIX.

## License

MIT — see [LICENSE](LICENSE).
