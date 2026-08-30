# Provider Status

Unified multi-provider status bar for Hermes.

- Chips in the statusbar (`↑ used` / `↓ remaining`) per enabled provider, colored by quota.
- Gear → dialog to paste keys, reorder rows (drag gripper), set poll interval, pick reset-day per key.
- OAuth login for Grok (xAI) and Codex (OpenAI) inside the dialog — browser flow with local callback.
- Library env (`library.env`) collects every key ever pasted so rotations never lose a previous subscription.
- Rotation:
  - **Pool rotation** — when displayed remaining ≤ 2%, switches to next healthy key in pool.
  - **Reset-day rotation** — per-key renewal day; after it passes once/month, switches to that key.

## Providers

`tavily`, `opencode` (OpenCode Go), `deepseek`, `glm` (Z.AI), `openrouter`, `grok`, `codex`

## Files

- `plugin.yaml` — native plugin manifest
- `__init__.py` — agent-side no-op (desktop handles UI)
- `dashboard/plugin_api.py` — FastAPI backend (`/api/plugins/provider-status/*`)
- `dashboard/manifest.json` — dashboard tab wiring
- `desktop/plugin.js` — statusbar chips + setup dialog

## Config

`plugins/provider-status/config.json` (created on first run) + `library.env` (key library).
Copy `.example` files to start; never commit real keys.

## API

- `GET /status?provider=grok` — single provider status
- `GET /status/all` — all providers in parallel
- `POST /config` — save providers/poll/reset-days
- `POST /grok/browser/start`, `/grok/browser/poll`, `/codex/browser/*` — OAuth
