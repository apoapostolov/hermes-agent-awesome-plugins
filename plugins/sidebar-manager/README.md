<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Sidebar Manager</h1>
  <strong>Hide and reorder the sidebar from a dim reorder glyph next to New session.</strong>
  <p>Click the list-ordered glyph after the Ctrl/N hint to enter edit mode. Click a nav row or session section to turn it off. Drag the grip to reorder with a live gap, the same HTML5 pattern used in Provider Status and RSS Reader.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Sidebar Manager" />
</div>

## What it does

- A dim list-ordered glyph sits after the New session keyboard hint. Click it to enter edit mode. Click it again, or press Escape, to leave. Row drag handles stay the gripper.
- In edit mode, every sidebar nav row after New session (Skills, Messaging, Artifacts, Cron, plugin pages) and every session section (Pinned, Recents, messaging platforms, Cron jobs) can be turned on or off. Off items stay on screen but dim. When you leave edit mode they hide.
- Each editable row gets a grip. Drag the grip, not the row body, so labels and header actions still work. While you drag, the list opens a gap where the row will land. A grab that never moved is not saved.
- New session stays first and cannot be hidden. Search results are left alone so a query cannot scramble your layout.
- Order and hidden ids persist in `localStorage` under `hermes.sidebar-manager.v1`.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/plugins/sidebar-manager
```

Enable **Sidebar Manager** under **Capabilities → Plugins**, then toggle it off and on once so the desktop loader picks it up.

## Compatibility

Desktop-only. No gateway or Python runtime is required. The plugin paints onto `data-tour="sidebar-nav-*"` rows and `[data-sessions-mode] [data-slot="sidebar-group"]` sections.

## Development and license

The implementation is in `desktop/plugin.js`. Metadata is in `plugin.yaml`. Licensed under [MIT](../../LICENSE).
