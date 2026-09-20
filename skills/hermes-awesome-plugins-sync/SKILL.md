---
name: hermes-awesome-plugins-sync
category: hermes
description: "Use when provider-status, tool-break, or better-colors changes — sync live plugins into the hermes-agent-awesome-plugins monorepo."
version: 1.0.0
tags:
- hermes
- plugins
- sync
related_skills:
- hermes-plugin-authoring
---

# Hermes Awesome Plugins Sync

Keep `C:/git-public/hermes-agent-awesome-plugins` (GitHub `apoapostolov/hermes-agent-awesome-plugins`) in sync with the live installs at `C:/Users/theap/AppData/Local/hermes/plugins/{provider-status,tool-break,better-colors}`. When any of those plugins is touched, the monorepo must be updated in the same session — no drift.

## Trigger

- Any edit to `provider-status`, `tool-break`, or `better-colors`.
- Version bump, bug fix, UI tweak, new provider — all of them.
- Explicit "sync the awesome plugins" / "push to awesome-plugins".

## Rules

1. Live dir is source of truth. Monorepo `plugins/<name>/` is a sanitized mirror — never edit it directly.
2. Never ship secrets: strip `config.json`, `library.env`, `.env`, `*.key`, `__pycache__`, `*.pyc`.
3. Always repin `hermes-pack.yaml` refs to the new commit SHA after push — packs require exact 40-char SHAs.
4. `README.md` at the monorepo root is the "show this repo to Hermes" installer. Keep its prompt + `hermes-pack.yaml` raw URL current.

## Procedure (do this every time)

### 1. Validate live plugins

```bash
hermes plugins doctor provider-status
hermes plugins doctor tool-break
```

Fix any failures before syncing.

### 2. Sync files (sanitized copy)

Run the helper:

```bash
python "C:/Users/theap/AppData/Local/hermes/skills/hermes-awesome-plugins-sync/scripts/sync.py"
# or directly:
python "C:/git-public/hermes-agent-awesome-plugins/skills/hermes-awesome-plugins-sync/scripts/sync.py"
```

It copies:

- `C:/Users/theap/AppData/Local/hermes/plugins/provider-status` → `C:/git-public/hermes-agent-awesome-plugins/plugins/provider-status` (ignores `config.json`, `library.env`, `__pycache__`)
- `C:/Users/theap/AppData/Local/hermes/plugins/tool-break` → `C:/git-public/hermes-agent-awesome-plugins/plugins/tool-break`
- `C:/Users/theap/AppData/Local/hermes/plugins/better-colors` → `C:/git-public/hermes-agent-awesome-plugins/plugins/better-colors` (root `plugin.js` is moved to `desktop/plugin.js` for the pack layout)

It preserves `.example` files and `README.md` in the monorepo if they are newer than live stubs.

Manual fallback (if script missing):

```bash
python -c "
import shutil, pathlib
for name in ('provider-status','tool-break','better-colors'):
  src=pathlib.Path(f'C:/Users/theap/AppData/Local/hermes/plugins/{name}')
  dst=pathlib.Path(f'C:/git-public/hermes-agent-awesome-plugins/plugins/{name}')
  if dst.exists(): shutil.rmtree(dst)
  shutil.copytree(src,dst,ignore=shutil.ignore_patterns('__pycache__','*.pyc','config.json','library.env','.env'))
"
```

### 3. Refresh examples if needed

If new config keys were added, update `plugins/provider-status/config.json.example` and `library.env.example` (dummy values only).

### 4. Commit → push → repin pack

```bash
git -C C:/git-public/hermes-agent-awesome-plugins status
git -C C:/git-public/hermes-agent-awesome-plugins add -A
git -C C:/git-public/hermes-agent-awesome-plugins commit -m "sync: provider-status vX.Y.Z + tool-break vA.B.C — <one-line why>"
git -C C:/git-public/hermes-agent-awesome-plugins push
# capture new SHA then patch hermes-pack.yaml refs
SHA=$(git -C C:/git-public/hermes-agent-awesome-plugins rev-parse HEAD)
# sed both entries to $SHA, commit+push again as "chore: repin pack to $SHA"
```

Or use `scripts/sync.py --commit --push --repin` which does all of it.

### 5. Verify

```bash
hermes plugins pack show C:/git-public/hermes-agent-awesome-plugins/hermes-pack.yaml
hermes plugins pack show https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Both must parse and list 3 plugins with exact SHAs.

## Installing monorepo → live (Win11 pull-latest path)

`hermes plugins install` and `hermes plugins pack install` CANNOT install Apo's own plugins on Hermes 0.21.x: every `plugin.yaml` is `manifest_version: 2` and the installer caps at v1 ("installer only supports up to 1"), while the runtime loads v2 fine. Bare-name install from the catalog also fails because the Revell index PRs have not landed. Do NOT npm or curl the monorepo; use the hand-copy path below.

Monorepo layout after the 2026-09 restructure: pack sources are `personal/<name>/` (and public exports `public/<name>/`), not `plugins/<name>/`. The old `plugins/` dirs are deleted from the repo. Install therefore means copying `personal/<name>` → live plugin dir and mirroring `desktop/plugin.js` → `desktop-plugins/<name>/plugin.js`, preserving live `config.json`/`library.env`.

```bash
python "C:/Users/theap/AppData/Local/hermes/cache/scratch/awesome-sync.py"   # reverse sync: repo personal/ -> live
hermes plugins doctor <name>                                                 # every installed plugin must pass
hermes plugins enable intelligent-tool-break                                 # one name per call; enable replaces
hermes plugins enable better-session-appearance                              # the old tool-break / better-colors
hermes plugins disable better-colors tool-break                              # also one name per call
hermes config get plugins.enabled                                            # verify final set
```

The reverse-sync script is a scratch-style helper: it wipes each live plugin dir (after backing up `config.json`/`library.env`), copies the `personal/<name>` tree, restores the secrets, and updates the desktop mirror. Plugin works best as a saved script in this skill — promote `awesome-sync.py` to `scripts/` when the layout settles.

Renames to respect: `tool-break` → `intelligent-tool-break`, `better-colors` → `better-session-appearance`. Disable the old names so hooks and desktop code do not double-load.

## Also mirrored in-repo

The same skill lives at `skills/hermes-awesome-plugins-sync/` inside the monorepo so anyone cloning it sees the sync contract. Changes to this SKILL.md must be mirrored there as well.

## Why this exists

Without this, the monorepo drifts and the public pack ships stale code. This skill is the only sanctioned path to update `hermes-agent-awesome-plugins`.
