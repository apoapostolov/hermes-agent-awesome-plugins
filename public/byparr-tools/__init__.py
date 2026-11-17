"""Hermes plugin entry point for byparr-tools.

Registers nine read-only solver tools. Every machine-specific value is read
from plugin Settings or an environment variable, so the same tree works on any
host after the documented solver and browser setup.
"""


def register(ctx):
    from .byparr_tools import fallback, schemas, tools

    tools.configure(ctx)
    fallback.configure(ctx)
    ctx.register_middleware("tool_execution", fallback.on_tool_execution)
    handlers = {
        "solver_get": tools.solver_get,
        "solver_cookies": tools.solver_cookies,
        "solver_load": tools.solver_load,
        "solver_status": tools.solver_status,
        "solver_bridge": tools.solver_bridge,
        "solver_extract": tools.solver_extract,
        "solver_fetch": tools.solver_fetch,
        "jar_list": tools.jar_list,
        "jar_clear": tools.jar_clear,
    }
    for name, schema in schemas.TOOLS:
        ctx.register_tool(
            name=name,
            toolset="byparr",
            schema=schema,
            handler=handlers[name],
        )
