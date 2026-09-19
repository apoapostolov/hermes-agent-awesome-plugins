"""Iteration Budget Meter — desktop statusbar plugin.

The desktop UI lives in desktop/plugin.js. There is no Python backend: the
plugin reads the app's own renderer state (host.state.busy for the running
turn, host.state.focusedUsage.calls for the live iteration count) and needs no
dashboard routes.
"""


def register(ctx=None):
    return None