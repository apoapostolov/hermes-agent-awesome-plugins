"""Drag to Pin Session — desktop UI plugin.

Agent-plugin register is a no-op. The UI half lives at the package root
as plugin.js (DR-capturable) and is mirrored to
desktop-plugins/drag-to-pin-session/plugin.js, which is the auto-on live
door.
"""


def register(ctx=None):
    return None
