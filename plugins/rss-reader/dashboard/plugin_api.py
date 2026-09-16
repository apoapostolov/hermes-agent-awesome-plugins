"""RSS Reader backend API: fetch public feeds without shell execution."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_MAX_BYTES = 2_000_000
_TIMEOUT = 25
_USER_AGENT = "HermesRSS/0.2"


class FeedRequest(BaseModel):
    url: str


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _validate_url(raw: str) -> str:
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Use a public HTTP(S) feed URL without credentials.")
    if parsed.port and parsed.port not in {80, 443}:
        raise ValueError("Feed URLs must use a standard HTTP or HTTPS port.")
    if not parsed.hostname or "." not in parsed.hostname:
        raise ValueError("Feed host must be public.")
    if parsed.hostname.lower().endswith((".local", ".internal")) or parsed.hostname.lower() in {"localhost", "local"}:
        raise ValueError("Private feed hosts are blocked.")
    return parsed.geturl()


def _public_addresses(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("Feed host could not be resolved.") from exc
    addresses = {info[4][0] for info in infos}
    if not addresses or any(not ipaddress.ip_address(addr).is_global for addr in addresses):
        raise ValueError("Feed host must resolve to a public IPv4 address.")


def _read_response(response) -> bytes:
    body = response.read(_MAX_BYTES + 1)
    if len(body) > _MAX_BYTES:
        raise ValueError("Feed exceeds 2 MB.")
    return body


@router.get("/commands")
def read_commands() -> list[dict]:
    home = Path(os.environ.get("HERMES_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hermes")
    path = home / "rss-reader" / "commands.jsonl"
    if not path.exists():
        return []
    commands = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            commands.append(value)
    return commands


@router.post("/feed")
def fetch_feed(payload: FeedRequest) -> dict[str, str | int]:
    try:
        url = _validate_url(payload.url)
        opener = build_opener(_NoRedirect())
        for _ in range(4):
            parsed = urlparse(url)
            _public_addresses(parsed.hostname or "")
            request = Request(
                url,
                headers={"Accept-Encoding": "identity", "User-Agent": _USER_AGENT},
            )
            try:
                response = opener.open(request, timeout=_TIMEOUT)
            except HTTPError as exc:
                if exc.code in {301, 302, 303, 307, 308}:
                    location = exc.headers.get("Location")
                    if not location:
                        raise ValueError(f"The feed returned HTTP {exc.code} without a redirect target.")
                    url = _validate_url(urljoin(url, location))
                    continue
                raise ValueError(f"The feed returned HTTP {exc.code}.") from exc
            body = _read_response(response)
            charset = response.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset)
            except (LookupError, UnicodeDecodeError):
                text = body.decode("utf-8", errors="replace")
            return {"text": text, "url": url, "status": response.status}
        raise ValueError("The feed redirects too many times.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Feed download failed: {exc}") from exc
