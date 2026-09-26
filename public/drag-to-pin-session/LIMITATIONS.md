# LIMITATIONS

**Drag to Pin Session** (`drag-to-pin-session`). This file records the catalog-safe edition's current feature boundary.

Catalog intake PR: [NousResearch/hermes-agent#115963](https://github.com/NousResearch/hermes-agent/pull/115963). Shared SDK hook wishlist: [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).

## Current catalog-safe behavior

The Desktop SDK now provides `host.sessions.pin()` and the `SESSION_ROW_AREAS` row slots. It does not provide a supported drag/drop target for the Pinned section. The public edition therefore exposes explicit Pin and Unpin actions in the trailing row slot. These use the durable `sessionId` supplied by the SDK and write through `host.sessions.pin()`.

The public edition does not inspect app-owned DOM, install global pointer or click listeners, simulate clicks, or depend on React internals or app storage. Dragging rows to pin or unpin them is unavailable in this edition until the SDK exposes a supported drop-target hook.
