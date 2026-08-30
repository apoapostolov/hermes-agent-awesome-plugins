# better-colors

Desktop plugin for **session list appearance**: titles take the Appearance color, optional per-session bold, extra colors in the picker, and a Codicon idle-bullet.

- Session title uses the Appearance color. Lightness flips for light vs dark so one hue stays readable in both modes.
- **Bold Session** is per chat, stored with that session's color.
- Appearance submenu: Custom sits beside No color (half width each). Full Codicon set with an underline search. Chosen glyph replaces the **idle** bullet only. Working (orange) and finished-unread (green) status dots stay Hermes's.

## Files

- `plugin.yaml` — metadata
- `__init__.py` — no-op agent register
- `desktop/plugin.js` — overlay on the session list + Appearance picker

## How it works

A MutationObserver restyles sidebar rows from the idle-dot color (`hermes.desktop.sessionColors`) and injects extra controls into `ColorSwatches`. Extra colors go through the picker's own `onChange`. Glyphs and bold live in plugin storage, keyed by session id.

Drop `desktop/plugin.js` in `$HERMES_HOME/desktop-plugins/better-colors/` for auto-on, or keep it under `plugins/better-colors/desktop/` and enable it in Settings → Plugins.
