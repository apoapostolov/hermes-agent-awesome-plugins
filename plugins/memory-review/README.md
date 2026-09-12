# Memory-Review

Desktop plugin: a Hermes-style dialog for staged memory writes.

Ctrl+K **Memory: pending**, or right-click empty app chrome. Check the writes you want, use **All**, then **Approve** or **Reject**.

## Install

Install the plugin pack (see the [repo README](../../README.md)) or copy this directory into your Hermes plugins folder and run:

```bash
hermes plugins enable memory-review --no-allow-tool-override
```

Turn it on under Capabilities → Plugins. Python routes mount on the next full desktop quit/reopen. The JS half hot-reloads.

## Files

- `plugin.yaml`: metadata
- `__init__.py`: no-op agent register
- `desktop/plugin.js`: palette, shell menu, review dialog
- `dashboard/plugin_api.py`: `GET /state`, `POST /decide`
