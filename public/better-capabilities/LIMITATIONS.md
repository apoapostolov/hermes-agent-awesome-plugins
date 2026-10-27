# LIMITATIONS

Public edition of **Better Capabilities** (`better-capabilities`), the catalog build. It keeps only
what the plugin SDK and this plugin's own routes can do, so it can be listed.

## What this edition does not have

### 1. The `/preset` chat command

- **Personal edition:** `/preset save skills|tools|plugins <name>` and
  `/preset skills|tools|plugins <name>` snapshot and apply capability state from Python.
- **Why not here:** reading a profile's enabled skills, toolsets or agent plugins from Python means
  importing `hermes_cli.skills_config`, `hermes_cli.tools_config`, `hermes_cli.plugins*`,
  `hermes_cli.profiles` and the profile-scope helpers — eight core modules with no public plugin
  surface. `hermes plugins validate` reports each as a rule 9 warning, and the submission guide
  treats rule 9 problems as declines. The renderer already does the same work through
  `host.skills`, `host.toolsets` and the `plugins.manage` RPC, so this edition keeps the page and
  drops the command.
- **What still works:** everything on the Presets page — save, apply, overwrite, rename, reorder,
  delete, per profile.

### 2. The sidebar row glyphs

- **Personal edition:** two dim glyphs on the Capabilities nav row open this profile's Skills
  editor and a profile picker.
- **Why not here:** the sidebar has no per-row SDK hook (`sidebar.nav` only adds rows;
  `sidebar.nav.prefs` only hides or reorders them), so that feature injects into app markup. It
  fails the catalog's `desktop surface` check and is excluded from this build.
- **What still works:** the gear on the plugin's row in Capabilities → Plugins, and the Settings
  rail.

### 3. Cross-profile file actions (both editions)

When the page is pinned to a profile other than the window's, Delete, Package, Open folder and the
file list are hidden. Those routes run in this plugin's own backend, which is scoped to the
requesting profile by construction — it cannot act on another profile's skills tree. Switches
(enable/disable) do apply to the pinned profile.

## Scope

- File actions reach only skills under `<hermes home>/skills`. Bundled and hub skills resolve
  elsewhere and are refused.
- A zip export never follows a symlink, and never leaves the skill folder.
- Preset state lives in `<hermes home>/better-capabilities-presets.json`.

## Disclosure

No network calls, no telemetry, no credential access. The plugin reads markdown inside a skill
folder, writes and deletes skill folders (Recycle Bin preferred, a moved-aside folder as fallback),
and on Windows runs `powershell.exe` once per delete for the Recycle Bin call.
