"""Minimal CDP client for injecting solver cookies into a browser.

Uses only stdlib: a short WebSocket handshake and RFC 6455 client frames over a
raw socket. No third-party dependency, so the plugin stays portable. The target
CDP endpoint comes from Settings (BYPARR_CDP_URL) and defaults to loopback.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request
from typing import Any, Dict, List
from urllib.parse import urlparse


def _endpoint(cdp_url: str) -> tuple[str, int, str]:
    parsed = urlparse(cdp_url)
    scheme = parsed.scheme or "http"
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if scheme == "https" else 9222)
    return host, port, parsed.path or "/"


def _first_target(cdp_url: str) -> str | None:
    """Pick the first page target exposing a webSocketDebuggerUrl."""
    parsed = urlparse(cdp_url)
    base = f"{parsed.scheme or 'http'}://{parsed.netloc or '127.0.0.1'}"
    try:
        with urllib.request.urlopen(base + "/json/list", timeout=5) as resp:
            targets = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    for target in targets or []:
        if target.get("type") == "page" and target.get("webSocketDebuggerUrl"):
            return target["webSocketDebuggerUrl"]
    return None


class _WS:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        parsed = urlparse(url)
        self._host = parsed.hostname or "127.0.0.1"
        self._port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        self._path = parsed.path or "/"
        self._sock = socket.create_connection((self._host, self._port), timeout=timeout)
        self._sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request = (
            f"GET {self._path} HTTP/1.1\r\n"
            f"Host: {self._host}:{self._port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
        )
        self._sock.sendall(request.encode("ascii"))
        header = b""
        while b"\r\n\r\n" not in header:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("CDP websocket handshake closed")
            header += chunk
        if b" 101 " not in header.split(b"\r\n", 1)[0]:
            raise ConnectionError("CDP websocket handshake refused")

    def send(self, obj: Dict[str, Any]) -> None:
        payload = json.dumps(obj).encode("utf-8")
        mask = os.urandom(4)
        length = len(payload)
        if length < 126:
            frame = bytes((0x81, 0x80 | length))
        elif length < 65536:
            frame = bytes((0x81, 0x80 | 126)) + struct.pack("!H", length)
        else:
            frame = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", length)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self._sock.sendall(frame + mask + masked)

    def recv(self) -> Dict[str, Any]:
        head = self._recv_exact(2)
        opcode = head[0] & 0x0F
        length = head[1] & 0x7F
        if length == 126:
            length = struct.unpack("!H", self._recv_exact(2))[0]
        elif length == 127:
            length = struct.unpack("!Q", self._recv_exact(8))[0]
        payload = self._recv_exact(length)
        if opcode == 0x8:
            raise ConnectionError("CDP closed the socket")
        return json.loads(payload.decode("utf-8", "replace"))

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("CDP socket closed mid-frame")
            buf += chunk
        return buf

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def call(ws_url: str, method: str, params: Dict[str, Any], ident: int = 1) -> Dict[str, Any]:
    ws = _WS(ws_url)
    try:
        ws.send({"id": ident, "method": method, "params": params})
        while True:
            message = ws.recv()
            if message.get("id") == ident:
                return message
    finally:
        ws.close()


def inject_cookies(cookies: List[Dict[str, Any]], cdp_url: str, user_agent: str = "") -> Dict[str, Any]:
    """Inject a solver_cookies payload into the first CDP page target."""
    target = _first_target(cdp_url)
    if not target:
        return {"ok": False, "error": "no CDP page target found at configured endpoint"}
    steps: List[str] = []
    try:
        call(target, "Network.enable", {}, 1)
        steps.append("Network.enable")
        call(target, "Network.setCookies", {"cookies": cookies}, 2)
        steps.append("Network.setCookies")
        if user_agent:
            call(target, "Network.setUserAgentOverride", {"userAgent": user_agent}, 3)
            steps.append("Network.setUserAgentOverride")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"CDP injection failed: {exc}", "steps": steps}
    return {
        "ok": True,
        "injected": len(cookies),
        "steps": steps,
        "note": "Cookies apply to the current CDP target. Reload the page to confirm.",
    }
