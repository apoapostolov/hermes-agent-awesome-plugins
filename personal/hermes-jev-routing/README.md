# Jev Routing

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Jev Routing" />
</div>

Per-turn model routing for Hermes. Apostol Apostolov.

Jev reads the current user message and a short recent excerpt, then names a task kind and a capability tier. Code walks your chains for that tier and picks the first configured model. Auto mode switches the live session onto that model before the client sends. A tier listed under confirm.tiers is recorded and left alone, because this build has no approval dialog.

Shadow is the default. It decides and does not switch. Off does nothing. An empty config_path leaves routing inert.

The current user message and up to four thousand characters of recent user and assistant text go to TypeSafe on your key. A missing key, a timeout, or a bad answer leaves the turn on the model you already had.

Quota floors are checked when a Codex reading is fresh and has not reset. A missing, stale, or reset reading follows onUnknown, which admits the model unless it says skip. A successful switch sets the session reasoning effort from the chosen row. A tier listed under confirm.tiers is held when onTimeout is reject. There is still no approval prompt, so that tier cannot be accepted from the turn.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/hermes-jev-routing
```

Requires Hermes Agent 0.21.4 or newer. Set config_path to your hermes-jev-routing.json, then enable the plugin. The running gateway keeps the copy it started with until you Save and Reconnect.

## License

[MIT](../../LICENSE)
