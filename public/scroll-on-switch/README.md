<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Scroll on Switch</h1>
  <strong>Land on the newest message when you switch sessions.</strong>
  <p>Snaps to the bottom on switch. Does not fight streaming or manual scroll during a turn.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.4.5-2ea44f" alt="Version 1.4.5" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Scroll on Switch" />
</div>

## What You Can Do

- Snap newly opened sessions to the bottom of the transcript.
- Snap keep-alive sessions to the bottom when they become visible again.
- Leave streaming and new messages alone so you can scroll while a turn runs.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Scroll on Switch** under **Capabilities → Plugins**. Reload desktop plugins from **Cmd+K** or **Ctrl+K** on Windows if needed.

## Requirements / Limits

Desktop-only. Depends on the transcript scroll surface Hermes Desktop exposes.

## License

[MIT](../../LICENSE)
