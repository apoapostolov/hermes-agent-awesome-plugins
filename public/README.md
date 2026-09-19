# Public editions

Listed editions. Not every personal plugin has a public copy yet.

These builds stay inside the Hermes plugin SDK (`ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`) so they can be submitted to the [Hermes Plugin Catalog](https://github.com/NousResearch/hermes-agent/tree/main/plugin-catalog). Where the desktop app has no hook yet, the public edition drops that surface rather than reaching into the app.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/<id>
```

Replace `<id>` with the plugin folder name.

Full-featured, install-at-your-own-risk builds live in [`../personal`](../personal).

Each public plugin that diverged from personal (or is held because of it) has `LIMITATIONS.md`. Read that file before migrating a personal feature back into the listed edition.

## Listing status

| Plugin | Public edition |
| --- | --- |
| memory-review | Path-id gate. No shell-menu inject. No hidden composer submit. Palette + dialog stay. |
| intelligent-tool-break | Hooks + slash commands stay. No Popen patch, no private CLI rebind, no process SIGKILL, no composer insert. |
| better-capabilities | Not in public. The product is Capabilities-page reach-in (row buttons, app-store writes, raw bridge). Kept in personal until a catalog hook exists. |
| provider-status | Quota chips, probes, plugin-owned config. No vendor CLI auth files, no token refresh on poll, no automatic Hermes `.env` / `config.yaml` writes, no `library.env` copy. |
| sidebar-manager | Snapshot. Held until `host.sidebar` exists. |
| drag-to-pin-session | Snapshot. Held until `host.sessions.pin` / `reorder`. |
| better-session-appearance | Snapshot. Held until session-row slot / `setColor`. |
| Other plugins | Identical to personal at the split. Review before a catalog pin. |
