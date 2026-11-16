# Queue Container Fix limits

This plugin has no catalog-listed edition, and the blocker is the whole plugin.

Catalog review rejects a plugin that restyles app-rendered DOM, because two plugins patching the same seam break each other and any desktop release can break both. Queue Container Fix is exactly that seam: one stylesheet that moves a row's columns.

What a `public/` cut would need is a supported seam to place the controls, and none exists:

- The queue row is built by `StatusRow` in the desktop app, from a grid whose fourth column is the trailing actions slot. The order is fixed by React, so only CSS can move the controls.
- The desktop SDK exposes slots and routes, not per-row composition inside the composer's status stack.
- There is no setting that reorders a status row's columns.

Until a seam exists, keep this personal: the pack pins `personal/queue-container-fix`, and the app renders exactly the markup this stylesheet expects.

The layout is filed upstream as https://github.com/NousResearch/hermes-agent/issues/156548, so the placement can move into the row itself rather than a stylesheet over it.

If upstream ever offers a row-composition hook, the plugin becomes a small SDK plugin and both trees can carry it.
