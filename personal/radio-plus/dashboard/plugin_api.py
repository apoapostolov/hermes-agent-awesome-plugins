"""Radio Plus backend API: the Shoutcast directory, without renderer CORS.

The renderer cannot talk to ``directory.shoutcast.com`` directly: the directory
sends no ``Access-Control-Allow-Origin`` header and answers ``OPTIONS`` with 405,
so a browser-style preflight never passes. This route performs the same two
requests the Shoutcast directory site performs for itself:

* ``POST /Search/UpdateSearch`` (form field ``query``) returns a JSON array of
  stations, and ``POST /Home/Top`` returns the popular list.
* Each row carries an ``ID`` but no stream URL (``StreamUrl`` is always null in
  the public feed), so playback needs the station's PLS tune-in file, which does
  contain the real stream address. Resolution happens here, concurrently, and
  resolved addresses are cached: a dead station drops out of the results instead
  of surfacing a row that cannot play.

No key, account, or credential is involved. Only the Shoutcast directory is
contacted, nothing is written to disk, and the caller's query is the only thing
forwarded.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()

_DIRECTORY = "https://directory.shoutcast.com"
_TUNE_IN = "http://yp.shoutcast.com/sbin/tunein-station.pls?id={station_id}"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36 HermesRadioPlus/1.2"
)
_TIMEOUT = 12
_STREAM_TIMEOUT = 7
_RESOLVE_WORKERS = 12
_CACHE_TTL = 900.0
_QUERY_TTL = 300.0

_query_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_stream_cache: dict[int, tuple[float, str]] = {}


def _freshest(cache: dict[Any, tuple[float, Any]], key: Any, ttl: float) -> Any:
    entry = cache.get(key)
    if not entry:
        return None
    stamp, value = entry
    if time.time() - stamp > ttl:
        cache.pop(key, None)
        return None
    return value


def _query_directory(path: str, query: str | None) -> list[dict[str, Any]]:
    key = f"{path}\u0000{query or ''}".lower()
    cached = _freshest(_query_cache, key, _QUERY_TTL)
    if cached is not None:
        return cached
    if query:
        request = urllib.request.Request(
            f"{_DIRECTORY}{path}",
            data=urllib.parse.urlencode({"query": query}).encode(),
            method="POST",
            headers={
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
    else:
        request = urllib.request.Request(
            f"{_DIRECTORY}{path}",
            data=b"",
            method="POST",
            headers={"User-Agent": _USER_AGENT, "X-Requested-With": "XMLHttpRequest"},
        )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            body = response.read(4_000_000)
    except urllib.error.HTTPError as error:
        raise HTTPException(status_code=502, detail=f"Shoutcast directory returned HTTP {error.code}.") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise HTTPException(status_code=502, detail="Shoutcast directory is unreachable.") from error

    try:
        payload = json.loads(body.decode("utf-8-sig", "replace"))
    except ValueError as error:
        raise HTTPException(status_code=502, detail="Shoutcast directory returned no readable station list.") from error
    rows = [row for row in payload if isinstance(row, dict)] if isinstance(payload, list) else []
    _query_cache[key] = (time.time(), rows)
    return rows


def _stream_for(station_id: int) -> str | None:
    """Resolve a station's PLS tune-in file to the underlying stream URL."""
    cached = _freshest(_stream_cache, station_id, _CACHE_TTL)
    if cached is not None:
        return cached or None
    request = urllib.request.Request(
        _TUNE_IN.format(station_id=station_id),
        headers={"User-Agent": _USER_AGENT},
    )
    address: str | None = None
    try:
        with urllib.request.urlopen(request, timeout=_STREAM_TIMEOUT) as response:
            text = response.read(65_536).decode("utf-8", "replace")
        for line in text.splitlines():
            key, _, value = line.partition("=")
            if key.strip().lower() == "file1" and value.strip():
                address = _clean_stream(value.strip())
                break
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        address = None
    # A station can be listed while its tune-in file is empty. Cache the miss
    # briefly so a repeated search does not hammer a dead endpoint.
    _stream_cache[station_id] = (time.time(), address or "")
    return address


_TAG = re.compile(r"<[^>]{0,64}>")


def _clean_text(value: Any, limit: int = 160) -> str:
    if not isinstance(value, str):
        return ""
    # Unescape first: a directory name can carry &amp; or &#039; directly, and
    # unescaping can also expose markup that the tag strip must then remove.
    text = " ".join(_TAG.sub(" ", html.unescape(value)).split())
    return text[:limit]


def _clean_stream(value: str) -> str | None:
    """Accept only absolute http(s) stream addresses."""
    candidate = value.strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return None
    parsed = urllib.parse.urlsplit(candidate)
    if not parsed.hostname:
        return None
    return candidate


def _station_id(row: dict[str, Any]) -> int | None:
    raw = row.get("ID")
    if isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _station(row: dict[str, Any], url: str) -> dict[str, Any]:
    identifier = _station_id(row) or 0
    genre = _clean_text(row.get("Genre"), 60)
    bitrate = row.get("Bitrate") if isinstance(row.get("Bitrate"), int) else 0
    listeners = row.get("Listeners") if isinstance(row.get("Listeners"), int) else 0
    parts = [genre] if genre else []
    if bitrate > 0:
        parts.append(f"{bitrate} kbps")
    homepage = _clean_stream(_clean_text(row.get("IceUrl"), 400)) or ""
    return {
        "id": f"sc-{identifier}",
        "name": _clean_text(row.get("Name"), 120) or f"Shoutcast {identifier}",
        "url": url,
        "provider": "Shoutcast",
        "description": " \u00b7 ".join(parts),
        "nowPlaying": _clean_text(row.get("CurrentTrack"), 120),
        "homepage": homepage,
        "listeners": listeners,
        "bitrate": bitrate,
    }


_PRIVATE_HOST = re.compile(
    r"^(?:localhost|127\.|10\.|192\.168\.|169\.254\.|172\.(?:1[6-9]|2\d|3[01])\.|0\.|\[?::1\]?$)", re.I
)


_PROBE_TIMEOUT = 2.5
_PROBE_WORKERS = 24
_probe_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _probe_cached(address: str) -> dict[str, Any]:
    cached = _freshest(_probe_cache, address, _CACHE_TTL)
    if cached is not None:
        return cached
    verdict = _probe(address)
    _probe_cache[address] = (time.time(), verdict)
    return verdict


def _probe_many(addresses: list[str], budget: float = 2.0) -> dict[str, dict[str, Any]]:
    """Probe addresses concurrently under a wall-clock budget.

    One dead station must not hold a whole search: whatever has not answered
    inside ``budget`` is dropped from this response, and its probe keeps running
    so the next search finds a cached verdict instead of waiting again.
    """
    verdicts: dict[str, dict[str, Any]] = {}
    pending: list[str] = []
    for address in dict.fromkeys(addresses):
        cached = _freshest(_probe_cache, address, _CACHE_TTL)
        if cached is not None:
            verdicts[address] = cached
        else:
            pending.append(address)
    if not pending:
        return verdicts
    pool = ThreadPoolExecutor(max_workers=min(_PROBE_WORKERS, len(pending)))
    futures = {pool.submit(_probe_cached, address): address for address in pending}
    done, not_done = wait(futures, timeout=budget)
    for future in done:
        address = futures[future]
        try:
            verdicts[address] = future.result()
        except Exception:  # noqa: BLE001 - a probe failure is a station failure
            verdicts[address] = {"ok": False, "kind": "unreachable", "status": 0, "contentType": "", "reason": "The probe failed."}
    for future in not_done:
        future.cancel()
    pool.shutdown(wait=False)
    return verdicts


def _probe(url: str) -> dict[str, Any]:
    """Open a stream address and report what actually answers there.

    The renderer cannot do this: most stations send no CORS headers, so a
    browser fetch is refused before it starts. This is also the answer to "why
    does this station not play": a website URL answers ``text/html``, a dead
    mount answers 404, an HLS master playlist answers ``mpegurl``.
    """
    address = _clean_stream(url or "")
    if not address:
        return {"ok": False, "kind": "invalid", "status": 0, "contentType": "", "reason": "That is not an http or https address."}
    host = urllib.parse.urlsplit(address).hostname or ""
    if _PRIVATE_HOST.match(host):
        return {"ok": False, "kind": "invalid", "status": 0, "contentType": "", "reason": "Local addresses are not probed."}
    request = urllib.request.Request(
        address,
        headers={"User-Agent": _USER_AGENT, "Icy-MetaData": "1", "Accept": "*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_PROBE_TIMEOUT) as response:
            content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            name = response.headers.get("icy-name") or ""
            body = response.read(2048)
            status = response.status
    except urllib.error.HTTPError as error:
        return {
            "ok": False, "kind": "http-error", "status": error.code, "contentType": "",
            "reason": f"The server answered HTTP {error.code}.",
        }
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        return {
            "ok": False, "kind": "unreachable", "status": 0, "contentType": "",
            "reason": f"The server did not answer ({type(error).__name__}).",
        }

    lowered = address.lower()
    if "mpegurl" in content_type or lowered.endswith(".m3u8") or body[:7] == b"#EXTM3U":
        kind = "hls"
    elif content_type.startswith("audio/") or content_type in {"application/ogg", "video/ogg", "application/octet-stream"}:
        kind = "audio"
    elif content_type in {"audio/x-scpls", "audio/mpegurl", "application/pls+xml"} or lowered.endswith((".pls", ".m3u")):
        kind = "playlist"
    elif content_type.startswith("text/html") or body[:15].lower().lstrip().startswith(b"<!doctype") or body[:5].lower() == b"<html":
        kind = "html"
    elif content_type.startswith("text/"):
        kind = "text"
    else:
        kind = "other"
    return {
        "ok": kind in {"audio", "hls"},
        "kind": kind,
        "status": status,
        "contentType": content_type,
        "name": _clean_text(name, 80),
        "reason": {
            "audio": "The address returns audio.",
            "hls": "This is an HLS playlist. This player has no HLS support.",
            "playlist": "This is a playlist file, not a stream address.",
            "html": "This is a web page, not an audio stream.",
            "text": "This address returns text, not audio.",
            "other": f"This address returns {content_type or 'an unknown type'}, not audio.",
        }[kind],
    }


def _log_path() -> "Any":
    from pathlib import Path

    # Same home resolution the other user plugins use: HERMES_HOME when the
    # process has it, otherwise the Windows per-user install root.
    home = Path(os.environ.get("HERMES_HOME") or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hermes")
    return home / "radio-plus" / "station-log.jsonl"


def _append_log(entry: dict[str, Any]) -> None:
    """Append one JSON line, rotating at 1 MB so the file cannot grow forever."""
    path = _log_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > 1_000_000:
            path.replace(path.with_suffix(".jsonl.1"))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=True)[:2000] + "\n")
    except OSError:
        return


def _stations(rows: Iterable[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        identifier = _station_id(row)
        if identifier is None:
            continue
        candidates.append(row)
        if len(candidates) >= limit:
            break
    if not candidates:
        return [], 0
    with ThreadPoolExecutor(max_workers=min(_RESOLVE_WORKERS, len(candidates))) as pool:
        addresses = list(pool.map(lambda row: _stream_for(_station_id(row) or 0), candidates))
    resolved = [(row, address) for row, address in zip(candidates, addresses) if address]
    skipped = len(candidates) - len(resolved)
    if not resolved:
        return [], skipped
    verdicts = _probe_many([address for _, address in resolved])
    stations: list[dict[str, Any]] = []
    logged = 0
    for row, address in resolved:
        # A directory row can resolve to an address that no longer serves audio:
        # an HTML error page, a closed mount, an HLS playlist. Drop it instead of
        # handing the player a row that cannot play, and leave a line behind so
        # the failure is explainable later.
        verdict = verdicts.get(address) or {"ok": False, "kind": "slow", "reason": "No answer within the probe budget."}
        if not verdict["ok"]:
            skipped += 1
            if logged < 10:
                logged += 1
                _append_log({
                    "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "source": "shoutcast-resolve",
                    "name": _clean_text(row.get("Name"), 120),
                    "url": address,
                    "reason": f"{verdict['kind']}: {verdict['reason']}",
                })
            continue
        stations.append(_station(row, address))
    stations.sort(key=lambda item: item.get("listeners") or 0, reverse=True)
    return stations, skipped



@router.get("/shoutcast/search")
def shoutcast_search(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(40, ge=1, le=60),
) -> dict[str, Any]:
    """Search the Shoutcast directory by station name, genre, or keyword.

    ``GET /api/plugins/radio-plus/shoutcast/search?q=jazz&limit=40``
    """
    term = " ".join(q.split())[:80]
    if not term:
        raise HTTPException(status_code=400, detail="A search term is required.")
    rows = _query_directory("/Search/UpdateSearch", term)
    stations, skipped = _stations(rows, limit)
    return {"source": "shoutcast", "query": term, "count": len(rows), "skipped": skipped, "stations": stations}


@router.get("/shoutcast/top")
def shoutcast_top(limit: int = Query(40, ge=1, le=60)) -> dict[str, Any]:
    """Popular Shoutcast stations, busiest first.

    ``GET /api/plugins/radio-plus/shoutcast/top?limit=40``
    """
    rows = _query_directory("/Home/Top", None)
    stations, skipped = _stations(rows, limit)
    return {"source": "shoutcast", "query": "", "count": len(rows), "skipped": skipped, "stations": stations}


@router.get("/probe")
def probe_stream(url: str = Query(..., min_length=8, max_length=600)) -> dict[str, Any]:
    """Report what a stream address actually returns.

    ``GET /api/plugins/radio-plus/probe?url=https://example.test/stream``
    """
    return _probe(url)


class StationLogEntry(BaseModel):
    name: str = ""
    url: str = ""
    reason: str = ""
    at: str = ""


@router.post("/log")
def write_station_log(payload: StationLogEntry) -> dict[str, str]:
    """Keep one line per station failure for later diagnosis.

    ``POST /api/plugins/radio-plus/log`` with ``{name, url, reason}``
    """
    entry = {
        "at": payload.at or time.strftime("%Y-%m-%dT%H:%M:%S"),
        "source": "player",
        "name": _clean_text(payload.name, 120),
        "url": _clean_stream(_clean_text(payload.url, 400) or "") or "",
        "reason": _clean_text(payload.reason, 300),
    }
    _append_log(entry)
    return {"status": "logged", "path": str(_log_path())}

