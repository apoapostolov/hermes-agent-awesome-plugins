# LIMITATIONS

**Drag to Pin Session** (`drag-to-pin-session`). This file records the blocker history and the current state. Both editions carry the same copy.

Catalog intake PR: [NousResearch/hermes-agent#115963](https://github.com/NousResearch/hermes-agent/pull/115963). Shared hook wishlist: [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).

## Resolved 2026-09-24: React fiber walk to pin and reorder

The plugin used to walk `__reactFiber$` on session rows to harvest
`onTogglePin` / `onReorderSessions` and call those props on drop. Fiber
internals are not a contract; rule 8 treats that as reaching into internal
stores.

The needed hook shipped: `host.sessions.pin/reorder` +
`SESSION_ROW_AREAS` ([#116305 item 3](https://github.com/NousResearch/hermes-agent/issues/116305),
merged 2026-09-24). Both editions now:

- publish the durable session id through a `SESSION_ROW_AREAS.leading`
  marker (read-only span; core keeps row ownership),
- pin with `host.sessions.pin(id, true, dropIndex)`, unpin with
  `host.sessions.pin(id, false)`,
- reset the manual order with `host.sessions.reorder([])` instead of the
  harvested `onReorderSessions`.

The fiber helpers are gone. Personal and public are byte-identical; there is
no longer an edition split for this plugin.
