# memory-review-command

Desktop plugin: one native menu command for memory review.

Right-click empty app chrome (the shell menu that replaced the old native menu). The row is grayed out when memory is clean. When a staged write is waiting or a store is full, the label shows the pending count and one click sends `/memory pending` through the composer. It never approves or discards entries.

- Label examples: `Memory: review pending (2)`, `Memory: store full`, `Pending: 2 · user store full`
- Failed state read: disabled with a `state unknown` suffix
- State is read from a tiny backend route when the menu opens. A stale count is preferred over a hung menu.

## Install

Install the plugin pack (see the [repo README](../../README.md)) or copy this directory into your Hermes plugins folder and run:

```bash
hermes plugins enable memory-review-command --no-allow-tool-override
```

Turn it on under Capabilities → Plugins. Python routes mount on the next full desktop quit/reopen. The JS half hot-reloads.

## Files

- `plugin.yaml`: metadata
- `__init__.py`: no-op agent register
- `desktop/plugin.js`: context-menu row + composer send
- `dashboard/plugin_api.py`: `GET /state`

## How it works

A MutationObserver watches the shell context menu open. The Python half counts `pending/memory/*.json` and compares `memories/MEMORY.md` / `USER.md` against the configured char limits. Click injects `/memory pending` with `hermes:composer-insert` and submits it with `hermes:composer-submit`.
