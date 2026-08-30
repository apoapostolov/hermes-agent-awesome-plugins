"""Provider Status — dashboard + desktop plugin package.

Agent-plugin register is a no-op. The desktop UI is desktop/plugin.js and
the backend is dashboard/plugin_api.py (FastAPI router).
"""


def register(ctx=None):
    return None
