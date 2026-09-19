"""Better Capabilities — dashboard + desktop plugin package.

Registers /preset so chat can save or apply Skills and Plugins presets.
The desktop UI is desktop/plugin.js. Recycle/zip/preset routes live in
dashboard/plugin_api.py.
"""

from __future__ import annotations

from typing import Any


def _handle_preset(raw_args: str) -> str:
    from pathlib import Path
    import importlib.util

    path = Path(__file__).resolve().parent / "presets.py"
    spec = importlib.util.spec_from_file_location("better_capabilities_presets", path)
    if spec is None or spec.loader is None:
        return "Could not load preset commands."
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.handle_preset_command(raw_args)


def register(ctx: Any = None):
    if ctx is None:
        return None
    ctx.register_command(
        "preset",
        handler=_handle_preset,
        description="Save or apply a Skills or Plugins on/off preset.",
        args_hint="save skills|plugins <name> | skills|plugins <name>",
        argument_mode="text",
    )
    return None
