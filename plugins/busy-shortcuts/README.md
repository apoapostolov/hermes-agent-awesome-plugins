# busy-shortcuts

Adds compact commands for changing how Hermes handles input while it is busy:

- `/i` sets **interrupt** mode.
- `/q <prompt>` remains Hermes' built-in queue shortcut.
- `/s` sets **steer** mode.
- `/s <prompt>` sends the prompt through `/steer` immediately.

The mode controls what a normal message does while Hermes is working. The
selected mode is persisted in `display.busy_input_mode` when Hermes exposes its
configuration writer.

This plugin has no desktop UI and does not change Hermes core files.
