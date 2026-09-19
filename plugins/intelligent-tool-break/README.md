<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Intelligent Tool Break</h1>
  <strong>Recover a stuck tool call without losing the turn.</strong>
  <p>Stop an in-flight spawn, send a correction, or retry the last action from Hermes Desktop.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.3.3-2ea44f" alt="Version 1.3.3" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Intelligent Tool Break" />
</div>

## What it does

- **Break the newest task.** `/break` stops the newest in-flight spawn tree and keeps the turn alive.
- **Send a correction.** `/break {message}` stops the call and gives the model your hint.
- **Retry deliberately.** `/again` repeats the exact call; `/again {hint}` repeats it with a correction.
- **See what can stop.** `/break-status` exposes the current killable list.
- **Use the desktop strip.** Break, Message, Again, elapsed time, and per-tool controls appear beside active work.

Previously published as `hermes-break`. The commands remain compatible.

## Install

Install the pack and enable **Intelligent Tool Break** under **Capabilities → Plugins**:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Use the shortcut `mod+shift+b` or the controls in the composer strip.

## How it works

The agent side tracks `terminal` and `process` spawns through a Popen hook and descendant sweep. Break and retry terminate the tree with the platform's process controls, then rewrite the tool result so Hermes can continue.

## Files and development

- `__init__.py`: spawn tracking, tree control, and slash commands
- `desktop/plugin.js`: composer strip, palette, and keybind
- `plugin.yaml`: hooks and command registration
- `tests_break.py`: helper checks

## Limits

The plugin depends on Hermes' active spawn and composer surfaces. If a future Hermes release changes those contracts, controls may become unavailable until compatibility is updated.

## License

[MIT](../../LICENSE).
