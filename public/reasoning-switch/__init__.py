"""reasoning-switch: desktop UI plugin, no Python backend.

The statusbar chip talks to the gateway JSON-RPC directly via
``host.request('config.get'/'config.set', {key: 'reasoning', ...})``.
"""


def register(ctx):
    """No-op: all behavior lives in desktop/plugin.js."""
