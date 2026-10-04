# Jev Routing

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Jev Routing" />
</div>

Per-turn model routing for Hermes. Apostol Apostolov.

Jev reads the current user message and a short recent excerpt, then names a task kind and a capability tier. This edition can rewrite the model id when the pick stays on the provider already bound to the request. A pick on another provider is recorded and left alone.

Shadow is the default. Off does nothing. An empty config_path leaves routing inert.

The current user message and up to four thousand characters of recent user and assistant text go to TypeSafe on your key. A missing key, a timeout, or a bad answer leaves the turn on the model you already had.

A tier listed under confirm.tiers is not rewritten. A Codex quota floor is checked only when a reading is available. This edition does not fetch one, so an unknown reading admits the model.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/hermes-jev-routing
```

Requires Hermes Agent 0.21.4 or newer. The running gateway keeps the copy it started with until you Save and Reconnect.

## License

[MIT](../../LICENSE)
