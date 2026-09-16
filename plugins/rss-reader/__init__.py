"""RSS Reader: desktop UI plugin.

The UI half is desktop/plugin.js and keeps its library in IndexedDB. The
agent-plugin register is a no-op, so the loader needs a ctx-tolerant signature.
"""


def register(ctx=None):
    return None
