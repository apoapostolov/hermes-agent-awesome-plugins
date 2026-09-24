# LIMITATIONS

Public edition of **Better Session Appearance** (`better-session-appearance`). This file records where the listed edition stops short of the personal edition and why. Both editions carry the same copy.

Catalog intake PR: [NousResearch/hermes-agent#115961](https://github.com/NousResearch/hermes-agent/pull/115961). Shared hook wishlist: [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).

## Edition split (post-migration 2026-09-24)

The SDK hooks this plugin was held on shipped: `host.sessions.setColor` +
`SESSION_ROW_AREAS` (item 3) and `APPEARANCE_AREAS.extra` + `ColorSwatches`
(item 7), both merged 2026-09-24. The public edition now uses them:

- Per-session **color** goes through `host.sessions.setColor(sid, hex | null)`,
  picked from the app's own `ColorSwatches` grid (plus a custom picker) inside
  a per-row popover. No writes to `hermes.desktop.sessionColors`, no fiber
  walks, no harvested `onChange`.
- Per-session **idle glyph** renders through a `SESSION_ROW_AREAS.leading`
  contribution with the slot's durable `sessionId`. Plugin state (colors,
  glyphs) lives in `ctx.storage`.

**The two editions differ in implementation:**

- **Personal** keeps the original DOM implementation: full-name repaint with
  lightness adaptation, bold titles (marquee-state removal included), auto
  rules matched on title text, presets, and the injected Appearance-submenu
  panel with the full 300-glyph gallery. Title restyling and menu injection
  are app-DOM reach-ins; the SDK has no hook that repaints the row title.
- **Public** covers color and glyph only, entirely through SDK row slots.
  It does not repaint the session title, does not bold, and has no auto
  rules or Appearance-submenu extras.

## If further hooks land

A row-title decoration area or an Appearance-menu slot could let the public
edition converge with personal. Track
[#116305](https://github.com/NousResearch/hermes-agent/issues/116305).
