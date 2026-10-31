"""Hermes plugin entry point: desktop automation tools backed by agent-desktop.

Eight tools over the Vercel Labs ``agent-desktop`` CLI. Semantic actions go
through the Windows accessibility tree, so a snapshot reads a real UI and a ref
action changes it without taking focus, moving the cursor or synthesizing
keystrokes.
"""

TOOLS = (
    ("desktop_status", "desktop", "desktop_status"),
    ("desktop_apps", "desktop", "desktop_apps"),
    ("desktop_snapshot", "desktop", "desktop_snapshot"),
    ("desktop_find", "desktop", "desktop_find"),
    ("desktop_act", "desktop", "desktop_act"),
    ("desktop_window", "desktop", "desktop_window"),
    ("desktop_clipboard", "desktop", "desktop_clipboard"),
    ("desktop_batch", "desktop", "desktop_batch"),
)


def register(ctx):
    from . import agentdesktop_schemas as schemas
    from . import agentdesktop_tools as tools

    for name, toolset, handler_name in TOOLS:
        ctx.register_tool(
            name=name,
            toolset=toolset,
            schema=schemas.ALL[name],
            handler=getattr(tools, handler_name),
        )
