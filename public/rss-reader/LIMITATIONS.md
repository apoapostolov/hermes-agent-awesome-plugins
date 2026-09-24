# LIMITATIONS

Public edition of **RSS Reader** (`rss-reader`). This file records the deliberate catalog-runtime cuts in this edition and the SDK migration state.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside the plugin SDK.
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

### 4. Private core import — RESOLVED by SDK (item 8, PR #120918)

- **Was:** `plugin_api.py` imported `tui_gateway.server._broadcast_global_event`.
- **Now (both editions):** `hermes_cli.plugin_events.broadcast_plugin_event("rss-reader", ...)` — the sanctioned bridge. `/preview` emits `plugin.rss-reader.preview`; the desktop half listens with `host.onEvent` and opens the workspace browser. Commands ride the same bridge, which deleted the `commands.jsonl` queue, the `GET /commands` route, and the 3-second poll.
- **Editions:** identical transport now. No divergence.

### 5. Unsandboxed embeds and app layout store — RESOLVED by SDK (item 9, PR #120927)

- **Was:** raw Electron `<webview>` on `persist:hermes-preview` (browser + YouTube) and a `hermes.desktop.layoutTree.v2` read in the ticker dock-watch.
- **Now (both editions):** `<SandboxedFrame>` renders the RSS browser pane and YouTube embeds. The dock-watch is gone: the ticker pane registers with `dock: { enforce: true }`, the SDK-sanctioned placement, so nothing reads the app layout store.
- **Editions:** identical. No divergence.

### 6. Script-strip regex (lint false positive)

- Fixed upstream: the `desktop surface` lint no longer flags RegExp script sanitisers (PR #120918). The string-concat dodge is removable; both editions carry the plain literal.

### 7. YouTube cookies must be pasted (security limitation)

- **Behavior:** YouTube cookies accept pasted header text or Netscape cookie-export text in Settings → Advanced.
- **Limitation:** Cookie-file paths are rejected. The dashboard no longer reads local files or forwards file contents to YouTube.

## Checklist before listing personal

- [ ] Adolanium MIT notice still in LICENSE and README.
- [ ] README matches whether paywall mirrors exist in that edition.
- [ ] No `prompt.submit` that edits the installed plugin tree.
- [ ] Transport stays on `broadcast_plugin_event` (no `tui_gateway` imports).
- [ ] Embeds stay on `SandboxedFrame`; no webview, no layout-store reads.
- [ ] Re-pin catalog `sha:` to `public/rss-reader` and comment on #115972.
