"""Load the plugin directory as an importable package for the tests.

The plugin directory is named ``vercel-agent-desktop-support``, which is not a legal
Python module name, so the tests register it under ``vercel_agent_desktop_support``
before importing anything from it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = "vercel_agent_desktop_support"

if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
