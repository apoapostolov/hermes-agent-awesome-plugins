"""CDP Manager — desktop plugin package.

Agent-plugin register wires the `cdp` tool (cdp_manager/__init__ wires it via
schemas + cdp_tools). The desktop UI is desktop/plugin.js and the backend is
dashboard/plugin_api.py (FastAPI router) which the JS hits via ctx.rest.
"""

from . import schemas, cdp_tools


def register(ctx):
    """Register the `cdp` tool so the agent can manage local CDP servers."""
    ctx.register_tool(
        name="cdp",
        toolset="cdp-manager",
        schema=schemas.CDP,
        handler=cdp_tools.cdp,
        description=(
            "Manage the local Chrome DevTools Protocol (CDP) server without "
            "bash: status lists probed ports, launch starts Chrome with "
            "--remote-debugging-port, stop closes the listener, recheck "
            "re-probes. Prefers the port marked preferred in the plugin "
            "config; port overrides the choice."
        ),
        emoji="\U0001f50c",
        is_async=False,
    )
