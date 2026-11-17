"""Hermes plugin entry point for byparr-tools.

Install into ~/.hermes/plugins/byparr-tools (or `hermes plugins install`), then
`hermes plugins enable byparr-tools`. Registers three read-only tools over the
Bedroom Byparr solver. No hooks, no middleware, no extra dependencies.
"""


def register(ctx):
    from .byparr_tools import schemas, tools

    for name, schema, handler in (
        ("solver_get", schemas.SOLVER_GET, tools.solver_get),
        ("solver_cookies", schemas.SOLVER_COOKIES, tools.solver_cookies),
        ("solver_load", schemas.SOLVER_LOAD, tools.solver_load),
    ):
        ctx.register_tool(
            name=name,
            toolset="byparr",
            schema=schema,
            handler=handler,
        )
