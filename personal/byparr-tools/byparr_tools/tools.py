"""Portable, read-only tools over a FlareSolverr-compatible solver.

The solver address, timeouts, browser endpoint and fallback behaviour all come
from plugin Settings or environment variables. No host-specific value is baked
into this module. Works with Byparr, FlareSolverr or any compatible API.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from .cdp import inject_cookies
from .config import Settings
from .extract import extract as extract_structured
from .jar import CookieJar
from .queue import SolverQueue

WALL_MARKERS = ("just a moment", "sec-if-cpt", "checking security", "access denied")

_settings = Settings()
_queue = SolverQueue()
_jar = CookieJar()


def configure(ctx: Any = None) -> None:
    """Called from register(ctx) so a settings save takes effect on reload."""
    global _settings, _queue, _jar
    _settings = Settings(ctx)
    _queue = SolverQueue(
        spacing=float(_settings.get("request_spacing_seconds")),
        retries=_settings.int_key("max_retries"),
    )
    _jar = CookieJar(
        ttl=_settings.int_key("cookie_jar_ttl_seconds"),
        persist=_settings.bool_key("persist_cookie_jar"),
        data_dir=str(_settings.get("cookie_jar_dir") or ""),
    )


def _post(path: str, payload: Dict[str, Any], timeout: int,
          headers: Dict[str, str] | None = None) -> Any:
    request = urllib.request.Request(
        _settings.solver_url() + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _get_json(path: str, timeout: int = 10) -> Any:
    with urllib.request.urlopen(_settings.solver_url() + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _proxy_headers(args: Dict[str, Any]) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    secrets = _settings.secrets()
    pairs = (
        ("proxyServer", "X-Proxy-Server", str(_settings.get("proxy_server") or "")),
        ("proxyUsername", "X-Proxy-Username", secrets.get("proxy_username", "")),
        ("proxyPassword", "X-Proxy-Password", secrets.get("proxy_password", "")),
    )
    for key, header, fallback in pairs:
        value = args.get(key) or fallback
        if value:
            headers[header] = str(value)
    return headers


def _walled(body: str) -> bool:
    low = body.lower()
    return any(marker in low for marker in WALL_MARKERS)


def _valid_url(args: Dict[str, Any]) -> str | None:
    url = str(args.get("url") or "")
    return url if url.startswith(("http://", "https://")) else None


def solver_get(args: Dict[str, Any], **kwargs: Any) -> str:
    url = _valid_url(args)
    if not url:
        return _fail("url must start with http:// or https://")
    timeout = _settings.timeout(args.get("maxTimeout"))
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": bool(args.get("blockMedia", _settings.get("block_media"))),
    }
    try:
        data = _queue.run(lambda: _post("/v1", payload, timeout + 30, _proxy_headers(args)))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver request failed: {type(exc).__name__}: {exc}")
    sol = data.get("solution") or {}
    body = sol.get("response") or ""
    wall = _walled(body)
    result: Dict[str, Any] = {
        "status": data.get("status"), "message": data.get("message"),
        "http_status": sol.get("status"), "final_url": sol.get("url"),
        "bytes": len(body), "wall": wall,
        "solved": data.get("status") == "ok" and not wall and len(body) >= 2000,
    }
    if args.get("returnHtml", _settings.get("return_html_default")):
        cap = max(1, int(args.get("maxChars", _settings.get("max_html_chars"))))
        result["html"] = body[:cap]
        result["html_truncated"] = len(body) > cap
    return _ok(**result)


def solver_cookies(args: Dict[str, Any], **kwargs: Any) -> str:
    url = _valid_url(args)
    if not url:
        return _fail("url must start with http:// or https://")
    timeout = _settings.timeout(args.get("maxTimeout"))
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": True, "returnOnlyCookies": True,
    }
    try:
        data = _queue.run(lambda: _post("/v1", payload, timeout + 30, _proxy_headers(args)))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver request failed: {type(exc).__name__}: {exc}")
    sol = data.get("solution") or {}
    cookies: List[Dict[str, Any]] = sol.get("cookies") or []
    cdp: List[Dict[str, Any]] = []
    for cookie in cookies:
        item: Dict[str, Any] = {
            "name": cookie.get("name"), "value": cookie.get("value"),
            "domain": cookie.get("domain"), "path": cookie.get("path") or "/",
            "secure": bool(cookie.get("secure")), "httpOnly": bool(cookie.get("httpOnly")),
        }
        exp = cookie.get("expires")
        if exp is not None:
            try:
                item["expires"] = -1 if exp < 0 else int(float(exp))
            except (TypeError, ValueError):
                pass
        same = str(cookie.get("sameSite") or "").lower()
        if same in ("lax", "strict", "none"):
            item["sameSite"] = same.capitalize()
        if cookie.get("partitionKey"):
            item["partitionKey"] = cookie["partitionKey"]
        cdp.append(item)
    show = bool(args.get("showValues", False))
    result: Dict[str, Any] = {
        "count": len(cookies),
        "names": [c.get("name") for c in cookies],
        "values": {c.get("name"): c.get("value") for c in cookies} if show else None,
        "cdp": {"cookies": cdp},
        "user_agent": sol.get("userAgent", ""),
        "note": ("Match the reported user agent in the browser and use a browser "
                 "sharing the solver's egress IP when a cookie is IP-bound."),
    }
    session = str(args.get("session") or "")
    if session:
        result["jar"] = _jar.put(session, cdp, result["user_agent"])
    return _ok(**result)


def solver_load(args: Dict[str, Any], **kwargs: Any) -> str:
    urls = args.get("urls") or []
    if not isinstance(urls, list) or not urls:
        return _fail("urls must be a non-empty array")
    try:
        results = _queue.run(lambda: _post("/load", {"urls": urls}, timeout=240))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver load failed: {type(exc).__name__}: {exc}")
    cap = max(1, int(args.get("maxChars", _settings.get("max_text_chars"))))
    pages = []
    for record in results or []:
        text = record.get("page_content") or ""
        pages.append({
            "source": (record.get("metadata") or {}).get("source", ""),
            "chars": len(text), "truncated": len(text) > cap, "text": text[:cap],
        })
    return _ok(pages=pages, count=len(pages))


def solver_status(args: Dict[str, Any], **kwargs: Any) -> str:
    import time

    started = time.monotonic()
    try:
        health = _get_json("/health", timeout=10)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver unreachable: {type(exc).__name__}: {exc}",
                     solver_url=_settings.solver_url())
    latency_ms = int((time.monotonic() - started) * 1000)
    version = ""
    if isinstance(health, dict):
        version = str(health.get("version") or health.get("msg") or "")[:120]
    return _ok(
        solver_url=_settings.solver_url(),
        health=health, version=version, latency_ms=latency_ms,
        queue=_queue.stats(),
        settings_summary={
            "default_timeout_seconds": _settings.get("default_timeout_seconds"),
            "auto_fallback": _settings.bool_key("auto_fallback"),
            "block_media": _settings.get("block_media"),
            "cdp_url_configured": bool(_settings.cdp_url()),
            "proxy_configured": bool(_settings.secrets()),
        },
    )


def solver_bridge(args: Dict[str, Any], **kwargs: Any) -> str:
    session = str(args.get("session") or "")
    entry = _jar.get(session) if session else None
    cookies = args.get("cookies")
    if not isinstance(cookies, list) and entry:
        cookies = entry.get("cookies") or []
    if not isinstance(cookies, list) or not cookies:
        return _fail("provide a stored session or a cookies array")
    user_agent = str(args.get("user_agent") or (entry or {}).get("user_agent", ""))
    result = inject_cookies(cookies, _settings.cdp_url(), user_agent)
    return _ok(**result) if result.get("ok") else _fail(
        str(result.get("error", "bridge failed")), **result
    )


def solver_extract(args: Dict[str, Any], **kwargs: Any) -> str:
    html = str(args.get("html") or "")
    url = _valid_url(args)
    if not html and url:
        single = json.loads(solver_get({"url": url, "returnHtml": True,
                                        "maxChars": 400000}))
        if not single.get("ok"):
            return _fail(str(single.get("error", "fetch failed")))
        html = single.get("html", "")
    if not html:
        return _fail("provide html or url")
    return _ok(**extract_structured(html))


def solver_fetch(args: Dict[str, Any], **kwargs: Any) -> str:
    """Plain fetch first, solver fallback on a walled or failed response."""
    url = _valid_url(args)
    if not url:
        return _fail("url must start with http:// or https://")
    timeout = _settings.timeout(args.get("maxTimeout"))
    body = ""
    via = "direct"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=min(timeout, 20)) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        body = ""
    walled = _walled(body)
    fallback_enabled = _settings.bool_key("auto_fallback")
    if (walled or len(body) < 2000) and fallback_enabled:
        solved = json.loads(solver_get({"url": url, "returnHtml": True,
                                        "maxChars": 400000}))
        if solved.get("ok") and solved.get("bytes", 0) > len(body):
            body = solved.get("html", "")
            via = "solver"
    cap = max(1, int(args.get("maxChars", _settings.get("max_text_chars"))))
    return _ok(url=url, via=via, bytes=len(body), wall=_walled(body), text=body[:cap])


def jar_list(args: Dict[str, Any], **kwargs: Any) -> str:
    return _ok(sessions=_jar.list())


def jar_clear(args: Dict[str, Any], **kwargs: Any) -> str:
    session = str(args.get("session") or "")
    return _ok(cleared=_jar.clear(session), session=session)
