<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Better Session Appearance</h1>
  <strong>Make session names easier to scan.</strong>
  <p>Give each session its own color and idle icon in the session list.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.2.2-2ea44f" alt="Version 1.2.2" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Better Session Appearance" />
</div>

## What You Can Do

- Give a session a color from the Appearance picker. It shows on that row’s dot.
- Pick an idle icon from the Codicon set (search included). Working and finished-unread status dots stay Hermes’s.
- Clear a color or icon to hand the row back to Hermes.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Better Session Appearance** under **Capabilities → Plugins**.

## Requirements / Limits

Desktop-only. The color and icon apply to idle session rows; Hermes keeps ownership of working and unread status dots. Bold session titles and Auto Rules are not part of this edition, since the SDK has no session-title area to decorate. See `LIMITATIONS.md`.

## License

[MIT](../../LICENSE)
