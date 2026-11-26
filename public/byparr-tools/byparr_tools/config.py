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
    "proxy_server": "",
    "allow_private_targets": False,
}

# Sensitive proxy credentials travel through the host's secret scope. These
# names are the env-var names the host resolves; get_secret is used whenever the
# plugin runs inside Hermes.
SECRET_KEYS = ("proxy_username", "proxy_password")


def host_secret_scope() -> Any:
    """The host's profile-aware secret helper, or None outside a Hermes process.

    Only a failed import counts as "outside the host". Every other error is left
    to propagate, and ``UnscopedSecretError`` matters most: it means the read has
    no profile scope while a multiplexing gateway is active, so falling back to
    ``os.environ`` would hand this profile another profile's credential.
    """
    try:
        from agent import secret_scope  # type: ignore
    except ImportError:
        return None
    return secret_scope


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
        """Proxy credentials from the host scope, or from the env outside Hermes.

        The env read is gated on the host module being absent, not on an error
        from it: a host that raises is telling us the scope is missing, and that
        answer must reach the caller instead of becoming a silent env read.
        """
        scope = host_secret_scope()
        out: Dict[str, str] = {}
        for key in SECRET_KEYS:
            name = "BYPARR_" + key.upper()
            value = os.environ.get(name, "") if scope is None else scope.get_secret(name, "")
            if value:
                out[key] = str(value)
        return out
