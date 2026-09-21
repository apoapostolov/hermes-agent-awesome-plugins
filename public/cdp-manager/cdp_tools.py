"""Handler for the `cdp` agent tool. Thin wrapper over cdp_core."""

from __future__ import annotations

import json

from . import cdp_core


def cdp(args: dict, **kwargs) -> str:
    """Dispatch the cdp tool. Every action returns a JSON dict."""
    action = (args.get("action") or "status").strip().lower()
    port = args.get("port")
    port = int(port) if port not in (None, "", 0) else None

    try:
        if action in ("status", "recheck"):
            results = cdp_core.probe_all()
            cfg = cdp_core.load_config()
            h = cdp_core.health()
            return json.dumps({
                "ok": True,
                "action": action,
                "ports": cfg["ports"],
                "preferredPort": cfg.get("preferredPort"),
                "health": h["health"],
                "reason": h.get("reason"),
                "supervisor": h.get("supervisor"),
                "modes": {str(p): cfg.get(f"mode_{p}") or "headful" for p in cfg["ports"]},
                "selections": {str(p): cdp_core.resolve_profile(p, None, cfg) for p in cfg["ports"]},
                "results": results,
                "live": [r["port"] for r in results if r["state"] == "live"],
            })

        if action == "profiles":
            return json.dumps({
                "ok": True,
                "action": "profiles",
                **cdp_core.profiles_overview(),
            })

        if action == "restart":
            target, err = cdp_core.resolve_port(port)
            if err:
                return json.dumps({"ok": False, "error": err, "action": action})
            out = cdp_core.restart(target, mode=args.get("mode"), profile=args.get("profile"))
            out["action"] = action
            out["port"] = target
            return json.dumps(out)

        if action == "unwedge":
            target, err = cdp_core.resolve_port(port)
            if err:
                return json.dumps({"ok": False, "error": err, "action": action})
            out = cdp_core.unwedge(target, mode=args.get("mode"), profile=args.get("profile"))
            out["action"] = action
            out["port"] = target
            return json.dumps(out)

        if action == "wedged":
            target, err = cdp_core.resolve_port(port)
            if err:
                return json.dumps({"ok": False, "error": err, "action": action})
            w = cdp_core.wedged(target)
            return json.dumps({"ok": True, "action": action, "port": target, **w})

        if action == "prefer":
            target = port if port else None
            out = cdp_core.set_preferred(target)
            return json.dumps(out)

        if action in ("launch", "stop"):
            target, err = cdp_core.resolve_port(port)
            if err:
                return json.dumps({"ok": False, "error": err, "action": action})
            mode = args.get("mode")  # 'headful' | 'headless' (launch only)
            profile = args.get("profile")  # 'hermes' | 'guest' | 'chrome:<dir>' (launch only)
            if action == "launch":
                out = cdp_core.launch(target, mode=mode, profile=profile)
            else:
                out = cdp_core.stop(target)
            out["action"] = action
            out["port"] = target
            return json.dumps(out)

        return json.dumps({"ok": False, "error": f"unknown action {action!r}"})
    except Exception as e:
        return json.dumps({"ok": False, "error": str(e), "action": action})
