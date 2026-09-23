<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Provider Quota Status</h1>
  <strong>See provider quota without leaving Hermes.</strong>
  <p>Status-bar used/remaining, multi-account pools, and rotation when a key runs low or hits its reset day.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.5.8-2ea44f" alt="Version 1.5.8" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Provider Quota Status" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" alt="Providers dialog with quota dots, extra keys, and key rotation" />
</div>

## What You Can Do

- Read used and remaining quota in the status bar for each enabled provider.
- Keep multiple accounts per provider, reorder them, and set a reset day per key.
- Rotate to the next healthy key when remaining quota hits your threshold or a renewal day passes.
- Start Grok and Codex OAuth from the setup dialog.

Supported providers: `tavily`, `opencode`, `deepseek`, `glm`, `openrouter`, `grok`, `codex`.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Provider Quota Status** under **Capabilities → Plugins**. Open the status-bar gear to configure providers. Never commit real keys.

## Requirements / Limits

Desktop-only. Quota numbers come from each provider's API. OAuth availability, reset behavior, and account limits follow the provider. This plugin manages configured credentials; it does not remove billing or usage caps.

## License

[MIT](../../LICENSE)
