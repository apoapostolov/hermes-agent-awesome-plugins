<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Provider Quota Status</h1>
  <strong>See provider quota without leaving Hermes.</strong>
  <p>Status-bar used/remaining and user-managed provider pools. Polling is read-only for vendor credentials.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.5.9-2ea44f" alt="Version 1.5.9" /></a>
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
- Keep multiple accounts per provider and inspect their status.
- Use an access token that is already configured in the plugin. Expired OAuth tokens require a new login.
- Provider polling does not read vendor CLI auth files, refresh vendor tokens, write Hermes `.env` or `config.yaml`, or copy secrets into a plugin-owned `library.env`.
- See [DeepSeek's pricing window](https://api-docs.deepseek.com/quick_start/pricing) beside its name, including full-day Chinese public-holiday overrides. The plugin applies official 2025 and 2026 State Council holiday dates; the built-in calendar ends on 2026-12-31.
- The GLM chip shows its peak/off-peak speedometer even when the quota response omits a weekly window. Z.AI lists Coding Plan peak hours as Monday-Friday 14:00-18:00 Singapore time (UTC+8); off-peak use consumes half the standard credit rate. See [Z.AI Coding Plan usage](https://docs.z.ai/devpack/overview).

**Disclosure:** quota checks for Codex and Grok use the documented client identity and user-agent expected by their CLI-compatible endpoints. The public edition sends keys only to their own provider endpoints and does not collect telemetry.

Supported providers: Tavily, OpenCode Go, DeepSeek, GLM (z.ai), OpenRouter, Grok (xAI), Codex (OpenAI), OpenAI, Anthropic, Groq, Cerebras, Moonshot Kimi, MiniMax, Google Gemini, Hugging Face, Mistral, and Qwen.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Enable **Provider Quota Status** under **Capabilities → Plugins**. Open the status-bar gear to configure providers. Never commit real keys.

The public edition keeps quota chips, provider probes, device login, and plugin-owned configuration. It does not perform automatic key rotation into Hermes configuration. An expired OAuth token requires logging in again.

## Requirements / Limits

Desktop-only. Quota numbers come from each provider's API. OAuth availability, reset behavior, and account limits follow the provider. This plugin manages configured credentials; it does not remove billing or usage caps.

## License

[MIT](../../LICENSE)
