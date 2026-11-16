"""Catalog Redesign — Python half.

Desktop-only plugin: the renderer in ``desktop/plugin.js`` owns the whole
surface (a Catalog page, its sidebar row and the detail panel). This module
registers nothing; it exists so the package loads as a normal plugin and so the
catalog proxy in ``dashboard/plugin_api.py`` has a package behind it.
"""

from __future__ import annotations

from typing import Any


def register(ctx: Any = None):
    """No agent-side surfaces: the page lives in the renderer."""
    return None
