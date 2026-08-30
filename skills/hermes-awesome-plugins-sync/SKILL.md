---
name: hermes-awesome-plugins-sync
category: hermes
description: "Use when provider-status, hermes-break, or better-colors changes — sync live plugins into the hermes-agent-awesome-plugins monorepo."
version: 1.0.0
tags:
- hermes
- plugins
- sync
related_skills:
- hermes-plugin-authoring
---

# Hermes Awesome Plugins Sync

Keep `C:/git-public/hermes-agent-awesome-plugins` (GitHub `apoapostolov/hermes-agent-awesome-plugins`) in sync with the live installs at `C:/Users/theap/AppData/Local/hermes/plugins/{provider-status,hermes-break,better-colors}`. When any of those plugins is touched, the monorepo must be updated in the same session — no drift.

## Trigger

- Any edit to `provider-status`, `hermes-break`, or `better-colors`.
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
hermes plugins doctor hermes-break
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
- `C:/Users/theap/AppData/Local/hermes/plugins/hermes-break` → `C:/git-public/hermes-agent-awesome-plugins/plugins/hermes-break`
- `C:/Users/theap/AppData/Local/hermes/plugins/better-colors` → `C:/git-public/hermes-agent-awesome-plugins/plugins/better-colors` (root `plugin.js` is moved to `desktop/plugin.js` for the pack layout)

It preserves `.example` files and `README.md` in the monorepo if they are newer than live stubs.

Manual fallback (if script missing):

```bash
python -c "
import shutil, pathlib
for name in ('provider-status','hermes-break','better-colors'):
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
git -C C:/git-public/hermes-agent-awesome-plugins commit -m "sync: provider-status vX.Y.Z + hermes-break vA.B.C — <one-line why>"
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

## Also mirrored in-repo

The same skill lives at `skills/hermes-awesome-plugins-sync/` inside the monorepo so anyone cloning it sees the sync contract. Changes to this SKILL.md must be mirrored there as well.

## Why this exists

Without this, the monorepo drifts and the public pack ships stale code. This skill is the only sanctioned path to update `hermes-agent-awesome-plugins`.
