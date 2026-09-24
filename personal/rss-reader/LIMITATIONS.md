# LIMITATIONS

Personal edition of **RSS Reader** (`rss-reader`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115972](https://github.com/NousResearch/hermes-agent/pull/115972)

## Blockers

### 1. MIT attribution (request-changes, backportable)

- **Personal behavior (before the fix):** fork of Adolanium `hermes-rss` with no upstream copyright notice.
- **Standing rule:** keep the Adolanium copyright in `LICENSE` and name the fork in the plugin README. MIT requires the notice to travel with the code.
- **Public edition:** same attribution.

### 2. README vs paywall mirrors (honesty, backportable text)

- **Personal behavior:** Settings can send capture through archive.today, 12ft.io, PrintFriendly, and the Wayback Machine.
- **Why it failed:** README said paywall bypass services are not used.
- **Standing rule:** personal README must describe those optional mirrors. Public drops the mirrors and the Settings checkbox so "not used" is true.
- **Public edition:** `PAYWALL_SERVICES` is empty. No Settings checkbox.

### 3. Self-improvement action (not admissible)

- **Personal behavior:** Settings Self-Improvement submits a prompt that tells the agent to edit the installed `plugin.js` in place.
- **Why it fails:** that is the same class as a self-updater. The only listed update path is a SHA-bump PR plus `hermes plugins update`.
- **Needed hook:** none. Do not list a build that `prompt.submit`s an install-tree edit.
- **Public edition:** action removed.

### 4. Private core import

- **Personal behavior:** `plugin_api.py` imports `tui_gateway.server._broadcast_global_event` to open the preview pane.
- **Why it fails:** private core import. Use `ctx.socket` frames when item 8 in [#116305](https://github.com/NousResearch/hermes-agent/issues/116305) exists.
- **Public edition:** `/preview` returns 501. The desktop half falls back to the system browser.

### 5. Unsandboxed embeds and app layout store

- **Personal behavior:** `sanitizeRichHtml` lets https `iframe`/`object`/`embed` through unsandboxed. A raw Electron `<webview>` mounts on `persist:hermes-preview`. Ticker code reads `hermes.desktop.layoutTree.v2`.
- **Why it fails:** rule 8 reach-in. Sandboxed embed primitive is item 9 in [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).
- **Public edition:** those tags are stripped, no webview, no layout-store read.

### 6. Script-strip regex (lint false positive)

- **Personal behavior:** `/<script.../` literal in `extractReadable`.
- **Why it fails:** catalog `desktop surface` lint treats it as script injection. Item 10 is a lint fix on their side.
- **Public edition:** the literal is split so pinned-source-validate can pass before item 10 lands.

### 7. YouTube cookies must be pasted (security limitation)

- **Behavior:** YouTube cookies accept pasted header text or Netscape cookie-export text in Settings → Advanced.
- **Limitation:** Cookie-file paths are rejected. The dashboard no longer reads local files or forwards file contents to YouTube.

## Checklist before listing personal

- [ ] Adolanium MIT notice still in LICENSE and README.
- [ ] README matches whether paywall mirrors exist in that edition.
- [ ] No `prompt.submit` that edits the installed plugin tree.
- [ ] No `tui_gateway.server._broadcast_global_event` unless item 8 is merged and used.
- [ ] No unsandboxed iframe/webview and no `hermes.desktop.layoutTree.v2` unless item 9 is merged and used.
- [ ] Re-pin catalog `sha:` to `public/rss-reader` and comment on #115972.
