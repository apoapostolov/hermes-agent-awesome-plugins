# Jev Routing

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Jev Routing" />
</div>

Per-turn model routing from TypeSafe Jev. Apostol Apostolov.

Type normally. Before the model starts, Jev reads the current message, a short history excerpt, an estimated context size, and the spend snapshot, then answers four typed questions about it. Code composes those into a capability tier, applies your budget policy, and the request that is about to go out is rewritten onto that model. The provider client is already bound to the turn, so the rewrite stays on the same provider.

Shadow is the default and changes nothing. Auto rewrites the request, and when the Desktop is attached it also moves the session onto the same model through the app's own model switch. Off does nothing. An empty config_path leaves routing inert.

A missing key, a timeout, or a bad payload leaves the current model alone and the turn sends. A prompt that is empty, a slash command, an acknowledgement, or a short continuation in a live conversation does not re-route.

A pick on a different provider cannot be sent from a plugin: middleware rewrites the request it is given, it cannot open another client. That pick is printed in the line and recorded as `blocked: cross-provider`, and the approve row can still move the session because that goes through the app's own model switch.

This edition reads no provider catalogue and no quota window, so a configured row stays eligible and a missing Codex reading admits the model. A tier under confirm.tiers offers the approve row; the turn that triggered it still answers on its current model. `/jev-routing suggest` previews a scores file, and `--write` saves a generated layer that a chain this file already names still overrides.

`LIMITATIONS.md` lists every behavior only the personal edition has, and the core hook each one needs.

## Install

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/hermes-jev-routing
```

Requires Hermes Agent 0.21.4 or newer, plus a TypeSafe API key with access to `jev-latest`, declared as `TYPESAFE_API_KEY` at install. The running gateway keeps the copy it started with until you Save and Reconnect.

## The routing table

```json
{
  "enabled": true,
  "confidenceThreshold": 0.34,
  "minPromptChars": 12,
  "routes": {
    "quick":    [{ "provider": "opencode-go", "model": "beam-free", "thinkingLevel": "medium" }],
    "standard": [{ "provider": "opencode-go", "model": "longcat-2.5-preview-free", "thinkingLevel": "medium" }],
    "high":     [{ "provider": "openai-codex", "model": "gpt-6-sol", "thinkingLevel": "medium" }],
    "premium":  [{ "provider": "openai-codex", "model": "gpt-6-sol", "thinkingLevel": "medium" }],
    "xpremium": []
  },
  "kindMinimumTier": { "plan": "high", "review": "high", "implement": "standard" },
  "kindModels": {
    "implement": [{ "provider": "openai-codex", "model": "gpt-6-sol", "minTier": "standard", "priority": 20 }]
  },
  "confirm": { "tiers": ["premium", "xpremium"], "onTimeout": "reject" },
  "quota": {
    "openai-codex": {
      "minQuota": { "fiveHour": 0.05, "weekly": 0.05 },
      "onUnknown": "use",
      "cacheTtlSec": 120
    }
  },
  "budget": { "dailyUsd": 10, "monthlyUsd": 150, "softRatio": 0.7, "hardRatio": 0.9 },
  "cache": { "aware": true, "deadband": 0.25, "maxPenaltyUsd": 0.05, "bypassTierDelta": 2 },
  "pricing": {
    "opencode-go/glm-5.3-flash": { "input": 0.15, "output": 0.5, "cache_read": 0.03 },
    "opencode-go/glm-5.3": { "input": 1.4, "output": 4.4, "cache_read": 0.26 }
  },
  "free": {
    "enabled": true,
    "policy": "fallback-only",
    "pool": [{ "provider": "opencode-go", "model": "beam-free", "thinkingLevel": "medium" }]
  },
  "ranking": {
    "scoresFile": "",
    "cutoffs": { "standard": 0.5, "high": 0.7, "premium": 0.85 },
    "spreadProviders": true
  }
}
```

A tier the file leaves empty stays empty, and the loader never invents a model list. `xpremium` only fires when the demand already rounds to premium and the kind confidence clears the threshold, so an empty chain disables the tier.

## Enable it

```yaml
# config.yaml
plugins:
  entries:
    hermes-jev-routing:
      settings:
        mode: auto
        config_path: C:/Users/you/AppData/Local/hermes/hermes-jev-routing.json
```

## Settings that override the table

Every scalar policy knob is also a plugin setting, and a setting you actually set replaces the file value. An unset setting leaves your tuned file alone, so a form default never overwrites your table.

`mode`, `enabled`, `confidence_threshold`, `min_prompt_chars`, `timeout_ms`, `history_turns`, `stickiness`, `confirm_on_timeout`, `confirm_tiers`, `quota_on_unknown`, `quota_enabled`, `cache_aware`, `free_enabled`, `free_policy`.

The chains, the model rows, and the scores stay in the JSON file. A route table is not a form field.

## What you see

One dim subline under the composer, for the turn that was just routed, before the model works:

```
tier quick · opencode-go/beam-free · thinking medium · kind chat · complexity 0.20/3 · capability 0.20/3 · reasoning 0.00/1
```

The glyph leads it: `>` applied to the request, `=` kept the active model through stickiness, `.` notify only, `x` offered but not applied. When a guarded tier wants a different model, a thin row appears under that line offering **Yes**, No, Free, and each tier name. Yes moves the session through the app's own model switch and sets the reasoning level; the turn that raised the row still answers on the model it started with, because a plugin cannot stop a send.

The line sits in the composer's underside strip, the contribution area the app provides for this. It is not attached to the message you already sent, so scrolling back to an older turn does not show the line that turn carried.

## Commands

| Command | What it does |
| --- | --- |
| `/jev-routing` | Mode, spend, every chain, and the last decision |
| `/jev-routing why` | Re-ask Jev about the last prompt and show the full judgment |
| `/jev-routing route <text>` | Classify any text and name a tier without switching |
| `/jev-routing revert` | Pin the model that was active before the last pick onto the next request from that provider |
| `/jev-routing budget daily\|monthly <usd>` | Session-only cap, no file write |
| `/jev-routing suggest [--write]` | Rank a scores file into proposed chains; your hand table still wins |
| `/jev-routing on` / `off` / `mode <name>` | Enable, disable, or set the mode for this session |
| `jev_route` tool | Let the model ask which tier a subtask deserves |

## The spend ledger

Every provider response records its usage into `<config-stem>-state.json` beside the routing file, split by day and month. Money comes from a reported total when the provider sends one, otherwise from the `pricing` block you wrote into the routing JSON. An unpriced model records tokens but no dollars rather than inventing spend, so its rows leave budget pressure at zero. That is what feeds budget pressure.

## License

[MIT](../../LICENSE)
