"""Regression tests for the CDP Manager core. Standard library only.

    python tests_cdp_core.py

Covers the four defects fixed in 1.0.3: an IPv6-only DevTools endpoint read as
dead, a launch that ignored the remembered mode, a launch that spawned a second
Chrome onto an occupied profile directory, and the `profile` request-body key
that the host's native-HTTP guard refuses with 403.
"""

import json
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import cdp_core  # noqa: E402

FAILS = []


def clear_live_host():
    """The address-family cache arrived in 1.0.3; absent on older cores."""
    host_map = getattr(cdp_core, "_live_host", None)
    if host_map:
        host_map.clear()


def check(name, ok, detail=""):
    print(("PASS  " if ok else "FAIL  ") + name + (("  [" + str(detail) + "]") if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


# ── a DevTools endpoint that answers on ::1 only ─────────────────────
class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        port = self.server.server_address[1]
        body = json.dumps({
            "Browser": "Chrome/test",
            "webSocketDebuggerUrl": "ws://[::1]:%d/devtools/browser/x" % port,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class _V6Server(HTTPServer):
    address_family = socket.AF_INET6
    daemon_threads = True


def start_v6_only():
    srv = _V6Server(("::1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


# 1. an IPv6-only endpoint must read live ---------------------------------
srv, v6_port = start_v6_only()
clear_live_host()
res = cdp_core.probe_port(v6_port)
check("probe finds a listener on [::1] only", res["state"] == "live" and res.get("host") == "[::1]", res)
srv.shutdown()
srv.server_close()
clear_live_host()

# 2. and reads dead once it is gone --------------------------------------
time.sleep(0.2)
check("probe reports the port dead after that listener stops",
      cdp_core.probe_port(v6_port)["state"] == "dead")

# ── a scratch config so nothing here touches the real one ─────────────
tmp = Path(tempfile.mkdtemp(prefix="cdp-test-"))
plug = tmp / "plugin"
plug.mkdir()
cfg_path = plug / "config.json"
cfg_path.write_text(json.dumps({
    "ports": [9401, 9402],
    "preferredPort": 9401,
    "chromePath": sys.executable,
    "userDataDir": str(tmp / "udd"),
    "mode_9401": "headless",
    "profile_9401": "hermes",
}), encoding="utf-8")
cdp_core.CONFIG_PATH = cfg_path
clear_live_host()

saved = (cdp_core.probe_port, cdp_core.profile_holder, cdp_core.wedged)
spawned = []


class _FakePopen:
    def __init__(self, args, **kw):
        spawned.append(args)


# 3. a launch with no mode reuses mode_<port> ---------------------------
calls = {"n": 0}


def probe_then_live(port):
    calls["n"] += 1
    if calls["n"] == 1:
        return {"port": int(port), "state": "dead", "reason": "no listener"}
    return {"port": int(port), "state": "live", "browser": "Chrome/test",
            "pid": None, "ws": None, "host": "127.0.0.1", "ms": 1}


cdp_core.probe_port = probe_then_live
cdp_core.wedged = lambda port: {"wedged": False, "targets": 1}
cdp_core.profile_holder = lambda d: None
cdp_core.subprocess.Popen = _FakePopen
out = cdp_core.launch(9401)
args = spawned[-1] if spawned else []
check("launch without a mode reuses the remembered mode",
      out.get("mode") == "headless" and "--headless=new" in args, (out.get("mode"), args))
check("the remembered mode survives that launch",
      cdp_core.load_config().get("mode_9401") == "headless")

# 4. a launch refuses when a Chrome already holds the profile dir -------
spawned.clear()
calls["n"] = 0  # the first probe of this launch must read dead
cdp_core.profile_holder = lambda d: 424242
out = cdp_core.launch(9402)
check("launch refuses by pid when another Chrome holds the profile dir",
      out.get("ok") is False and "424242" in (out.get("error") or ""), out)
check("that refusal spawns nothing", spawned == [])

# 5. Browser.close addresses an IPv6 endpoint with a bracketed Host -----
received = {}


def fake_cdp_ws():
    srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    srv.bind(("::1", 0))
    srv.listen(1)
    received["port"] = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
        received["request"] = data
        conn.close()

    threading.Thread(target=serve, daemon=True).start()
    return srv


srv = fake_cdp_ws()
try:
    cdp_core._browser_close_ws("ws://[::1]:%d/devtools/browser/x" % received["port"])
except Exception:
    pass
finally:
    srv.close()
time.sleep(0.2)
req = received.get("request", b"")
expect = ("Host: [::1]:%d" % received["port"]).encode()
check("Browser.close sends a bracketed IPv6 Host header", expect in req, req[:160])

cdp_core.probe_port, cdp_core.profile_holder, cdp_core.wedged = saved

# 6. the REST body never carries a bare `profile` key ------------------
# The host's native-HTTP guard reads body.profile as a Hermes profile
# selector and answers 403 profile_scope_mismatch, so the desktop half must
# post `browserProfile` and the backend must accept that name.
js = (HERE / "desktop" / "plugin.js").read_text(encoding="utf-8", errors="replace")
api = (HERE / "dashboard" / "plugin_api.py").read_text(encoding="utf-8", errors="replace")
posts_bare = [ln for ln in js.splitlines()
              if "api(" in ln and ("{ profile }" in ln or "profile: " in ln and "browserProfile" not in ln)]
check("desktop half posts browserProfile, never profile", not posts_bare, posts_bare[:2])
check("backend accepts browserProfile on launch and profile routes",
      api.count("browserProfile: str | None = None") == 2, api.count("browserProfile: str | None = None"))

print()
if FAILS:
    print("%d check(s) failed: %s" % (len(FAILS), ", ".join(FAILS)))
    sys.exit(1)
print("all checks passed")
