<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Session Pin Controls</h1>
  <strong>Pin or unpin sessions from their row.</strong>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.1.0-2ea44f" alt="Version 1.1.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>



## What You Can Do

- Use the row's **Pin** action to add it to Pinned.
- Use **Unpin** to move a pinned session back to Sessions.
- The app keeps ownership of row layout, selection, and ordering.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Session Pin Controls** under **Capabilities → Plugins**. Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows if needed.

## Requirements / Limits

Desktop-only. The public edition uses supported SDK actions and row slots. Pin drag-and-drop is unavailable until the Desktop SDK provides a drop-target hook.

## License

[MIT](../../LICENSE)
