# Drag to Pin Session

Make the **Pinned** section of the Sessions sidebar a drag container.

- Drag a session row into **Pinned** → pins it
- Drag a pinned row out into **Sessions** → unpins it

No rebuild, no restart. The UI half hot-reloads.

## Install

```
Install the drag-to-pin-session plugin from
https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

After install, run **Cmd+K → Reload desktop plugins**. If it does not appear on
the first try, quit and reopen Hermes once — after that edits hot-reload.

## Doors

The pack installs the UI half at `plugins/drag-to-pin-session/desktop/plugin.js`.
That is the opt-in door (Settings → Plugins).

For auto-on, copy that same file to
`$HERMES_HOME/desktop-plugins/drag-to-pin-session/plugin.js`, which activates
without a Settings visit. Do not leave both live — two loaders, one id, double
registration.

## How it works

The session row already runs two gestures off one press: dnd-kit's PointerSensor
reorder, and the pane session-drag. This plugin adds a third on the same 6px
threshold rather than native HTML5 DnD, which collided with both.

- Dragging the row **body** pins/unpins. The grabber stays pure reorder, the
  kebab keeps its own gestures.
- The row's identity is read off React fiber props, then the row's **own
  `onPin`** is called. That resolves to `pinSession` in Sessions and
  `unpinSession` in Pinned, so the real store atom updates, the backend
  `pinned` flag PATCHes, and the state survives reloads and other windows.
  No localStorage poking the in-memory store would never see.
- dnd-kit also reacts to the drag. Its cross-list reorder is visually a no-op
  but flips the flat list into manual sort, so the plugin resets that after
  dnd-kit's own pointerup.
- The click that follows a real drag is suppressed, so it will not resume
  the chat.

## Caveats

This reads the Pinned section label and row component props from the compiled
app. If a future Hermes release renames that label or reshuffles the row props,
the plugin goes quiet instead of breaking. Re-verify after app updates.
