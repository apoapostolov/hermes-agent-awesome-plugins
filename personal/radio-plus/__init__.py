"""Radio Plus — a desktop radio player with an editable station list.

The player is renderer-only (``desktop/plugin.js``). This module exists because
the agent plugin loader owns the plugin directory, and ``dashboard/plugin_api.py``
is mounted as ``/api/plugins/radio-plus/`` for the one thing a renderer cannot
do alone: search the Shoutcast directory, which sends no CORS headers.

No tools, hooks, or middleware: the agent gets nothing from this plugin.
"""

from __future__ import annotations

from typing import Any


def register(ctx: Any) -> None:
    """Register nothing. The dashboard route is mounted by the web server."""
    return None
