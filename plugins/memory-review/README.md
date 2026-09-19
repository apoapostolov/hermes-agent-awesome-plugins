<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Memory Review</h1>
  <strong>Review staged memory writes before they land.</strong>
  <p>Checkbox the writes you want. Approve or reject from a dialog.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.2.1-2ea44f" alt="Version 1.2.1" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Memory Review" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" alt="Memory review dialog with generic staged writes, All selected, Reject and Approve" />
</div>

## What You Can Do

- Open pending memory from **Ctrl+K → Memory: pending** or by right-clicking empty app chrome.
- Select individual rows or use **All**.
- Approve or reject the selected staged writes in one decision.
- See store meters and a Consolidate action when a store is over budget. Approve skips dead replace/remove ops.

The plugin reviews pending writes. It does not silently approve them.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Memory Review** under **Capabilities → Plugins**. The JavaScript UI hot-reloads. Python dashboard routes mount after a full Hermes Desktop quit and reopen.

## Requirements / Limits

Desktop plugin with a small dashboard API. First install may need a full quit and reopen before Approve/Reject work.

## License

[MIT](../../LICENSE)
