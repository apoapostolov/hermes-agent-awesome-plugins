#!/usr/bin/env python3
"""Dependency-free MCP stdio server for a FlareSolverr-compatible solver.

Speaks MCP's newline-delimited JSON-RPC 2.0 over stdin/stdout using only the
standard library, so it runs on any machine with Python 3.10+. The solver
address comes from BYPAAR_BASE_URL, forwarded by the plugin package. No local
or machine-specific value is baked into this file.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List

BASE = os.environ.get("BYPAAR_BASE_URL", "http://127.0.0.1:8191").rstrip("/")
WALL_MARKERS = ("just a moment", "sec-if-cpt", "checking security", "access denied")


def _post(path: str, payload: Any, timeout: int) -> Any:
    request = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _get(path: str, timeout: int = 10) -> Any:
    with urllib.request.urlopen(BASE + path, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _text(obj: Any) -> str:
    content = {"type": "text", "text": json.dumps(obj, ensure_ascii=False, default=str)}
    return json.dumps({"content": [content]})


def _error(message: str) -> str:
    return json.dumps({"content": [{"type": "text", "text": json.dumps({"ok": False, "error": message})}], "isError": True})


def solver_get(args: Dict[str, Any]) -> Any:
    url = str(args.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://"}
    timeout = int(args.get("maxTimeout", 60))
    try:
        data = _post("/v1", {"cmd": "request.get", "url": url,
                             "maxTimeout": timeout, "blockMedia": True},
                     timeout + 30)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sol = data.get("solution") or {}
    body = sol.get("response") or ""
    wall = any(m in body.lower() for m in WALL_MARKERS)
    result: Dict[str, Any] = {
        "ok": data.get("status") == "ok" and not wall and len(body) >= 2000,
        "status": data.get("status"), "bytes": len(body), "wall": wall,
    }
    if args.get("returnHtml"):
        cap = max(1, int(args.get("maxChars", 6000)))
        result["html"] = body[:cap]
    return result


def solver_cookies(args: Dict[str, Any]) -> Any:
    url = str(args.get("url") or "")
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "url must start with http:// or https://"}
    timeout = int(args.get("maxTimeout", 60))
    try:
        data = _post("/v1", {"cmd": "request.get", "url": url, "maxTimeout": timeout,
                             "blockMedia": True, "returnOnlyCookies": True}, timeout + 30)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    sol = data.get("solution") or {}
    cookies = sol.get("cookies") or []
    names = [c.get("name") for c in cookies]
    values = ({c.get("name"): c.get("value") for c in cookies}
              if args.get("showValues") else None)
    return {"ok": True, "count": len(cookies), "names": names, "values": values,
            "cdp": {"cookies": cookies}, "user_agent": sol.get("userAgent", "")}


def solver_load(args: Dict[str, Any]) -> Any:
    urls = args.get("urls") or []
    if not isinstance(urls, list) or not urls:
        return {"ok": False, "error": "urls must be a non-empty array"}
    try:
        results = _post("/load", {"urls": urls}, 240)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    cap = max(1, int(args.get("maxChars", 3000)))
    pages = []
    for record in results or []:
        text = record.get("page_content") or ""
        pages.append({"source": (record.get("metadata") or {}).get("source", ""),
                      "chars": len(text), "text": text[:cap]})
    return {"ok": True, "pages": pages, "count": len(pages)}


def solver_status(args: Dict[str, Any]) -> Any:
    try:
        health = _get("/health")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"solver unreachable: {type(exc).__name__}: {exc}",
                "solver_url": BASE}
    return {"ok": True, "solver_url": BASE, "health": health}


TOOLS = {
    "solver_get": (solver_get, {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "maxTimeout": {"type": "integer"},
            "blockMedia": {"type": "boolean"},
            "returnHtml": {"type": "boolean"},
            "maxChars": {"type": "integer"},
        },
        "required": ["url"],
    }, "Fetch a Cloudflare-walled public page through the configured solver and return solved HTML."),
    "solver_cookies": (solver_cookies, {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "maxTimeout": {"type": "integer"},
            "showValues": {"type": "boolean"},
        },
        "required": ["url"],
    }, "Harvest challenge cookies and a CDP payload plus the exact user agent to set in a browser."),
    "solver_load": (solver_load, {
        "type": "object",
        "properties": {
            "urls": {"type": "array", "items": {"type": "string"}},
            "maxChars": {"type": "integer"},
        },
        "required": ["urls"],
    }, "Batch-fetch public URLs to clean text for RAG and document capture."),
    "solver_status": (solver_status, {"type": "object", "properties": {}},
                      "Check solver health, version and latency at the configured address."),
}


def handle(message: Dict[str, Any]) -> Dict[str, Any] | None:
    method = message.get("method")
    ident = message.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": ident, "result": {
            "protocolVersion": "2025-06-18",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "byparr", "version": "0.2.0"},
        }}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": ident, "result": {}}
    if method == "tools/list":
        tools = [{"name": name, "description": desc, "inputSchema": schema}
                 for name, (_, schema, desc) in TOOLS.items()]
        return {"jsonrpc": "2.0", "id": ident, "result": {"tools": tools}}
    if method == "tools/call":
        params = message.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") or {}
        entry = TOOLS.get(name)
        if not entry:
            return {"jsonrpc": "2.0", "id": ident,
                    "error": {"code": -32601, "message": f"unknown tool: {name}"}}
        try:
            result = entry[0](arguments)
            return {"jsonrpc": "2.0", "id": ident,
                    "result": {"content": [{"type": "text",
                                            "text": json.dumps(result, ensure_ascii=False, default=str)}]}}
        except Exception as exc:  # noqa: BLE001
            return {"jsonrpc": "2.0", "id": ident,
                    "result": {"content": [{"type": "text", "text": str(exc)}], "isError": True}}
    if method and method.startswith("notifications/"):
        return None
    if ident is not None:
        return {"jsonrpc": "2.0", "id": ident,
                "error": {"code": -32601, "message": f"unknown method: {method}"}}
    return None


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
