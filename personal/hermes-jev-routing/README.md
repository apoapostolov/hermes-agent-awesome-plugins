# Jev Routing

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Jev Routing" />
</div>

Per-turn model routing from TypeSafe Jev. Apostol Apostolov.

Type normally. Before the model starts, Jev reads the current message, a short history excerpt, the cwd, the live context size, and the spend snapshot, then answers four typed questions about it. Code composes those into a capability tier, applies your budget and availability policy, and the live session moves onto that model before the provider client is built. Jev judges the task; your policy owns the money.

Shadow is the default and switches nothing. Auto switches the live session. Off does nothing. An empty config_path leaves routing inert.

A missing key, a timeout, a bad payload, or an unreadable provider catalogue leaves the current model alone and the turn sends. The quota hold is the exception: when every eligible route, including the current model, is under its floor, the turn is not sent. A prompt that is empty, a slash command, an acknowledgement, or a short continuation in a live conversation does not re-route.

Codex quota is checked when a reading is fresh and has not reset. The stricter of the provider floor and the row floor wins, equality passes, and a missing, stale, or reset reading follows onUnknown. A real switch sets the session reasoning effort from the chosen row, and the destination credential is resolved before the client is rebuilt, so a cross-provider pick lands. A model the provider no longer serves loses the chain.

Every routed turn shows one dim subline under the prompt you just sent. A tier under confirm.tiers is held when onTimeout is reject, and the thin strip under that line is where a guarded pick is accepted.

Real cost lands in a ledger beside the routing file and feeds the budget caps. `/jev-routing suggest` previews a scores file, and `--write` saves a generated layer beside the hand table, where a chain the hand table already names still wins.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/hermes-jev-routing
```

Requires Hermes Agent 0.21.4 or newer. Set config_path to your hermes-jev-routing.json, then enable the plugin. The running gateway keeps the copy it started with until you Save and Reconnect.

Full configuration reference, settings, and command list: see [the public edition's README](../../public/hermes-jev-routing/README.md). Not in `hermes-pack.yaml`.

## License

[MIT](../../LICENSE)
