"""URL admission for every solver call.

Hermes core owns the SSRF policy in ``tools.url_safety``: it blocks loopback,
private, link-local, reserved and cloud-metadata targets, honours
``security.allow_private_urls`` and the fake-ip ranges a local proxy declares,
and fails closed when a name does not resolve. Reusing it keeps a solver call
inside the same policy the built-in fetch tools follow, so a prompt-injected
URL cannot reach an address that ``web_extract`` refuses.

Outside a Hermes process the module is absent and there is no resolver policy to
borrow, so only the floor is enforced here: the scheme, address-shaped literals
and the cloud-metadata names and addresses. The plugin reports that weaker
guarantee in its README instead of implying full SSRF coverage.
"""
from __future__ import annotations

import ipaddress
from typing import Any, Optional, Tuple
from urllib.parse import urlsplit

SCHEMES = ("http", "https")
METADATA_HOSTS = frozenset({"metadata.google.internal", "metadata.goog"})
METADATA_IPS = frozenset({
    ipaddress.ip_address("169.254.169.254"),
    ipaddress.ip_address("fd00:ec2::254"),
})


def core() -> Optional[Any]:
    """Core's ``url_safety`` module, or None when this is not a Hermes process."""
    try:
        from tools import url_safety  # type: ignore
    except Exception:  # noqa: BLE001 - absent, or a different package named tools
        return None
    return url_safety


def split_host(url: str) -> Tuple[str, str]:
    """(scheme, hostname) in lower case, empty strings when the URL will not parse."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "", ""
    return (parts.scheme or "").lower(), (parts.hostname or "").lower()


def _ipv4_mapped(ip: Any) -> Optional[Any]:
    if isinstance(ip, ipaddress.IPv6Address):
        return ip.ipv4_mapped
    return None


def _literal_reason(host: str, allow_private: bool) -> str:
    """Why an address-shaped host must be refused, or "" when it may pass."""
    if not host:
        return "the URL has no hostname"
    if host in METADATA_HOSTS:
        return "cloud metadata hostname"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip in METADATA_IPS:
            return "cloud metadata address"
        mapped = _ipv4_mapped(ip)
        if mapped is not None and mapped in METADATA_IPS:
            return "cloud metadata address"
        if not allow_private and (ip.is_private or ip.is_loopback or ip.is_link_local
                                  or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return "private or internal address"
        return ""
    if not allow_private and (host == "localhost" or host.endswith(".localhost")):
        return "loopback hostname"
    return ""


def url_allowed(url: str, allow_private: bool = False) -> Tuple[bool, str]:
    """(allowed, reason). The reason is empty when the URL may be fetched.

    ``allow_private`` is the plugin's own LAN opt-in. It relaxes private ranges
    exactly as core's ``security.allow_private_urls`` does and never relaxes the
    cloud-metadata floor.
    """
    scheme, host = split_host(url)
    if scheme not in SCHEMES:
        return False, "only http and https URLs are accepted"
    module = core()
    if module is not None:
        name = "is_always_blocked_url" if allow_private else "is_safe_url"
        guard = getattr(module, name, None)
        if callable(guard):
            try:
                verdict = bool(guard(url))
            except Exception:  # noqa: BLE001 - a host error must not read as approval
                return False, "the host URL check failed"
            if allow_private:
                return (False, "cloud metadata address") if verdict else (True, "")
            if not verdict:
                return False, "private, internal or unresolvable address"
            # Core answers the resolved-name case. An address literal is still
            # judged here, because a host that set security.allow_private_urls
            # globally would otherwise answer "allowed" while this plugin's own
            # opt-in shows off.
            reason = _literal_reason(host, False)
            return (False, reason) if reason else (True, "")
    reason = _literal_reason(host, allow_private)
    return (False, reason) if reason else (True, "")
