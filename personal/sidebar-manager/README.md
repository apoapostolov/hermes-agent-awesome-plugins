<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Sidebar Manager</h1>
  <strong>Hide and reorder sidebar nav and session sections.</strong>
  <p>Edit mode from a dim glyph next to New session. Drag grips to reorder; click rows to hide.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Sidebar Manager" />
</div>

## What You Can Do

- Enter edit mode from the dim list-ordered glyph next to New session. Escape or click again to leave.
- Turn nav rows after New session (Skills, Messaging, Artifacts, Cron, plugin pages) and session sections (Pinned, Recents, messaging platforms, Cron jobs) on or off. Off items dim in edit mode and hide when you leave.
- Drag the grip to reorder with a live gap. A grab that never moved is not saved.
- New session stays first and cannot be hidden. Search results are left alone so a query cannot scramble your layout.
- Order and hidden choices persist across reloads.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Or install just this plugin:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/sidebar-manager
```

Enable **Sidebar Manager** under **Capabilities → Plugins**, then toggle it off and on once so the desktop loader picks it up.

## Requirements / Limits

Desktop-only. No gateway or Python runtime required.

## License

[MIT](../../LICENSE)
