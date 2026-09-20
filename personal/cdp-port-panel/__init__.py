"""cdp-port-panel: desktop UI plugin, no Python backend.

The statusbar gear opens a dialog that probes 127.0.0.1 CDP ports against
``/json/version`` from the renderer. Read-only: nothing is launched or killed.
"""


def register(ctx):
    """No-op: all behavior lives in desktop/plugin.js."""
