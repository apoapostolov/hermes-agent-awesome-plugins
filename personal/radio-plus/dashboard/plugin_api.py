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
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from fastapi import APIRouter, HTTPException, Query

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


def _stations(rows: Iterable[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        identifier = _station_id(row)
        if identifier is None:
            continue
        candidates.append(row)
        if len(candidates) >= limit:
            break
    if not candidates:
        return []
    with ThreadPoolExecutor(max_workers=min(_RESOLVE_WORKERS, len(candidates))) as pool:
        addresses = list(pool.map(lambda row: _stream_for(_station_id(row) or 0), candidates))
    stations: list[dict[str, Any]] = []
    for row, address in zip(candidates, addresses):
        if address:
            stations.append(_station(row, address))
    stations.sort(key=lambda item: item.get("listeners") or 0, reverse=True)
    return stations


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
    return {"source": "shoutcast", "query": term, "count": len(rows), "stations": _stations(rows, limit)}


@router.get("/shoutcast/top")
def shoutcast_top(limit: int = Query(40, ge=1, le=60)) -> dict[str, Any]:
    """Popular Shoutcast stations, busiest first.

    ``GET /api/plugins/radio-plus/shoutcast/top?limit=40``
    """
    rows = _query_directory("/Home/Top", None)
    return {"source": "shoutcast", "query": "", "count": len(rows), "stations": _stations(rows, limit)}
