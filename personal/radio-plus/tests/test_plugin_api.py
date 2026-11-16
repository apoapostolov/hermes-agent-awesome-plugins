"""Tests for the Radio Plus Shoutcast route.

Offline tests pin the mapping rules. The live tests hit the real Shoutcast
directory and stream resolver and run only with ``RADIO_PLUS_LIVE=1``.

    python -m pytest tests/test_plugin_api.py -q
    RADIO_PLUS_LIVE=1 python -m pytest tests/test_plugin_api.py -q
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parents[1] / "dashboard" / "plugin_api.py"
_spec = importlib.util.spec_from_file_location("radio_plus_api", MODULE_PATH)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

LIVE = os.environ.get("RADIO_PLUS_LIVE") == "1"


@pytest.fixture(autouse=True)
def _clear_caches():
    """Every test starts with empty caches so a verdict cannot leak across cases."""
    for cache in (api._query_cache, api._stream_cache, api._probe_cache):
        cache.clear()
    yield


ROW = {
    "ID": 99426190,
    "Name": "BEST SMOOTH JAZZ  - UK (LONDON) HOST ROD LUCAS",
    "Format": "audio/mpeg",
    "Bitrate": 128,
    "Genre": "Smooth Jazz",
    "CurrentTrack": "Host Rod Lucas - Londons Best Smooth Jazz UK",
    "Listeners": 443,
    "IsRadionomy": False,
    "IceUrl": "https://bestsmoothjazz.com",
    "StreamUrl": None,
    "AACEnabled": 0,
    "IsPlaying": False,
    "IsAACEnabled": False,
}


def test_clean_text_strips_markup_and_entities():
    assert api._clean_text("Tom &amp; Jerry <b>Live</b>") == "Tom & Jerry Live"
    assert api._clean_text(None) == ""
    assert api._clean_text("  spaced\tout  ") == "spaced out"


def test_clean_stream_rejects_non_http_and_hostless():
    assert api._clean_stream("http://162.252.171.80:8002/stream") == "http://162.252.171.80:8002/stream"
    assert api._clean_stream("https://server5.mediasector.es:8020/jazzradiospain.mp3") is not None
    assert api._clean_stream("file://../../victim") is None
    assert api._clean_stream("http://") is None
    assert api._clean_stream("") is None


def test_station_id_requires_positive_integer():
    assert api._station_id({"ID": 12}) == 12
    assert api._station_id({"ID": "12"}) == 12
    assert api._station_id({"ID": 0}) is None
    assert api._station_id({"ID": True}) is None
    assert api._station_id({}) is None


def test_station_maps_directory_row_to_playable_station():
    station = api._station(ROW, "http://162.252.171.80:8002/stream")
    assert station["id"] == "sc-99426190"
    assert station["provider"] == "Shoutcast"
    assert station["url"] == "http://162.252.171.80:8002/stream"
    assert station["description"] == "Smooth Jazz · 128 kbps"
    assert station["homepage"] == "https://bestsmoothjazz.com"
    assert station["nowPlaying"] == "Host Rod Lucas - Londons Best Smooth Jazz UK"
    assert station["listeners"] == 443


def test_station_without_homepage_keeps_current_track_only():
    row = dict(ROW, IceUrl=None, CurrentTrack="", Genre="")
    station = api._station(row, "http://example.test/stream")
    assert station["homepage"] == ""
    assert station["description"] == "128 kbps"


def test_stations_drop_unresolvable_rows_and_sort_by_listeners(monkeypatch):
    rows = [
        dict(ROW, ID=1, Listeners=10),
        dict(ROW, ID=2, Listeners=900),
        dict(ROW, ID=3, Listeners=50),
    ]
    monkeypatch.setattr(api, "_stream_for", lambda station_id: None if station_id == 1 else f"http://example.test/{station_id}")
    monkeypatch.setattr(api, "_probe", lambda url: {"ok": True, "kind": "audio", "status": 200, "contentType": "audio/mpeg", "reason": ""})
    page = api._stations(rows, limit=10)
    assert [item["id"] for item in page["stations"]] == ["sc-2", "sc-3"]
    assert page["skipped"] == 1


def test_stations_drop_addresses_that_no_longer_serve_audio(monkeypatch):
    """A directory row that resolves to an HTML page must not reach the player."""
    rows = [dict(ROW, ID=7), dict(ROW, ID=8)]
    monkeypatch.setattr(api, "_stream_for", lambda station_id: f"http://example.test/{station_id}")
    monkeypatch.setattr(api, "_probe", lambda url: {
        "ok": "8" not in url, "kind": "html" if "8" in url else "audio", "status": 200,
        "contentType": "text/html" if "8" in url else "audio/mpeg", "reason": "",
    })
    logged: list[dict] = []
    monkeypatch.setattr(api, "_append_log", lambda entry: logged.append(entry))
    page = api._stations(rows, limit=10)
    assert [item["id"] for item in page["stations"]] == ["sc-7"]
    assert page["skipped"] == 1
    assert logged and logged[0]["source"] == "shoutcast-resolve"
    assert "html" in logged[0]["reason"]


def test_stations_respect_limit_before_resolving(monkeypatch):
    rows = [dict(ROW, ID=index) for index in range(1, 21)]
    calls: list[int] = []
    monkeypatch.setattr(api, "_stream_for", lambda station_id: calls.append(station_id) or "http://example.test/x")
    monkeypatch.setattr(api, "_probe", lambda url: {"ok": True, "kind": "audio", "status": 200, "contentType": "audio/mpeg", "reason": ""})
    api._stations(rows, limit=5)
    assert len(calls) == 5


def test_stations_page_with_an_offset_and_say_where_the_next_one_starts(monkeypatch):
    """A page is a slice of the directory list, and rows that resolve to nothing
    still count as consumed, so the next page does not read them again."""
    rows = [dict(ROW, ID=index) for index in range(1, 13)]
    seen: list[int] = []
    monkeypatch.setattr(api, "_stream_for", lambda station_id: seen.append(station_id) or f"http://example.test/{station_id}")
    # Station 5 resolves to nothing, so its page comes back one station short.
    monkeypatch.setattr(api, "_stream_for", lambda station_id: None if station_id == 5 else f"http://example.test/{station_id}")
    monkeypatch.setattr(api, "_probe", lambda url: {"ok": True, "kind": "audio", "status": 200, "contentType": "audio/mpeg", "reason": ""})
    first = api._stations(rows, limit=4)
    assert [item["id"] for item in first["stations"]] == ["sc-1", "sc-2", "sc-3", "sc-4"]
    assert first["count"] == 12
    assert first["next"] == 4
    second = api._stations(rows, limit=4, offset=4)
    assert [item["id"] for item in second["stations"]] == ["sc-6", "sc-7", "sc-8"]
    assert second["skipped"] == 1
    assert second["next"] == 8, "a skipped row is consumed, so the next page starts past it"
    assert first["stations"][0]["id"] != second["stations"][0]["id"]
    last = api._stations(rows, limit=4, offset=12)
    assert last["stations"] == []
    assert last["next"] == 12 == last["count"], "past the end there is nothing left"


def test_probe_rejects_non_http_and_local_addresses():
    assert api._probe("")["kind"] == "invalid"
    assert api._probe("not a url")["kind"] == "invalid"
    assert api._probe("http://127.0.0.1:8000/stream")["kind"] == "invalid"
    assert api._probe("http://localhost/stream")["kind"] == "invalid"
    assert api._probe("http://192.168.1.9:8000/")["kind"] == "invalid"



def test_freshest_expires_entries():
    cache = {"k": (api.time.time(), ["old"])}
    assert api._freshest(cache, "k", ttl=60) == ["old"]
    cache["k"] = (0.0, ["old"])
    assert api._freshest(cache, "k", ttl=60) is None
    assert "k" not in cache
    assert api._freshest(cache, "missing", ttl=60) is None


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")
def test_live_search_returns_playable_stations():
    result = api.shoutcast_search(q="jazz", limit=12)
    assert result["source"] == "shoutcast"
    assert result["stations"], "Shoutcast returned no playable jazz station"
    for station in result["stations"]:
        assert station["url"].startswith(("http://", "https://"))
        assert station["id"].startswith("sc-")


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")
def test_live_top_is_sorted_by_listeners():
    result = api.shoutcast_top(limit=8)
    listeners = [station["listeners"] for station in result["stations"]]
    assert listeners == sorted(listeners, reverse=True)


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")
def test_live_top_pages_with_an_offset():
    """The route pages the real directory: page two is not page one, and the
    response says where the next slice starts."""
    first = api.shoutcast_top(limit=6)
    second = api.shoutcast_top(limit=6, offset=6)
    assert first["stations"] and second["stations"]
    assert first["next"] == 6, "the first page ends where the second starts"
    assert second["next"] == 12
    assert first["count"] > first["next"], "the directory holds more than one page"
    first_ids = {station["id"] for station in first["stations"]}
    repeated = [station for station in second["stations"] if station["id"] in first_ids]
    assert not repeated, f"page two repeated {len(repeated)} stations"


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")
def test_live_station_holds_no_undeclared_keys():
    station = api.shoutcast_top(limit=1)["stations"][0]
    assert set(station) == {
        "id", "name", "url", "provider", "description", "nowPlaying", "homepage", "listeners", "bitrate",
    }


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")
def test_router_answers_under_the_mounted_prefix():
    """The dashboard mounts this router at /api/plugins/radio-plus."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/radio-plus")
    client = TestClient(app)

    top = client.get("/api/plugins/radio-plus/shoutcast/top", params={"limit": 3})
    assert top.status_code == 200
    payload = top.json()
    assert payload["source"] == "shoutcast"
    assert 0 < len(payload["stations"]) <= 3

    search = client.get("/api/plugins/radio-plus/shoutcast/search", params={"q": "jazz", "limit": 5})
    assert search.status_code == 200
    assert search.json()["query"] == "jazz"

    assert client.get("/api/plugins/radio-plus/shoutcast/search", params={"q": ""}).status_code == 422
    assert client.get("/api/plugins/radio-plus/shoutcast/search", params={"q": "jazz", "limit": 500}).status_code == 422


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to probe real stations")
def test_live_probe_tells_a_website_from_a_stream_from_hls():
    """The belisimo.BG mount answers HTML; BNR Horizont answers AAC; BNR HLS is a playlist."""
    website = api._probe("http://79.98.108.170:8002")
    assert website["ok"] is False
    assert website["kind"] == "html"

    audio = api._probe("https://play.global.audio/testb.aac?dist=RADIOPLAY")
    assert audio["ok"] is True
    assert audio["kind"] == "audio"
    assert "bnr" in audio["name"].lower()

    playlist = api._probe("https://lb-hls.cdn.bg/2032/fls/Horizont.stream/playlist.m3u8")
    assert playlist["kind"] == "hls"
    assert playlist["ok"] is True, "an HLS playlist is playable now that the player ships hls.js"


def test_log_route_writes_one_json_line(monkeypatch, tmp_path):
    import json

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/radio-plus")
    client = TestClient(app)

    response = client.post("/api/plugins/radio-plus/log", json={
        "name": "Belisimo.BG", "url": "http://79.98.108.170:8002", "reason": "html: this is a web page",
    })
    assert response.status_code == 200
    assert response.json()["status"] == "logged"

    path = tmp_path / "radio-plus" / "station-log.jsonl"
    assert path.exists()
    line = json.loads(path.read_text(encoding="utf-8").strip())
    assert line["name"] == "Belisimo.BG"
    assert line["source"] == "player"
    assert line["url"].startswith("http://79.98.108.170")


@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to probe real stations")
def test_probe_route_is_mounted():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(api.router, prefix="/api/plugins/radio-plus")
    client = TestClient(app)

    response = client.get("/api/plugins/radio-plus/probe", params={"url": "https://play.global.audio/testb.aac?dist=RADIOPLAY"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert client.get("/api/plugins/radio-plus/probe", params={"url": "x"}).status_code == 422
