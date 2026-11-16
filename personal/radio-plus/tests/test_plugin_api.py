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
    stations = api._stations(rows, limit=10)
    assert [item["id"] for item in stations] == ["sc-2", "sc-3"]


def test_stations_respect_limit_before_resolving(monkeypatch):
    rows = [dict(ROW, ID=index) for index in range(1, 21)]
    calls: list[int] = []
    monkeypatch.setattr(api, "_stream_for", lambda station_id: calls.append(station_id) or "http://example.test/x")
    api._stations(rows, limit=5)
    assert len(calls) == 5


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
