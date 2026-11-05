"""Runtime settings for the desktop tools.

Hermes reads these from the plugin's ``config_schema`` at register time, so a
tool never has to reach into config.yaml or the environment itself.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULTS: Dict[str, Any] = {
    "bin_path": "",
    "install_dir": "",
    "version": "1.2.0",
    "auto_install": False,
}

_settings: Dict[str, Any] = dict(DEFAULTS)


def update(values: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge values read from the host config, ignoring empty strings."""
    for key, value in (values or {}).items():
        if key not in DEFAULTS:
            continue
        if value is None or value == "":
            continue
        _settings[key] = value
    return dict(_settings)


def get(key: str, default: Any = None) -> Any:
    return _settings.get(key, DEFAULTS.get(key, default))


def as_bool(key: str) -> bool:
    value = _settings.get(key, DEFAULTS.get(key))
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def snapshot() -> Dict[str, Any]:
    return dict(_settings)
