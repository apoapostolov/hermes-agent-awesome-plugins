# busy-shortcuts

Adds compact commands for changing how Hermes handles input while it is busy:

- `/i` sets **interrupt** mode.
- `/q` sets **queue** mode, while `/q <prompt>` remains Hermes' built-in queue shortcut.
- `/s` sets **steer** mode.
- `/s <prompt>` sends the prompt through `/steer` immediately.

The mode controls what a normal message does while Hermes is working. The
selected mode is persisted in `display.busy_input_mode` when Hermes exposes its
configuration writer.

This plugin has a Python command half and a minimal desktop entry so it
appears in Hermes' desktop plugin toggle surface. It does not duplicate the
shortcut implementation in JavaScript and does not change Hermes core files.
