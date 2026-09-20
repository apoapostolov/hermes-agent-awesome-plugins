"""CDP Manager core: probe, launch, stop local Chrome CDP ports.

Shared by dashboard/plugin_api.py (renderer REST) and cdp_tools.py (the
`cdp` agent tool). All mutations run on 127.0.0.1 only.
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"

DEFAULT_PORTS = [9222, 9333, 9335]
PROBE_TIMEOUT_S = 1.0

DEFAULT_CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe"
DEFAULT_PROFILE = "C:/Users/theap/AppData/Local/hermes/chrome-profile"

_lock = threading.RLock()


# ── config ────────────────────────────────────────────────────────────

def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text("utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            pass
    ports = cfg.get("ports")
    if not isinstance(ports, list) or not ports:
        ports = list(DEFAULT_PORTS)
    cfg["ports"] = [
        int(p) for p in ports
        if isinstance(p, (int, float)) and 0 < int(p) < 65536
    ] or list(DEFAULT_PORTS)
    cfg["chromePath"] = cfg.get("chromePath") or DEFAULT_CHROME
    cfg["userDataDir"] = cfg.get("userDataDir") or DEFAULT_PROFILE
    cfg["preferredPort"] = int(cfg.get("preferredPort") or 0) or None
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), "utf-8")
    os.replace(tmp, CONFIG_PATH)


def mutate_config(fn) -> dict:
    """Locked read-modify-write of config.json."""
    with _lock:
        cfg = load_config()
        fn(cfg)
        save_config(cfg)
        return cfg


# ── probing ───────────────────────────────────────────────────────────

def probe_port(port: int) -> dict:
    """One /json/version probe. Returns the same shape the JS renders."""
    t0 = time.monotonic()
    url = f"http://127.0.0.1:{int(port)}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S) as res:
            if res.status != 200:
                return {"port": int(port), "state": "dead", "reason": f"HTTP {res.status}"}
            j = json.loads(res.read().decode("utf-8", "replace"))
        return {
            "port": int(port),
            "state": "live",
            "browser": j.get("Browser") or "unknown browser",
            "pid": int(j["Process Id"]) if str(j.get("Process Id", "")).isdigit() else None,
            "ws": j.get("webSocketDebuggerUrl"),
            "ms": int((time.monotonic() - t0) * 1000),
        }
    except urllib.error.HTTPError as e:
        return {"port": int(port), "state": "dead", "reason": f"HTTP {e.code}"}
    except Exception:
        return {"port": int(port), "state": "dead", "reason": "no listener"}


def probe_all(ports: list[int] | None = None) -> list[dict]:
    cfg = load_config()
    ports = ports or cfg["ports"]
    return [probe_port(p) for p in ports]


# ── mutations ─────────────────────────────────────────────────────────

def launch(port: int, mode: str | None = None) -> dict:
    """Start Chrome with --remote-debugging-port on 127.0.0.1. DETACHED_PROCESS
    + CREATE_NO_WINDOW: no visible terminal (standing Apo rule).

    mode: 'headful' (default) or 'headless' (--headless=new). Each port gets
    its own user-data-dir (config override userDataDir + '-' + port): a
    second Chrome on an occupied profile joins the running instance instead
    of binding its debug port, so per-port dirs are required.
    """
    cfg = load_config()
    port = int(port)
    if not 0 < port < 65536:
        return {"ok": False, "error": f"invalid port {port}"}
    live = probe_port(port)
    if live["state"] == "live":
        return {"ok": True, "already": True, "port": port, "result": live}
    chrome = cfg["chromePath"]
    if not Path(chrome).exists():
        return {"ok": False, "error": f"chrome.exe not found at {chrome}"}
    headless = (mode or load_config().get("mode") or "headful") == "headless"
    flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    args = [
        chrome,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={cfg['userDataDir']}-{port}",
        "--no-first-run",
    ]
    if headless:
        args.append("--headless=new")
    # remember the mode so the supervisor auto-start uses the same one
    mutate_config(lambda c: c.update({f"mode_{port}": "headless" if headless else "headful"}))
    try:
        subprocess.Popen(
            args,
            creationflags=flags,
            cwd=str(Path(chrome).parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as e:
        return {"ok": False, "error": f"spawn failed: {e}"}
    # Chrome needs a beat before /json/version answers.
    deadline = time.monotonic() + 8.0
    result = None
    while time.monotonic() < deadline:
        time.sleep(0.4)
        result = probe_port(port)
        if result["state"] == "live":
            break
    return {
        "ok": bool(result and result["state"] == "live"),
        "port": port,
        "mode": "headless" if headless else "headful",
        "result": result,
        "error": None if result and result["state"] == "live" else "no listener after 8s",
    }


def stop(port: int) -> dict:
    """Close the CDP listener cleanly via Browser.close (kills the browser we
    own on that debug port; never touches an arbitrary pid)."""
    port = int(port)
    live = probe_port(port)
    if live["state"] != "live":
        return {"ok": True, "already": True, "port": port}
    # Browser.close over the version endpoint's WS is the full-browser close.
    # Chrome may still hold the port briefly, so allow one immediate retry.
    try:
        _browser_close_ws(live.get("ws"))
    except Exception as e:
        return {"ok": False, "port": port, "error": f"close failed: {e}"}
    deadline = time.monotonic() + 6.0
    retried = False
    while time.monotonic() < deadline:
        time.sleep(0.3)
        if probe_port(port)["state"] == "dead":
            return {"ok": True, "port": port}
        if not retried and time.monotonic() > deadline - 4.0:
            # Chrome sometimes ignores the first frame (still booting pages);
            # send Browser.close once more before giving up.
            try:
                fresh = probe_port(port)
                if fresh["state"] == "live" and fresh.get("ws"):
                    _browser_close_ws(fresh["ws"])
            except Exception:
                pass
            retried = True
    return {"ok": False, "port": port, "error": "listener still live after 6s"}


def _browser_close_ws(browser_ws: str | None) -> None:
    """Minimal WebSocket Browser.close against the CDP endpoint. Only stdlib."""
    if not browser_ws:
        raise RuntimeError("no webSocketDebuggerUrl")
    import base64
    import socket
    from urllib.parse import urlparse

    u = urlparse(browser_ws)
    host, port = u.hostname, u.port or 80
    sock = socket.create_connection((host, port), timeout=3)
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {u.path} HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(handshake.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk
    if b"101" not in resp.split(b"\r\n", 1)[0]:
        sock.close()
        raise RuntimeError(f"ws upgrade refused: {resp[:120]!r}")
    # Masked text frame: {"id":1,"method":"Browser.close"}
    payload = json.dumps({"id": 1, "method": "Browser.close"}).encode()
    mask = os.urandom(4)
    header = bytes([0x81])
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + n.to_bytes(2, "big")
    else:
        header += bytes([0x80 | 127]) + n.to_bytes(8, "big")
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    sock.sendall(header + mask + masked)
    time.sleep(0.5)
    sock.close()


def set_preferred(port: int | None) -> dict:
    """Mark port preferred (None clears). Port must be in the probe list."""
    port = int(port) if port else None
    if port is not None and port not in load_config()["ports"]:
        return {"ok": False, "error": f"port {port} is not in the probe list"}
    cfg = mutate_config(lambda c: c.update(preferredPort=port))
    return {"ok": True, "preferredPort": port, "ports": cfg["ports"]}


def update_ports(ports: list[int]) -> dict:
    clean = sorted({int(p) for p in ports if 0 < int(p) < 65536})
    if not clean:
        return {"ok": False, "error": "no valid ports"}
    cfg = mutate_config(lambda c: c.update(ports=clean))
    pref = cfg.get("preferredPort")
    if pref and pref not in clean:
        cfg = mutate_config(lambda c: c.update(preferredPort=None))
    return {"ok": True, "ports": cfg["ports"], "preferredPort": cfg.get("preferredPort")}


def resolve_port(port: int | None) -> tuple[int | None, str | None]:
    """Pick the port an action should use: explicit > preferred > sole live."""
    cfg = load_config()
    if port:
        return int(port), None
    pref = cfg.get("preferredPort")
    if pref:
        return int(pref), None
    live = [r["port"] for r in probe_all() if r["state"] == "live"]
    if len(live) == 1:
        return live[0], None
    return None, "no port given, no preferred port set, and not exactly one port is live"


# ── health + managed-port supervision ────────────────────────────────
#
# Health model (drives the statusbar chip and the dialog):
#   ok        at least one port live, all probes healthy
#   down      no port live (and nothing is wrong beyond "not running")
#   warn      a live port is degraded: probe slow, or the managed port is
#             down while others are up
#   critical  the managed port is repeatedly failing to come up / needs a
#             reboot (launch attempts exhausted)
#
# The supervisor runs as one daemon thread: every poll tick it probes all
# ports (regular health check for every port), and if the managed port is
# down it launches it; if launches keep failing it escalates to critical
# and force-reboots (stop + launch) on the next tick.

SUPERVISE_TICK_S = 2.0          # supervisor loop granularity
SUPERVISE_MAX_BACKOFF_S = 60.0  # cap for the retry backoff
SLOW_PROBE_MS = 1500            # live but slower than this = warn
CRITICAL_AFTER = 3              # consecutive failed launches -> critical
HEALTH_CACHE_TTL_S = 2.0

_health_cache: dict = {"at": 0.0, "payload": None}
_supervise_started = False


def _classify(results: list[dict], managed: int | None, fail_streak: int) -> tuple[str, str | None]:
    """Map probe results to (health, reason)."""
    by_port = {r["port"]: r for r in results}
    any_live = any(r["state"] == "live" for r in results)
    managed_res = by_port.get(managed) if managed else None
    managed_down = managed is not None and (managed_res is None or managed_res["state"] != "live")

    if fail_streak >= CRITICAL_AFTER:
        return "critical", f"managed port {managed} failed {fail_streak}x, needs reboot"
    if not any_live:
        return "down", None
    if managed_down:
        return "warn", f"managed port {managed} is down"
    slow = [r["port"] for r in results if r["state"] == "live" and (r.get("ms") or 0) > SLOW_PROBE_MS]
    if slow:
        return "warn", f"slow probe: {', '.join(map(str, slow))}"
    if managed is None and not any_live:
        return "down", None
    return "ok", None


def health() -> dict:
    """Cached health snapshot for the statusbar chip. Probes only when the
    cache is older than HEALTH_CACHE_TTL_S."""
    now = time.monotonic()
    if _health_cache["payload"] is not None and now - _health_cache["at"] < HEALTH_CACHE_TTL_S:
        return _health_cache["payload"]
    cfg = load_config()
    results = probe_all()
    payload = {
        "health": "down",
        "reason": None,
        "results": results,
        "preferredPort": cfg.get("preferredPort"),
        "ports": cfg["ports"],
        "supervisor": {
            "failStreak": _supervisor_state.get("fail_streak", 0),
            "lastAction": _supervisor_state.get("last_action"),
        },
    }
    payload["health"], payload["reason"] = _classify(
        results, cfg.get("preferredPort"), _supervisor_state.get("fail_streak", 0)
    )
    _health_cache["at"] = now
    _health_cache["payload"] = payload
    return payload


def invalidate_health() -> None:
    """Drop the cached snapshot so the next health() re-probes."""
    _health_cache["at"] = 0.0
    _health_cache["payload"] = None


def _supervise_loop() -> None:
    """One daemon thread: keeps health fresh, starts the managed port when
    down, force-reboots it when launches keep failing."""
    while True:
        try:
            cfg = load_config()
            managed = cfg.get("preferredPort")
            h = health()  # refreshes the cache (respects its own TTL)
            if managed:
                by_port = {r["port"]: r for r in h["results"]}
                managed_res = by_port.get(managed)
                is_up = managed_res is not None and managed_res["state"] == "live"
                st = _supervisor_state
                if is_up:
                    st["fail_streak"] = 0
                    st["last_action"] = None
                else:
                    # managed port is down: start it, or reboot after streak
                    if st["fail_streak"] >= CRITICAL_AFTER:
                        # critical: stop anything on the port, then launch
                        try:
                            stop(managed)
                        except Exception:
                            pass
                        st["last_action"] = f"reboot {managed}"
                    else:
                        st["last_action"] = f"start {managed}"
                    out = launch(managed, mode=load_config().get(f"mode_{managed}"))
                    if out.get("ok") and not out.get("already"):
                        st["fail_streak"] = 0
                        st["last_action"] = f"started {managed}"
                    elif out.get("already"):
                        pass  # probe race; next tick re-classifies
                    else:
                        st["fail_streak"] = st.get("fail_streak", 0) + 1
        except Exception:
            pass
        time.sleep(SUPERVISE_TICK_S)


_supervisor_state: dict = {"fail_streak": 0, "last_action": None}


def ensure_supervisor() -> None:
    """Start the supervision thread once per process."""
    global _supervise_started
    if _supervise_started:
        return
    t = threading.Thread(target=_supervise_loop, name="cdp-manager-supervisor", daemon=True)
    t.start()
    _supervise_started = True
