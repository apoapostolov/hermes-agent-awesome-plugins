# Scroll on Switch

Keep the active Hermes Desktop transcript at the newest message when a session becomes active or receives a new message.

## What it does

- Scrolls newly mounted sessions to the bottom.
- Scrolls keep-alive sessions to the bottom when they become visible.
- Follows inserted user and assistant message nodes, including the final response after a request finishes.
- Stops forcing the viewport after the update settles, so manual scrolling still works.

Desktop-only. The plugin hot-reloads in Hermes Desktop.

## Install

Install the `hermes-agent-awesome-plugins` pack, or install this subdirectory from the repository with Hermes Agent's plugin installer.