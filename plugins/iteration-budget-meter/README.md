<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Iteration Budget Meter</h1>
  <strong>See how hard the focused session is pushing.</strong>
  <p>Watch per-turn tool-call usage live and inspect the session's longer-term budget pattern from the status bar.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.2.1-2ea44f" alt="Version 1.2.1" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Iteration Budget Meter" />
</div>

## What it does

- **Watch the current turn.** See tool-call usage against the session's iteration budget while work runs.
- **Inspect the details.** Hover for request stats and click for averages, ceiling-hit ratio, and a data-based ceiling suggestion.
- **Keep turns separate.** The counter resets for each turn, avoiding the cumulative-counter leak fixed in v1.1.0.

## Install

Install the pack and enable **Iteration Budget Meter** under **Capabilities → Plugins**:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

The meter appears in the desktop status bar when a turn is active.

## Compatibility and development

Desktop-only. The implementation is in `desktop/plugin.js` and follows the focused session's tool-call and turn signals. Budget ceilings remain controlled by Hermes and the connected model configuration.

## License

[MIT](../../LICENSE).
