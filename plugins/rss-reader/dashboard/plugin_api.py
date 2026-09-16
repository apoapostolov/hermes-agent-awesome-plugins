"""RSS Reader backend API: fetch public feeds without shell execution."""
from __future__ import annotations

import ipaddress
import json
import os
import re
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


class GradingSkillRequest(BaseModel):
    name: str
    content: str = ""
    create_if_missing: bool = False


class PreferenceFileRequest(BaseModel):
    filename: str
    content: str


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


def _hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hermes")


def _skill_path(name: str) -> Path:
    if not name or not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", name):
        raise HTTPException(status_code=400, detail="Invalid skill name.")
    return _hermes_home() / "skills" / name / "SKILL.md"


@router.get("/grading-skill")
def read_grading_skill(name: str) -> dict[str, str]:
    path = _skill_path(name.lower())
    return {"content": path.read_text(encoding="utf-8") if path.exists() else ""}


@router.post("/grading-skill")
def write_grading_skill(payload: GradingSkillRequest) -> dict[str, str]:
    path = _skill_path(payload.name.lower())
    if path.exists():
        return {"status": "present"}
    if not payload.create_if_missing:
        raise HTTPException(status_code=404, detail="Skill not found.")
    if len(payload.content.encode("utf-8")) > 100_000:
        raise HTTPException(status_code=413, detail="Skill is too large.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.content, encoding="utf-8")
    return {"status": "created"}


@router.post("/preference-file")
def write_preference_file(payload: PreferenceFileRequest) -> dict[str, str]:
    if payload.filename not in {"saved.json", "preference-report.md"}:
        raise HTTPException(status_code=400, detail="Invalid preference filename.")
    if len(payload.content.encode("utf-8")) > 2_000_000:
        raise HTTPException(status_code=413, detail="Preference file is too large.")
    path = _hermes_home() / "rss-reader" / payload.filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload.content, encoding="utf-8")
    return {"path": str(path)}


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


@router.post("/article")
def fetch_article(payload: FeedRequest) -> dict[str, str | int]:
    return fetch_feed(payload)


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
