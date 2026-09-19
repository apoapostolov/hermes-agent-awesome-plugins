<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Drag to Pin Session</h1>
  <strong>Pin and unpin sessions by dragging.</strong>
  <p>Drop into Pinned or back into Sessions. Order lasts across reloads.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.1.0-2ea44f" alt="Version 1.1.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Drag to Pin Session" />
</div>

## What You Can Do

- Drag a session into **Pinned** and drop it at the visible slot.
- Drag a pinned row back into **Sessions** to unpin.
- Keep that order after reloads.
- Grabber, kebab menu, and normal row click keep their own behavior.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Drag to Pin Session** under **Capabilities → Plugins**. Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows if needed.

## Requirements / Limits

Desktop-only. After a Hermes update, confirm Pinned, row callbacks, and the drop surface still exist.

## License

[MIT](../../LICENSE)
