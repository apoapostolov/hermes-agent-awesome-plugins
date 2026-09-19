<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Drag to Pin Session</h1>
  <strong>Arrange pinned sessions with the gesture you already use.</strong>
  <p>Drag a session into Pinned to place it, or drag it back to Sessions to unpin it.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.1.0-2ea44f" alt="Version 1.1.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Drag to Pin Session" />
</div>

## What it does

- **Pin by dragging.** Drag a session row into **Pinned** and drop at the visible slot.
- **Unpin the same way.** Drag a pinned row back into **Sessions**.
- **Keep the order.** The visual drop line follows the target position and the order survives reloads.
- **Protect existing gestures.** The grabber, kebab menu, and normal row click keep their own behavior.

## Install

Install the pack and enable **Drag to Pin Session** under **Capabilities → Plugins**:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows. The UI half hot-reloads after installation.

## How it works

The plugin uses the session row's own pin callbacks and a six-pixel pointer threshold. It coordinates with dnd-kit instead of adding a competing native HTML5 drag path, then suppresses the click that follows a real drag.

## Compatibility

Desktop-only. The plugin reads compiled session-row labels and props. After a Hermes update, verify that Pinned, row callbacks, and the drop surface still exist.

## License

[MIT](../../LICENSE).
