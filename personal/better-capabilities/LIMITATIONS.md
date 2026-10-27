# LIMITATIONS

Personal edition of **Better Capabilities** (`better-capabilities`). This file tracks what
still stands between this tree and a Hermes Plugin Catalog listing, and what the 1.1.0 rebuild
resolved.

There is no `public/` copy. The product is a plugin-owned Settings page plus this plugin's own
Python routes, so an edition that dropped either half would be a stub.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md).
  A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor: no app DOM reach, no `document.body` observer, no
  dynamic code, no remote imports. Reviewers also read raw bridge calls and app `localStorage`
  keys by hand (`apps/desktop/src/contrib/runtime-loader.ts`).
- Catalog intake PR: [NousResearch/hermes-agent#115960](https://github.com/NousResearch/hermes-agent/pull/115960)
  (closed on the old DOM-based design; a fresh PR needs this clean tree).

## Resolved in 1.1.0

- **Raw Desktop bridge.** The page now uses `host.skills`, `host.toolsets`, `host.profiles`,
  `host.request('plugins.manage')`, `ctx.rest` and `ctx.os`. No `window.hermesDesktop` call
  remains in the renderer.
- **App-store write and synthetic clicks.** `hermes.desktop.pluginDecisions.v2` is neither read
  nor written from the renderer. Desktop-plugin switches are read-only for plugins by design
  (`sdk/bridge.ts`), so presets cover agent halves only and the page says so.
- **App DOM reach on the page.** Every control on the page is rendered by this plugin inside its own
  Settings page: no `data-slot` / `data-testid` selector, no injected tab, no mutation observer
  there. The page half alone reports `desktop surface — stays inside the plugin SDK surface`. The
  sidebar row actions below are the one deliberate exception.
- **Delete off-Windows.** A non-Windows host, or one whose Recycle Bin helper is unavailable, now
  falls back to `<hermes home>/better-capabilities-trash/` instead of raising first.
- **Zip symlinks.** `_zip_dir` skips symlinks and non-regular files, so a link to `~/.ssh` cannot
  ride along in the export.
- **Wrong-profile paths.** Every filesystem path resolves per request through
  `hermes_constants.get_hermes_home()`, which honors the backend's context-local home override.

## Deliberate exception: the Capabilities row actions (personal only)

The Capabilities nav row carries two dim glyphs — one opens this profile’s Skills editor, the other
picks a profile to edit Skills or Plugins for. The sidebar has no SDK hook for a per-row action
(`SIDEBAR_NAV_AREA` only ADDS rows; `SIDEBAR_NAV_PREFS_AREA` only hides or reorders them), so this
injects into the row and runs a `document.body` MutationObserver to repaint after sidebar renders.

Consequences, accepted on purpose:

- `hermes plugins validate` now FAILS `desktop surface` for this tree. Current findings:

  ```text
  app DOM reach (desktop/plugin.js:1106)
  app DOM reach (desktop/plugin.js:1284)
  ```

- A Desktop release that renames the row markup, the nav label or the row button drops these two
  glyphs until the selector is updated. Nothing else in the plugin depends on them: they are two
  `location.hash` writes.
- The public edition omits this block entirely. A listing cut never comes back to personal.

Needed hook: a per-row action or decoration slot on `sidebar.nav`
([#116305](https://github.com/NousResearch/hermes-agent/issues/116305)).

## Still open

1. **Private core imports (warning, not a failure).** `presets.py` reads plugin, skill and profile
   state through `hermes_cli.config`, `hermes_cli.skills_config`, `hermes_cli.tools_config`,
   `hermes_cli.plugins*` and `hermes_cli.web_server_profiles`. `hermes plugins validate` warns on
   each one under catalog rule 9. Closing this needs a `ctx`-side door for snapshotting capability
   state, or for the plugin to call `hermes` CLI verbs instead.
2. **The Capabilities page has no contribution area.** Row actions on the native page remain
   impossible for any plugin, so this one does not try. If one lands, the Skills sub-page can move
   its per-row controls back onto the native rows.
3. **`/preset` applies to the launch profile.** The slash command takes no profile argument, so it
   writes the profile its process runs as. The Settings page covers whichever profile the page is
   scoped to.

## Checklist before a fresh listing

- [x] SDK doors only. No `window.hermesDesktop.*`, `readDir`, or `readFileText`.
- [x] No writes to `hermes.desktop.pluginDecisions.v2`, no synthetic clicks.
- [x] `desktop surface` lint clean.
- [x] Delete works off-Windows without a 500-before-fallback.
- [x] `_zip_dir` does not follow symlinks.
- [ ] Private core imports reduced, or accepted by a reviewer.
- [ ] Sidebar row actions stripped from the public tree (personal-only reach-in; fails `desktop surface`).
- [ ] Pin the catalog `sha:` to the clean tree and open a fresh intake PR.
