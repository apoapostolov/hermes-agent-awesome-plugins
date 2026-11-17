"""Portable settings for byparr-tools.

No machine-specific default lives in this module. The fallback solver address is
the standard local solver port; every deployment overrides it through the
plugin's Settings page, the FLARESOLVERR_URL variable, or both.
"""
from __future__ import annotations

import os
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "solver_url": "http://127.0.0.1:8191",
    "default_timeout_seconds": 60,
    "block_media": True,
    "auto_fallback": True,
    "return_html_default": False,
    "max_html_chars": 6000,
    "max_text_chars": 3000,
    "cdp_url": "http://127.0.0.1:9222",
    "request_spacing_seconds": 0.2,
    "max_retries": 2,
    "cookie_jar_ttl_seconds": 1800,
    "persist_cookie_jar": False,
    "cookie_jar_dir": "",
}

# Sensitive proxy credentials travel through the host's secret scope. These
# names are the declared env fallbacks; get_secret is used when available.
SECRET_KEYS = ("proxy_username", "proxy_password")


class Settings:
    """Snapshot of plugin settings with defaults, read once in register()."""

    def __init__(self, ctx: Any = None) -> None:
        self._ctx = ctx

    def get(self, key: str) -> Any:
        default = DEFAULTS.get(key, "")
        value = default
        if self._ctx is not None and hasattr(self._ctx, "get_config"):
            try:
                value = self._ctx.get_config(key, default)
            except Exception:  # noqa: BLE001 - a broken ctx must not break a tool
                value = default
        if key == "solver_url":
            env = os.environ.get("FLARESOLVERR_URL")
            if env:
                return env.rstrip("/")
        if key == "cdp_url":
            env = os.environ.get("BYPARR_CDP_URL")
            if env:
                return env.rstrip("/")
        if value is None:
            return default
        return value

    def solver_url(self) -> str:
        return str(self.get("solver_url")).rstrip("/")

    def cdp_url(self) -> str:
        return str(self.get("cdp_url")).rstrip("/")

    def timeout(self, supplied: Any = None) -> int:
        raw = supplied if supplied not in (None, "") else self.get("default_timeout_seconds")
        try:
            return max(1, int(raw))
        except (TypeError, ValueError):
            return max(1, int(self.get("default_timeout_seconds")))

    def int_key(self, key: str) -> int:
        try:
            return max(0, int(self.get(key)))
        except (TypeError, ValueError):
            return int(DEFAULTS.get(key, 0))

    def bool_key(self, key: str) -> bool:
        value = self.get(key)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on")
        return bool(value)

    def secrets(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for key in SECRET_KEYS:
            value = ""
            # Prefer the profile-aware host helper when running inside Hermes.
            try:
                from agent.secret_scope import get_secret  # type: ignore

                value = get_secret("BYPARR_" + key.upper(), "")
            except Exception:  # noqa: BLE001 - outside the host, fall back to env
                value = os.environ.get("BYPARR_" + key.upper(), "")
            if value:
                out[key] = value
        return out
