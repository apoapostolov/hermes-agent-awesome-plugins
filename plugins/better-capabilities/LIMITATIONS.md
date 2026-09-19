# LIMITATIONS

Personal edition of **Better Capabilities** (`better-capabilities`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

There is no `public/` copy. The product is Capabilities-page reach-in. A listed edition would be a stub until the hooks below exist.

Before you pin personal to the catalog, or recreate a public edition, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115960](https://github.com/NousResearch/hermes-agent/pull/115960)

## Blockers

### 1. Raw Desktop bridge instead of the SDK

- **Personal behavior:** calls `window.hermesDesktop.api`, `readDir`, and `readFileText`. Hits `/api/skills/toggle`, `/api/tools/toolsets`, and `/api/profiles` as the user.
- **Why it fails:** the SDK door for gateway RPC is `host.request`. Typed skills / toolsets / profiles are not a public plugin contract yet.
- **Needed hook:** `host.request` plus a typed skills/toolsets/profiles surface ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 6).
- **Public edition:** none.

### 2. App-store write and synthetic clicks

- **Personal behavior:** writes `hermes.desktop.pluginDecisions.v2` and fires synthetic clicks on app switches.
- **Why it fails:** app persisted keys and app-owned controls are not a plugin contract.
- **Needed hook:** `host.pluginDecisions` or equivalent from [#116305](https://github.com/NousResearch/hermes-agent/issues/116305). No synthetic clicks.
- **Public edition:** none.

### 3. Delete path off-Windows

- **Personal behavior:** the delete route can 500 off-Windows before its fallback runs (`plugin_api.py`).
- **Why it fails:** listing asks for a working delete path on every supported OS. This is a defect, independent of rule 8.
- **Needed hook:** none. Fix the fallback so non-Windows delete never 500s first.
- **Public edition:** none.

### 4. Zip follows symlinks

- **Personal behavior:** `_zip_dir` follows symlinks inside a skill dir. A symlink to `~/.ssh` can land in the export zip.
- **Why it fails:** LOW security finding on the intake. Listed builds must skip symlinks in the zip.
- **Needed hook:** none. Skip symlinks in `_zip_dir` before any listing attempt.
- **Public edition:** none.

## Checklist before listing personal

- [ ] SDK bridge only. No `window.hermesDesktop.api`, `readDir`, or `readFileText`.
- [ ] No writes to `hermes.desktop.pluginDecisions.v2`.
- [ ] No synthetic clicks on app switches.
- [ ] Skills / toolsets / profiles go through item 6 in #116305 once merged.
- [ ] Delete works off-Windows without a 500-before-fallback.
- [ ] `_zip_dir` does not follow symlinks.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115960.
