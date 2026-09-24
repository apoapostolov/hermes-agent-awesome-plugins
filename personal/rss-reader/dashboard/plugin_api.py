"""RSS Reader backend API: fetch public feeds without shell execution."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_MAX_BYTES = 2_000_000
_TIMEOUT = 25
_USER_AGENT = "HermesRSS/0.2"
_ARTICLE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)


class FeedRequest(BaseModel):
    url: str
    user_agent: str | None = None
    cookie: str | None = None


class GradingSkillRequest(BaseModel):
    name: str
    content: str = ""
    create_if_missing: bool = False


class PreferenceFileRequest(BaseModel):
    filename: str
    content: str


class ToolsEnabledRequest(BaseModel):
    enabled: bool = False


class CommandResultRequest(BaseModel):
    id: str
    ok: bool = True
    result: object | None = None
    error: str = ""


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


@router.post("/tools-enabled")
def write_tools_enabled(payload: ToolsEnabledRequest) -> dict[str, bool]:
    path = _hermes_home() / "rss-reader" / "tools-enabled.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": bool(payload.enabled)}), encoding="utf-8")
    return {"enabled": bool(payload.enabled)}


@router.get("/tools-enabled")
def read_tools_enabled() -> dict[str, bool]:
    path = _hermes_home() / "rss-reader" / "tools-enabled.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {"enabled": False}
    return {"enabled": bool(isinstance(data, dict) and data.get("enabled") is True)}


@router.post("/command-result")
def write_command_result(payload: CommandResultRequest) -> dict[str, str]:
    ident = re.sub(r"[^a-zA-Z0-9_-]", "", payload.id)[:80]
    if not ident:
        raise HTTPException(status_code=400, detail="Invalid command id.")
    folder = _hermes_home() / "rss-reader" / "results"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{ident}.json"
    path.write_text(
        json.dumps(
            {"id": ident, "ok": bool(payload.ok), "result": payload.result, "error": str(payload.error or "")[:400]},
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
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


def _request_user_agent(payload: FeedRequest, fallback: str) -> str:
    raw = str(payload.user_agent or "").strip()
    if 1 <= len(raw) <= 512 and all(32 <= ord(ch) <= 126 for ch in raw):
        return raw
    return fallback


def _is_youtube_url(raw: str) -> bool:
    host = (urlparse(raw).hostname or "").lower()
    return host.endswith("youtube.com") or host.endswith("youtu.be") or host.endswith("youtube-nocookie.com")


def _cookie_header(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if re.match(r"^[A-Za-z]:[\\/]", value) or value.startswith("/"):
        return ""
    if value.lower().startswith("cookie:"):
        value = value[7:].strip()
    if "\t" in value or value.lstrip().startswith("# Netscape"):
        pairs: list[str] = []
        for line in value.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain = parts[0].lower()
            if "youtube.com" not in domain and "google.com" not in domain:
                continue
            name, cookie_value = parts[5], parts[6]
            if name and "=" not in name:
                pairs.append(f"{name}={cookie_value}")
        return "; ".join(pairs)[:32000]
    if "=" not in value:
        return ""
    return value.replace("\n", " ").strip()[:32000]


def _headers_with_cookie(headers: dict[str, str], payload: FeedRequest, url: str) -> dict[str, str]:
    if not _is_youtube_url(url):
        return headers
    cookie = _cookie_header(payload.cookie or "")
    if not cookie:
        return headers
    return {**headers, "Cookie": cookie}


def _reddit_subreddit(raw: str) -> str | None:
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        return None
    if (parsed.hostname or "").lower() not in {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com"}:
        return None
    match = re.fullmatch(
        r"/r/([A-Za-z0-9_]{2,50})(?:/(?:hot|new|top|rising|\.rss))?",
        (parsed.path or "/").rstrip("/") or "/",
        flags=re.I,
    )
    return match.group(1) if match else None


def _reddit_api_url(raw: str) -> str | None:
    subreddit = _reddit_subreddit(raw)
    if not subreddit:
        return None
    return f"https://www.reddit.com/r/{subreddit}/.rss"


def _fetch_reddit(payload: FeedRequest) -> dict[str, str | int]:
    api_url = _reddit_api_url(payload.url)
    if not api_url:
        raise ValueError("Use a Reddit community URL such as https://www.reddit.com/r/python.")
    headers = {
        "Accept": "application/atom+xml, application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "identity",
        "User-Agent": _request_user_agent(payload, _USER_AGENT),
    }
    last_error: Exception | None = None
    for attempt in range(4):
        try:
            return _download(api_url, headers)
        except HTTPException as exc:
            last_error = exc
            detail = str(exc.detail or "")
            if "HTTP 429" not in detail or attempt == 3:
                if "HTTP 429" in detail:
                    raise HTTPException(
                        status_code=502,
                        detail="Reddit rate-limited the feed. Wait a few seconds and try again.",
                    ) from exc
                raise
            time.sleep(1.5 * (attempt + 1))
    raise last_error or HTTPException(status_code=502, detail="Reddit download failed.")


@router.post("/reddit")
def fetch_reddit(payload: FeedRequest) -> dict[str, str | int]:
    try:
        return _fetch_reddit(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Reddit download failed: {exc}") from exc
@router.post("/article")
def fetch_article(payload: FeedRequest) -> dict[str, str | int]:
    if _reddit_api_url(payload.url):
        return fetch_reddit(payload)
    return _download(
        payload.url,
        _headers_with_cookie(
            {
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Encoding": "identity",
                "User-Agent": _request_user_agent(payload, _ARTICLE_UA),
            },
            payload,
            payload.url,
        ),
    )


_FEEDSEARCH = "https://feedsearch.dev/api/v1/search"
_DISCOVERY_TLDS = (
    "com", "org", "net", "io", "co", "ai", "dev", "app", "me", "tv",
    "info", "biz", "news", "online", "xyz", "site", "tech", "store",
    "us", "ca", "uk", "au", "nz", "de", "fr", "es", "it", "nl",
    "be", "se", "no", "dk", "fi", "pl", "cz", "at", "ch", "ie",
    "pt", "in", "jp", "kr", "sg", "za", "br", "mx", "bg"
)


def _discover_targets(raw: str) -> tuple[str, list[str]]:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("Give a website URL, domain, or site name to search.")
    if "://" in value or "." in value or "/" in value:
        query = _discover_query(value)
        return query, [query]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,62}", value, re.IGNORECASE):
        raise ValueError("Use a site name, domain, or public website URL.")
    return value, [f"https://{value}.{tld}" for tld in _DISCOVERY_TLDS]


def _feedsearch_lookup(query: str) -> list[dict[str, object]]:
    target = f"{_FEEDSEARCH}?url={quote(query, safe='')}&info=true"
    opener = build_opener(_NoRedirect())
    request = Request(
        target,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": _USER_AGENT,
        },
    )
    with opener.open(request, timeout=min(_TIMEOUT, 12)) as response:
        body = _read_response(response)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("Feedsearch returned an unexpected payload.")
    return [row for row in data if isinstance(row, dict)]


def _discover_query(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("Give a website URL or domain to search.")
    if "://" not in value:
        value = "https://" + value
    return _validate_url(value)


@router.post("/discover")
def discover_feeds(payload: FeedRequest) -> dict[str, object]:
    try:
        query, targets = _discover_targets(payload.url)
        rows: list[dict[str, object]] = []
        failures = 0
        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = {pool.submit(_feedsearch_lookup, target): target for target in targets}
            for future in as_completed(futures):
                try:
                    rows.extend(future.result())
                except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError):
                    failures += 1
        if not rows and failures == len(targets):
            raise ValueError("Feed discovery returned no usable results.")
        return {"feeds": rows[:300], "query": query, "targets": len(targets)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HTTPException(status_code=502, detail=f"Feedsearch failed: {exc}") from exc


@router.post("/feed")
def fetch_feed(payload: FeedRequest) -> dict[str, str | int]:
    if _reddit_api_url(payload.url):
        return fetch_reddit(payload)
    return _download(
        payload.url,
        _headers_with_cookie(
            {"Accept-Encoding": "identity", "User-Agent": _request_user_agent(payload, _USER_AGENT)},
            payload,
            payload.url,
        ),
    )


def _download(source_url: str, headers: dict[str, str]) -> dict[str, str | int]:
    try:
        url = _validate_url(source_url)
        opener = build_opener(_NoRedirect())
        for _ in range(4):
            parsed = urlparse(url)
            _public_addresses(parsed.hostname or "")
            host = (parsed.hostname or "").lower()
            if "Cookie" in headers and "youtube.com" not in host and "youtu.be" not in host and "google.com" not in host:
                headers = {key: value for key, value in headers.items() if key.lower() != "cookie"}
            request = Request(url, headers=headers)
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


class PreviewRequest(BaseModel):
    url: str
    label: str = ""


@router.post("/preview")
def open_in_preview(payload: PreviewRequest) -> dict[str, str]:
    """Open an article in the desktop in-app preview pane.

    Emits the preview.open gateway event used by the in-app preview pane.
    """
    try:
        url = _validate_url(payload.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    label = (payload.label or url).strip()
    try:
        from tui_gateway.server import _broadcast_global_event
        _broadcast_global_event("preview.open", {"url": url, "label": label})
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Preview pane unavailable: {exc}") from exc
    return {"opened": url}
