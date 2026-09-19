"""Memory-Review: desktop UI plugin.

Agent-plugin register is a no-op. The UI half is desktop/plugin.js.
The backend is dashboard/plugin_api.py (FastAPI router).
"""


def register(ctx=None):
    return None
