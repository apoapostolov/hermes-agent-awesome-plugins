# Limitations

The limits below are what the page does not do, and what an update needs. Both trees carry the same build: the page reads no app markup, so there is nothing to cut for the catalog edition.

## Navigation

The plugin adds its own route, sidebar row and palette entry. It does not touch the core Capabilities row, does not intercept clicks, and does not query app markup for navigation, so nothing here depends on the app's internal DOM. The native Capabilities page keeps its own table view; **Open in native Capabilities** in every panel is the hop between the two.

Every surface it uses is a public one, which is why the catalog edition is the same code.

## Enable state of desktop halves

`host.pluginDecisions` is deliberately read-only, so this page can read that a desktop half is on but cannot toggle another plugin's desktop half. The row switch and the panel both drive `plugins.manage toggle`, which is the agent half: for a unified package the app materializes the desktop half only while the agent half is enabled, so the switch covers both, and a desktop-only plugin still needs **Capabilities → Plugins** for its interface half. The switch flips the row first and flips it back if the backend refuses, so it never shows a state the backend does not hold. Desktop-only plugins that ship no Python half do not appear in the Installed list at all, because `plugins.manage list` reports packages, not app-level folders.

## Connectors

Configured MCP servers and the curated presets are both readable. Adding a preset needs its environment keys, and that form lives in the native page, so the panel offers **Add from native Capabilities** rather than half-building a server. Hosted connectors (accounts) are not shown: their state lives in the app's own store, not behind an SDK door.

## Catalog size

The plugin list is not virtualized. It filters, sorts by featured then stars, and renders 150 rows at a time with a **Show more** control. On a 2,380-entry catalog that is a deliberate trade against a virtualization dependency the plugin does not have. Search is client-side over the projected rows, including descriptions, categories, tool names and required keys.

The skills catalog is paged through the hub, and a search is debounced by 280ms. Both need the network; the installed views do not.

## Wording and identity

A short name is the normalized slug: lowercase, punctuation collapsed to hyphens, a leading `hermes-` dropped, clipped at 30 characters. Some entries already read as slugs, so the short name repeats the title in those rows. It is an identity column, not a second name, and the title is what changes when the catalog gets a human name.

## What an update needs

The desktop half does not reload in place. After installing or updating, restart Hermes Desktop. The dashboard route that serves the projected catalog mounts with the gateway, so a freshly installed Python half answers only after that restart.

## Switches on connectors

MCP has no JSON-RPC method for enabling or disabling a server, so the connector switch does not go through `host.request`. It posts to this plugin's own `POST /servers/toggle`, which performs the same guarded config write as the app's Connectors tab: it refuses a server that a plugin provides (409), reports an unknown name (404), and leaves a disabled server in the config so it can come back without being retyped. The change lands for the next session or gateway cycle, not in the running one.

## What the public edition drops

The connector switch. Enabling or disabling an MCP server needs the same guarded config write the app's Connectors tab performs, which lives behind `hermes_cli.web_routers._common.config_write_scope` and `save_config`; MCP itself has no JSON-RPC method for it, and the SDK exposes no door. The catalog tree therefore lists connectors with their state and leaves the switch to the native page, and its `plugin_api.py` carries three routes instead of four. Everything else, including the plugin, skill and toolset switches, is identical in both trees.

## Catalog sources

Both catalog filters read the published snapshots on `nousresearch.github.io/hermes-agent/docs/api`, the same two files the native Capabilities page reads. The skills snapshot is 66 MB of JSON; parsing it costs about five seconds the first time in a thirty-minute window and the gateway then holds the projected rows, which is roughly 100,000 rows of name, description, category, tags and install identifier. Nothing else from the snapshot is kept.

Paging is server-side, so search matches any row in the snapshot rather than only the rows already painted. The trade is that a page request needs the gateway; with the Python half missing, neither catalog paints and the page falls back to the installed list.

Archived skills are read from `skills/.archive` for the active profile. That folder is the whole record: a skill is archived by moving its directory, so a row shows the name, description, category and version its `SKILL.md` still carries, plus the fold's modification time. Restoring one is a move back that this page does not perform.
