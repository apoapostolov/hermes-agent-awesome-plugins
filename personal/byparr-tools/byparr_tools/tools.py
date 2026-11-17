"""Read-only tools over the Bedroom Byparr solver. Stdlib only."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any, Dict, List

DEFAULT_BASE = "http://192.168.1.217:8191"
WALL_MARKERS = ("just a moment", "sec-if-cpt", "checking security", "access denied")


def _base() -> str:
    return os.environ.get("FLARESOLVERR_URL", DEFAULT_BASE).rstrip("/")


def _post(path: str, payload: Dict[str, Any], timeout: int,
          headers: Dict[str, str] | None = None) -> Any:
    req = urllib.request.Request(
        _base() + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _ok(**payload: Any) -> str:
    payload.setdefault("ok", True)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _fail(message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, default=str)


def _proxy_headers(args: Dict[str, Any]) -> Dict[str, str]:
    h: Dict[str, str] = {}
    if args.get("proxyServer"):
        h["X-Proxy-Server"] = str(args["proxyServer"])
    if args.get("proxyUsername"):
        h["X-Proxy-Username"] = str(args["proxyUsername"])
    if args.get("proxyPassword"):
        h["X-Proxy-Password"] = str(args["proxyPassword"])
    return h


def _timeout(args: Dict[str, Any]) -> int:
    try:
        return max(1, int(args.get("maxTimeout", 60)))
    except (TypeError, ValueError):
        return 60


def solver_get(args: Dict[str, Any], **kwargs: Any) -> str:
    url = str(args.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return _fail("url must start with http:// or https://")
    timeout = _timeout(args)
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": bool(args.get("blockMedia", True)),
    }
    try:
        data = _post("/v1", payload, timeout + 30, _proxy_headers(args))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver request failed: {type(exc).__name__}: {exc}")
    sol = data.get("solution") or {}
    body = sol.get("response") or ""
    wall = any(w in body.lower() for w in WALL_MARKERS)
    result: Dict[str, Any] = {
        "status": data.get("status"),
        "message": data.get("message"),
        "http_status": sol.get("status"),
        "final_url": sol.get("url"),
        "bytes": len(body),
        "wall": wall,
        "solved": data.get("status") == "ok" and not wall and len(body) >= 2000,
    }
    if args.get("returnHtml"):
        cap = max(1, int(args.get("maxChars", 6000)))
        result["html"] = body[:cap]
        result["html_truncated"] = len(body) > cap
    return _ok(**result)


def solver_cookies(args: Dict[str, Any], **kwargs: Any) -> str:
    url = str(args.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return _fail("url must start with http:// or https://")
    timeout = _timeout(args)
    payload = {
        "cmd": "request.get", "url": url, "maxTimeout": timeout,
        "blockMedia": True, "returnOnlyCookies": True,
    }
    try:
        data = _post("/v1", payload, timeout + 30, _proxy_headers(args))
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver request failed: {type(exc).__name__}: {exc}")
    sol = data.get("solution") or {}
    cookies: List[Dict[str, Any]] = sol.get("cookies") or []
    cdp: List[Dict[str, Any]] = []
    for c in cookies:
        item: Dict[str, Any] = {
            "name": c.get("name"), "value": c.get("value"),
            "domain": c.get("domain"), "path": c.get("path") or "/",
            "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly")),
        }
        exp = c.get("expires")
        if exp is not None:
            try:
                item["expires"] = -1 if exp < 0 else int(float(exp))
            except (TypeError, ValueError):
                pass
        same = str(c.get("sameSite") or "").lower()
        if same in ("lax", "strict", "none"):
            item["sameSite"] = same.capitalize()
        if c.get("partitionKey"):
            item["partitionKey"] = c["partitionKey"]
        cdp.append(item)
    show = bool(args.get("showValues", False))
    names = [c.get("name") for c in cookies]
    return _ok(
        count=len(cookies), names=names,
        values={c.get("name"): c.get("value") for c in cookies} if show else None,
        cdp={"cookies": cdp},
        user_agent=sol.get("userAgent", ""),
        note=("Set the target browser UA to user_agent and use a browser on Bedroom "
              "(same egress IP); cf_clearance is UA- and IP-bound."),
    )


def solver_load(args: Dict[str, Any], **kwargs: Any) -> str:
    urls = args.get("urls") or []
    if not isinstance(urls, list) or not urls:
        return _fail("urls must be a non-empty array")
    try:
        results = _post("/load", {"urls": urls}, timeout=240)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"solver load failed: {type(exc).__name__}: {exc}")
    cap = max(1, int(args.get("maxChars", 3000)))
    out = []
    for r in results or []:
        text = r.get("page_content") or ""
        out.append({
            "source": (r.get("metadata") or {}).get("source", ""),
            "chars": len(text),
            "truncated": len(text) > cap,
            "text": text[:cap],
        })
    return _ok(pages=out, count=len(out))
