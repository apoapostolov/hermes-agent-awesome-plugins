"""Portable, read-only tools over a FlareSolverr-compatible solver.

The solver address, timeouts, browser endpoint, proxy and fallback behaviour all
come from plugin Settings or environment variables. No host-specific value is
baked into this module, and no tool argument can redirect a stored credential.
Works with Byparr, FlareSolverr or any compatible API.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

from .cdp import inject_cookies
from .config import Settings
from .extract import extract as extract_structured
from .jar import CookieJar
from .queue import SolverQueue
from .safety import url_allowed

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


def _allow_private() -> bool:
    return _settings.bool_key("allow_private_targets")


def _proxy_headers() -> Dict[str, str]:
    """Proxy headers from Settings and the secret store, never from a tool argument.

    A model-chosen proxy host would receive the user's stored proxy credentials,
    so ``proxy_server`` is a setting and no handler reads a proxy field from
    ``args``. Credentials are resolved only when a proxy is configured, which
    keeps an unproxied install away from the secret store entirely.
    """
    server = str(_settings.get("proxy_server") or "").strip()
    if not server:
        return {}
    headers = {"X-Proxy-Server": server}
    secrets = _settings.secrets()
    username = secrets.get("proxy_username", "")
    password = secrets.get("proxy_password", "")
    if username:
        headers["X-Proxy-Username"] = username
    if password:
        headers["X-Proxy-Password"] = password
    return headers


def _walled(body: str) -> bool:
    low = body.lower()
    return any(marker in low for marker in WALL_MARKERS)


def _checked_url(value: Any) -> Tuple[str, str]:
    """(url, error). The error is empty when the host URL policy accepts the target."""
    url = str(value or "").strip()
    if not url:
        return "", "url is required"
    allowed, reason = url_allowed(url, _allow_private())
    if not allowed:
        return "", f"url rejected: {reason}"
    return url, ""


class _RedirectBlocked(Exception):
    """A redirect hop pointed at an address the URL policy refuses."""


class _SafeRedirects(urllib.request.HTTPRedirectHandler):
    """Re-check every redirect hop, so a public URL cannot bounce to a private one."""

    def __init__(self, allow_private: bool = False) -> None:
        self._allow_private = allow_private

    def redirect_request(self, req: Any, fp: Any, code: int, msg: str,
                         headers: Any, newurl: str) -> Any:
        allowed, reason = url_allowed(newurl, self._allow_private)
        if not allowed:
            raise _RedirectBlocked(f"redirect to {newurl} blocked: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _direct_open(url: str, timeout: int, allow_private: bool = False) -> Any:
    opener = urllib.request.build_opener(_SafeRedirects(allow_private))
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return opener.open(request, timeout=timeout)


def solver_get(args: Dict[str, Any], **kwargs: Any) -> str:
    url, error = _checked_url(args.get("url"))
    if not url:
        return _fail(error)
    timeout = _settings.timeout(args.get("maxTimeout"))
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": bool(args.get("blockMedia", _settings.get("block_media"))),
    }
    try:
        data = _queue.run(lambda: _post("/v1", payload, timeout + 30, _proxy_headers()))
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
    url, error = _checked_url(args.get("url"))
    if not url:
        return _fail(error)
    timeout = _settings.timeout(args.get("maxTimeout"))
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": True, "returnOnlyCookies": True,
    }
    try:
        data = _queue.run(lambda: _post("/v1", payload, timeout + 30, _proxy_headers()))
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
    # The result is what the model sees; the jar keeps the full cookies for
    # solver_bridge, which injects them without printing them.
    visible = [dict(item) for item in cdp] if show else [
        {key: val for key, val in item.items() if key != "value"} for item in cdp
    ]
    result: Dict[str, Any] = {
        "count": len(cookies),
        "names": [c.get("name") for c in cookies],
        "values": {c.get("name"): c.get("value") for c in cookies} if show else None,
        "cdp": {"cookies": visible},
        "user_agent": sol.get("userAgent", ""),
        "note": ("Match the reported user agent in the browser and use a browser "
                 "sharing the solver's egress IP when a cookie is IP-bound."),
    }
    session = str(args.get("session") or "")
    if session:
        result["jar"] = _jar.put(session, [dict(item) for item in cdp], result["user_agent"])
    return _ok(**result)


def solver_load(args: Dict[str, Any], **kwargs: Any) -> str:
    urls = args.get("urls") or []
    if not isinstance(urls, list) or not urls:
        return _fail("urls must be a non-empty array")
    rejected = []
    for value in urls:
        _, error = _checked_url(value)
        if error:
            rejected.append({"url": str(value)[:200], "reason": error})
    if rejected:
        return _fail("refusing URLs the host URL policy rejects", rejected=rejected)
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
            "proxy_configured": bool(_settings.get("proxy_server")),
            "allow_private_targets": _allow_private(),
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
    raw = str(args.get("url") or "").strip()
    if not html and raw:
        url, error = _checked_url(raw)
        if not url:
            return _fail(error)
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
    url, error = _checked_url(args.get("url"))
    if not url:
        return _fail(error)
    timeout = _settings.timeout(args.get("maxTimeout"))
    allow_private = _allow_private()
    body = ""
    via = "direct"
    blocked_redirect = ""
    try:
        with _direct_open(url, min(timeout, 20), allow_private) as response:
            body = response.read().decode("utf-8", "replace")
    except _RedirectBlocked as exc:
        blocked_redirect = str(exc)
        body = ""
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        body = ""
    walled = _walled(body)
    fallback_enabled = _settings.bool_key("auto_fallback")
    if not blocked_redirect and (walled or len(body) < 2000) and fallback_enabled:
        solved = json.loads(solver_get({"url": url, "returnHtml": True,
                                        "maxChars": 400000}))
        if solved.get("ok") and solved.get("bytes", 0) > len(body):
            body = solved.get("html", "")
            via = "solver"
    cap = max(1, int(args.get("maxChars", _settings.get("max_text_chars"))))
    result: Dict[str, Any] = dict(url=url, via=via, bytes=len(body),
                                  wall=_walled(body), text=body[:cap])
    if blocked_redirect:
        # The solver would follow the same chain, so the hop is reported, not retried.
        result["redirect_blocked"] = blocked_redirect
    return _ok(**result)


def jar_list(args: Dict[str, Any], **kwargs: Any) -> str:
    return _ok(sessions=_jar.list())


def jar_clear(args: Dict[str, Any], **kwargs: Any) -> str:
    session = str(args.get("session") or "")
    return _ok(cleared=_jar.clear(session), session=session)
