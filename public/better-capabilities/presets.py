"""The preset store — the one file the Desktop page reads and writes.

This module only persists JSON and validates preset names. Snapshotting and
applying capability state happen in the renderer through the Desktop plugin SDK
(``host.skills``, ``host.toolsets``, ``plugins.manage``), so nothing in the
public edition imports a Hermes core module to read or change that state.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,59}$")
KINDS = ("skills", "tools", "plugins")


def hermes_home() -> Path:
    """The active profile's Hermes home, resolved per call."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        env = os.environ.get("HERMES_HOME")
        if env:
            return Path(env)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            win = Path(local) / "hermes"
            if win.exists():
                return win
        return Path.home() / ".hermes"


def store_path() -> Path:
    return hermes_home() / "better-capabilities-presets.json"


def empty_store() -> dict[str, Any]:
    return {kind: {} for kind in KINDS}


def valid_name(name: Any) -> bool:
    return isinstance(name, str) and bool(PRESET_NAME_RE.match(name))


def load_store() -> dict[str, Any]:
    path = store_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_store()
    return clean_store(raw)


def clean_store(raw: Any) -> dict[str, Any]:
    """Coerce a posted store into the shape this file owns.

    Preset payloads are opaque (they are whatever the renderer snapshotted);
    only the outer buckets and the ``_order`` list are checked here, so a
    malformed POST cannot write something the page then chokes on.
    """
    store = empty_store()
    if not isinstance(raw, dict):
        return store
    for kind in KINDS:
        bucket = raw.get(kind)
        if not isinstance(bucket, dict):
            continue
        rows = {name: row for name, row in bucket.items() if name != "_order" and valid_name(name)}
        order = [name for name in bucket.get("_order", []) if isinstance(name, str) and name in rows]
        rows["_order"] = order
        store[kind] = rows
    return store


def save_store(store: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(clean_store(store), indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
