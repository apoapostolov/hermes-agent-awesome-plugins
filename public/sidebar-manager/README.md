<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Sidebar Manager</h1>
  <strong>Hide and reorder the sidebar's core nav rows.</strong>
  <p>A statusbar chip opens a dialog: toggle each row on or off, and move it up or down.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.1-blue" alt="Version 1.0.1" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Sidebar Manager" />
</div>

## What You Can Do

- Open the manager from the statusbar chip, a list-ordered glyph on the right.
- Turn each core nav row on or off. Capabilities cannot be turned off: it hosts the Plugins tab, your only path to a plugin's own switch.
- Move a row up or down. The order you set is the order the sidebar renders.
- Your choices persist across reloads, in the plugin's own storage, which is cleared when you uninstall.

Rows covered: New session, Capabilities, Messaging, Artifacts, Cron jobs. Artifacts and Cron jobs only render in the Advanced interface mode, so they appear here regardless of your mode.

When more than one plugin contributes a preference, hidden rows are the union of every list and the first order to name a row places it.

## Not Covered

Session sections are not managed here. Pinned, Recents, messaging platform groups and Cron job sections stay as Hermes renders them, because the SDK's sidebar prefs area covers nav rows only and no sessions-section hook exists yet. See `LIMITATIONS.md`.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/sidebar-manager
```

Or install the whole pack:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Sidebar Manager** under **Capabilities → Plugins**, then toggle it off and on once so the desktop loader picks it up.

## Requirements / Limits

Desktop-only. No gateway or Python runtime required.

## License

[MIT](../../LICENSE)
