<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Opaque Composer</h1>
  <strong>Keep the message composer readable while you scroll.</strong>
  <p>Replace the translucent input surface with the active theme's card color so transcript text does not show through it.</p>
  [![Version](https://img.shields.io/badge/version-1.0.0-2ea44f)](plugin.yaml) [![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)
</div>

## What it does

- Applies an opaque theme-aware fill in normal and scrolled composer states.
- Uses Hermes' `data-slot="composer-root"` surface.
- Removes its namespaced stylesheet when disabled.
- Changes only the desktop composer; it does not alter conversations or gateway behavior.

## Install

Install the pack and enable **Opaque Composer** under **Capabilities → Plugins**:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows.

## Compatibility

Desktop-only. No gateway or Python runtime is required. The plugin depends on the composer root slot remaining available in Hermes Desktop.

## Development and license

The implementation is in `desktop/plugin.js`. Metadata is in `plugin.yaml`. Licensed under [MIT](../../LICENSE).
