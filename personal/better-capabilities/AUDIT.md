# Audit: Better Capabilities against the current Hermes Desktop build

Written against the **running** Desktop build (`c714c42431`, `main`, 2026-10-26) and the
older checkout at `C:/git-ext/hermes-agent` for history. Version stays `1.0.0` until the
owner calls the audit finished.

## Why the plugin died

Not a missing feature and not a missing SDK hook. Two independent kills:

1. **Admission.** `hermes_cli/plugin_validate_desktop.py:36-40` fails the `desktop surface`
   check on `document.querySelector*(…[data-slot|data-tour|data-sidebar|data-testid…])` and on
   `.observe(document.body, {childList|subtree})`. Catalog rule 8
   (`plugin-catalog/README.md`) says a listed desktop half may only use the plugin SDK. The old
   `desktop/plugin.js` painted every control by querying and mutating app markup, so no fix keeps
   it listable.
2. **The surface itself.** The Capabilities page consumed no contribution area before and
   consumes none now (`grep` over `app/capabilities` finds no registry area). There is no row
   action slot to put a button into. That part of the old design has no future.

The retirement note also under-read the SDK. It said "`host.skills` exposes `list` and
`setEnabled` only, and presets have no API". `host.skills`/`host.toolsets`/`host.profiles`/
`host.pluginDecisions` landed **2026-09-24** (`488cd566ba`) and `ctx.registerSettingsPage` →
Settings ▸ Plugins landed **2026-10-05** (`ea0e4299ec`). The plugin was retired 2026-10-20, two weeks
after the second door shipped and with the first already open.

## What the new Capabilities page does natively

Verified in the running build's source, not the docs.

| Tab | Row actions | Detail | Delete | Zip | Skill file browse | Presets |
| --- | --- | --- | --- | --- | --- | --- |
| Skills | enable switch, install (+) for hub rows | SKILL.md body, Edit (agent/external only), Archive | **no** (`uninstallSkillFromHub` has no caller) | **no** | **no** (SKILL.md only) | **no** |
| Toolsets | enable switch | dialog: tools, keys, provider matrix | **no** | no | no | **no** |
| Connectors | connect / disconnect / test | account + server dialogs | yes (servers, accounts) | no | no | **no** |
| Plugins | whole-package switch | per-half switches, update, settings gear, reveal | **yes**, in the detail pane: agent half when `source` is `user`/`git` (`plugins.manage remove`), standalone desktop disk plugin (Electron) | no | no | **no** |

So: plugin uninstall is native now (drop that feature), skills keep **no** delete, **no** zip,
**no** folder browse, and the page still has **no** presets — which is everything else the plugin
did.

## Return matrix

| Old feature | Old mechanism (dead) | New door | Verdict |
| --- | --- | --- | --- |
| Delete plugin from a row | DOM trash button + own `/delete` on any folder under `plugins/` | Native: Capabilities ▸ Plugins detail, or `plugins.manage remove` (agent) / Electron `uninstallDiskPlugin` (standalone desktop) | **Drop.** Native is better: it prunes package markers and folder grants; raw folder delete left stale state. |
| Reveal plugin folder | own `/resolve` + `window.hermesDesktop.revealPath` | Native folder icon per row + plugins-root button; `ctx.os.revealPath` for our own paths | **Drop** (redundant). |
| Package (zip) a skill | DOM button between Edit and Archive + `/zip` + base64 blob download | No native equivalent. Own Settings page + `ctx.rest('/zip')` | **Return.** |
| Delete a skill folder | DOM trash on the skill row + `/delete` → Recycle Bin | No native equivalent. Own page + `ctx.rest('/delete')` | **Return.** |
| Browse other `.md` files in a skill | hid native blocks with `display:none`, own `<pre>`, `readDir`/`readFileText` | No native directory listing (backend has no listing route). Own page + `/files` + `/file` | **Return**, rendered in our own pane; no native DOM touched. |
| Presets tab (skills/tools/plugins on-off) | injected a tab into `[data-capability-tabs]`, flipped `[data-slot=switch]` by synthetic click, wrote `hermes.desktop.pluginDecisions.v2`, read `/api/skills` raw | `ctx.registerSettingsPage` (own page in Settings ▸ Plugins) + `host.skills.setEnabled` + `host.toolsets.setEnabled` + `host.request('plugins.manage', {action:'toggle'})` + own `/presets` store | **Return**, redesigned. |
| Desktop-plugin on/off inside a plugin preset | localStorage write + synthetic clicks | `host.pluginDecisions` is **read-only on purpose** (`sdk/bridge.ts` header: a `set()` would let one plugin flip another plugin's switch; the singleton `host` cannot tell which plugin is calling) | **Drop**, stated in the UI instead of faked. |
| `/preset save\|apply` from chat | python only, no UI needed | unchanged | **Keep**, and extend to `tools`. |

## What the last month added that this plugin should use

| Door | Landed | Use |
| --- | --- | --- |
| `ctx.registerSettingsPage` (+ sub-pages) → Settings ▸ Plugins | 2026-10-05 `ea0e4299ec` | The whole UI now lives here. React render, app components, no DOM reach, removed with the plugin. |
| `host.skills` / `host.toolsets` / `host.profiles` / `host.pluginDecisions` | 2026-09-24 `488cd566ba` | Typed, profile-scoped replacements for `window.hermesDesktop.api` and the raw localStorage read. |
| `ctx.storage` (namespaced `hermes.plugin.<id>.*`) | earlier | UI prefs only; the preset store stays in Python so chat and Desktop agree. |
| `ctx.os.revealPath` / `ctx.os.pickSavePath` | in build | Sanctioned reveal; no raw bridge. |
| `ctx.runAction('nav.capabilities')` | 2026-10-10 `0e0539c0f0` | Send the user to the native page for the things we deliberately do not duplicate. |
| `ctx.rest` namespace guard (`pluginPathSuffix`) | in build | Our routes are already `/api/plugins/better-capabilities/*`. |

Not usable, checked so nobody tries again:

- **`ctx.files` cannot open the skills tree.** A folder holding Hermes data is refused with
  `error: 'protected'` (`contrib/plugin-files.ts` + `electron/plugin-files.ts`). Skill file work
  has to stay in the plugin's own Python half.
- **No Capabilities contribution area, now or planned.** `CapabilitiesView` is exported for
  plugins to *embed* the page (`embedded`, `fixedProfile`, `fixedConnection`), never to extend it.
- **`host.request` is unfiltered**, so `plugins.manage`/`skills.manage`/`profiles.*` are all
  reachable — but a plugin must not behave like the page where the page already exists.

## Fixes to make while returning the features

Carried from `LIMITATIONS.md`, all four are cheap and all four are real:

1. Renderer reaches the raw bridge → replaced by `host.*` + `ctx.rest`.
2. Writes to `hermes.desktop.pluginDecisions.v2` and synthetic clicks → deleted, not ported.
3. `/delete` 500s off-Windows before its fallback runs → fall back to a moved-aside folder on
   every platform.
4. `_zip_dir` follows symlinks (a link to `~/.ssh` ships in the export) → skip symlinks and
   non-regular files.
5. New: `HOME` was resolved once at import, so a per-request profile scope could address the
   wrong profile's tree → resolve per request via `hermes_constants.get_hermes_home()`, which
   honors the backend's context-local override.

## What still keeps it off the catalog

Rule 8 is satisfied by this rebuild. Remaining, for a later pass: the security scan reads the
PowerShell Recycle-Bin helper as `caution`, and `plugin_validate_private_imports` warns on
`hermes_cli.*`/`tools.skills_tool` imports even though the skills helpers are public now. Both are
warnings, not failures.
