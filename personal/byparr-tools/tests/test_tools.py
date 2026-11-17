"""Tests for byparr-tools. Offline by default; no live solver required."""
import json
from unittest import mock

from byparr_tools import tools


def test_solver_get_rejects_bad_url():
    r = json.loads(tools.solver_get({"url": "ftp://bad"}))
    assert r["ok"] is False


def test_solver_get_detects_wall():
    fake = {"status": "ok", "solution": {"response": "Just a moment...", "status": 403}}
    with mock.patch.object(tools, "_post", return_value=fake):
        r = json.loads(tools.solver_get({"url": "https://example.com"}))
    assert r["solved"] is False and r["wall"] is True


def test_solver_get_ok_and_truncate():
    body = "x" * 2500
    fake = {"status": "ok", "solution": {"response": body, "status": 200, "url": "https://example.com"}}
    with mock.patch.object(tools, "_post", return_value=fake):
        r = json.loads(tools.solver_get({"url": "https://example.com", "returnHtml": True, "maxChars": 10}))
    assert r["solved"] is True and r["bytes"] == 2500
    assert r["html"] == "x" * 10 and r["html_truncated"] is True


def test_solver_cookies_mapping_and_redaction():
    fake = {"status": "ok", "solution": {"userAgent": "UA/1", "cookies": [
        {"name": "cf_clearance", "value": "SECRET", "domain": ".x.com", "path": "/",
         "secure": True, "httpOnly": False, "expires": 1800000000, "sameSite": "None"},
    ]}}
    with mock.patch.object(tools, "_post", return_value=fake):
        r = json.loads(tools.solver_cookies({"url": "https://x.com"}))
    assert r["names"] == ["cf_clearance"]
    assert r["values"] is None
    assert r["cdp"]["cookies"][0]["sameSite"] == "None"
    assert r["user_agent"] == "UA/1"


def test_solver_cookies_show_values():
    fake = {"status": "ok", "solution": {"cookies": [{"name": "a", "value": "b"}]}}
    with mock.patch.object(tools, "_post", return_value=fake):
        r = json.loads(tools.solver_cookies({"url": "https://x.com", "showValues": True}))
    assert r["values"] == {"a": "b"}


def test_solver_load():
    fake = [{"page_content": "hello world", "metadata": {"source": "https://example.com"}}]
    with mock.patch.object(tools, "_post", return_value=fake):
        r = json.loads(tools.solver_load({"urls": ["https://example.com"], "maxChars": 5}))
    assert r["count"] == 1 and r["pages"][0]["text"] == "hello"


def test_proxy_headers():
    h = tools._proxy_headers({"proxyServer": "http://p:1", "proxyUsername": "u", "proxyPassword": "p"})
    assert h["X-Proxy-Server"] == "http://p:1"
