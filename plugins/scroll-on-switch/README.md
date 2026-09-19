<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Scroll on Switch</h1>
  <strong>Start each selected session at its newest message.</strong>
  <p>Keep session switching predictable without interrupting manual scrolling or live work.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.4.5-2ea44f" alt="Version 1.4.5" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

## What it does

- Scrolls newly mounted sessions to the bottom.
- Scrolls keep-alive sessions to the bottom when they become visible again.
- Ignores new messages and AI streaming, so it does not fight manual scrolling during a turn.

## Install

Install the pack and enable **Scroll on Switch** under **Capabilities → Plugins**:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows.

## Compatibility and development

Desktop-only. The implementation is in `desktop/plugin.js` and hot-reloads in Hermes Desktop. It depends on the transcript scroll surface exposed by the desktop app.

## License

[MIT](../../LICENSE).
