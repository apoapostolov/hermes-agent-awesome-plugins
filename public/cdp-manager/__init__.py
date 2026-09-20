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
            "Manage local Chrome DevTools Protocol (CDP) servers without "
            "bash: status (probes plus health, modes, selections), profiles "
            "(launchable profiles with locked/served state), launch, restart "
            "(the way to switch mode or profile), stop, recheck, prefer "
            "(marks the managed port a backend supervisor keeps up). Uses "
            "the managed port when none is given; port overrides."
        ),
        emoji="\U0001f50c",
        is_async=False,
    )
