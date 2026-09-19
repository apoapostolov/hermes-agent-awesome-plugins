<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Compact Reasoning Label</h1>
  <strong>Model pill shows the model. Reasoning pill shows the level.</strong>
  <p>Strips the duplicated effort word from the composer model label.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Compact Reasoning Label" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" alt="Composer model pill showing Glm 5.3 Flash next to a Med reasoning pill" />
</div>

## What You Can Do

- Read a model name only in the model pill (for example "Grok 4.6" instead of "Grok 4.6 Medium").
- Leave the effort word on the reasoning pill beside it, which still changes the level when clicked.
- Cover standardized effort labels in short and full forms (Off, Min, Low, Med/Medium, High, XHigh/Extra High, Max, Ultra).
- Keep the label intact if stripping would leave nothing.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Or install just this plugin:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/plugins/compact-reasoning-label
```

Enable **Compact Reasoning Label** under **Capabilities → Plugins**. Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows if needed.

## Requirements / Limits

Desktop-only. No gateway or Python runtime required.

## License

[MIT](../../LICENSE)
