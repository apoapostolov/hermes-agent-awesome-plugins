"""Tool handlers: observe and operate desktop apps through the accessibility tree.

Every handler returns the agent-desktop JSON envelope as text. Refs are
qualified (``@<snapshot_id>:eN``) and valid for one snapshot, so the loop is
observe, act on a ref, observe again.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

from . import agentdesktop_cli as cli
from . import agentdesktop_install as install

# commands that take a ref and nothing else
_REF_ONLY = {
    "click": "click",
    "double-click": "double-click",
    "triple-click": "triple-click",
    "right-click": "right-click",
    "focus": "focus",
    "clear": "clear",
    "toggle": "toggle",
    "check": "check",
    "uncheck": "uncheck",
    "expand": "expand",
    "collapse": "collapse",
    "scroll-to": "scroll-to",
}

# commands that take a ref and one value
_REF_VALUE = {
    "set-value": "set-value",
    "select": "select",
}

_REF_ACTIONS = sorted(set(_REF_ONLY) | set(_REF_VALUE) | {"scroll", "hover", "press"})

_WINDOW_ACTIONS = sorted(
    {"launch", "close", "focus", "resize", "move", "minimize", "maximize", "restore"}
)

_MAX_OUTPUT = 80000


def _args(raw: Any) -> Dict[str, Any]:
    return raw if isinstance(raw, dict) else {}


def _error(code: str, message: str, **extra: Any) -> str:
    payload: Dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    payload["error"].update(extra)
    return json.dumps(payload, ensure_ascii=False)


def _max_chars(args: Dict[str, Any]) -> int:
    try:
        value = int(args.get("max_chars") or _MAX_OUTPUT)
    except (TypeError, ValueError):
        value = _MAX_OUTPUT
    return max(2000, min(value, 200000))


def _timeout(args: Dict[str, Any], default: float = cli.DEFAULT_TIMEOUT) -> float:
    try:
        value = float(args.get("timeout_ms") or 0) / 1000.0
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def desktop_status(args: Dict[str, Any], **kwargs: Any) -> str:
    return cli.run("status", timeout=20.0, max_chars=8000)


def desktop_apps(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    app = args.get("app")
    include_windows = bool(args.get("include_windows"))
    if not include_windows and not app:
        return cli.run("list-apps", timeout=20.0, max_chars=_max_chars(args))

    apps_raw = cli.run("list-apps", timeout=20.0, max_chars=_max_chars(args))
    windows_raw = cli.run("list-windows", cli.flags(app=app), timeout=20.0, max_chars=_max_chars(args))
    try:
        apps = json.loads(apps_raw).get("data") or []
        windows = json.loads(windows_raw).get("data") or []
    except json.JSONDecodeError:
        return apps_raw if app is None else windows_raw
    return json.dumps({"ok": True, "command": "list-apps+list-windows", "data": {"apps": apps, "windows": windows}}, ensure_ascii=False)[: _max_chars(args)]


def desktop_snapshot(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    flags = cli.flags(
        app=args.get("app"),
        window_id=args.get("window_id"),
        surface=args.get("surface"),
        root=args.get("root"),
        max_depth=args.get("max_depth"),
        interactive_only=bool(args.get("interactive_only")),
        compact=bool(args.get("compact")),
        skeleton=bool(args.get("skeleton")),
        include_bounds=bool(args.get("include_bounds")),
        wait_for=args.get("wait_for"),
        wait_timeout=args.get("wait_timeout_ms"),
    )
    return cli.run(
        "snapshot",
        flags,
        headed=bool(args.get("headed")),
        timeout=_timeout(args),
        max_chars=_max_chars(args),
    )


def desktop_find(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    flags = cli.flags(
        app=args.get("app"),
        window_id=args.get("window_id"),
        role=args.get("role"),
        name=args.get("name"),
        value=args.get("value"),
        text=args.get("text"),
        description=args.get("description"),
        native_id=args.get("native_id"),
        limit=args.get("limit"),
        exact=bool(args.get("exact")),
    )
    return cli.run("find", flags, timeout=_timeout(args), max_chars=_max_chars(args))


def desktop_act(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    action = str(args.get("action") or "").strip().lower()
    if action not in _REF_ACTIONS:
        return _error(
            "INVALID_ARGS",
            f"unknown action {action!r}",
            allowed=_REF_ACTIONS,
        )

    headed = bool(args.get("headed"))
    timeout = _timeout(args)

    if action == "press":
        combo = args.get("keys") or args.get("combo")
        if not combo:
            return _error("INVALID_ARGS", "press needs 'keys', e.g. 'ctrl+c' or 'return'")
        flags = cli.flags(window_id=args.get("window_id"), force=bool(args.get("force")))
        return cli.run("press", flags, [str(combo)], headed=headed, timeout=timeout, max_chars=_max_chars(args))

    ref = args.get("ref")
    if not ref:
        return _error("INVALID_ARGS", f"{action} needs a 'ref' from a snapshot")

    if action == "hover":
        if not headed:
            return _error(
                "HEADED_REQUIRED",
                "hover moves the real cursor, so it needs headed=true",
                suggestion="prefer click or scroll, which are semantic; set headed=true only when physical input is intended",
            )
        return cli.run("hover", cli.flags(timeout_ms=args.get("timeout_ms")), [str(ref)], headed=True, timeout=timeout, max_chars=_max_chars(args))

    if action == "scroll":
        flags = cli.flags(
            direction=args.get("direction"),
            amount=args.get("amount"),
            timeout_ms=args.get("timeout_ms"),
        )
        return cli.run("scroll", flags, [str(ref)], headed=headed, timeout=timeout, max_chars=_max_chars(args))

    if action in _REF_VALUE:
        value = args.get("value")
        if value is None:
            return _error("INVALID_ARGS", f"{action} needs a 'value'")
        flags = cli.flags(timeout_ms=args.get("timeout_ms"))
        return cli.run(_REF_VALUE[action], flags, [str(ref), str(value)], headed=headed, timeout=timeout, max_chars=_max_chars(args))

    flags = cli.flags(timeout_ms=args.get("timeout_ms"))
    return cli.run(_REF_ONLY[action], flags, [str(ref)], headed=headed, timeout=timeout, max_chars=_max_chars(args))


def desktop_window(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    action = str(args.get("action") or "").strip().lower()
    if action not in _WINDOW_ACTIONS:
        return _error("INVALID_ARGS", f"unknown window action {action!r}", allowed=_WINDOW_ACTIONS)

    app = args.get("app")
    window_id = args.get("window_id")
    timeout = _timeout(args)

    if action == "launch":
        if not app:
            return _error("INVALID_ARGS", "launch needs 'app' (a bare System32/Windows name or an absolute path)")
        launch_args: List[str] = []
        for extra in args.get("app_args") or []:
            launch_args.extend(["--arg", str(extra)])
        flags = cli.flags(activate=bool(args.get("activate")), no_attach=bool(args.get("no_attach")))
        flags.extend(launch_args)
        return cli.run("launch", flags, [str(app)], timeout=timeout, max_chars=_max_chars(args))

    if action == "close":
        if not app:
            return _error("INVALID_ARGS", "close needs 'app'")
        return cli.run("close-app", cli.flags(force=bool(args.get("force"))), [str(app)], timeout=timeout, max_chars=_max_chars(args))

    if action == "resize":
        if not args.get("width") or not args.get("height"):
            return _error("INVALID_ARGS", "resize needs 'width' and 'height'")
        flags = cli.flags(app=app, window_id=window_id, width=args.get("width"), height=args.get("height"))
        return cli.run("resize-window", flags, timeout=timeout, max_chars=_max_chars(args))

    if action == "move":
        if args.get("x") is None or args.get("y") is None:
            return _error("INVALID_ARGS", "move needs 'x' and 'y'")
        flags = cli.flags(app=app, window_id=window_id, x=args.get("x"), y=args.get("y"))
        return cli.run("move-window", flags, timeout=timeout, max_chars=_max_chars(args))

    command = {
        "focus": "focus-window",
        "minimize": "minimize",
        "maximize": "maximize",
        "restore": "restore",
    }[action]
    flags = cli.flags(app=app, window_id=window_id)
    return cli.run(command, flags, timeout=timeout, max_chars=_max_chars(args))


def desktop_clipboard(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    action = str(args.get("action") or "get").strip().lower()
    timeout = _timeout(args)
    if action == "get":
        return cli.run("clipboard-get", timeout=timeout, max_chars=_max_chars(args))
    if action == "clear":
        return cli.run("clipboard-clear", timeout=timeout, max_chars=_max_chars(args))
    if action == "set":
        text = args.get("text")
        if text is None:
            return _error("INVALID_ARGS", "set needs 'text'")
        return cli.run("clipboard-set", [], [str(text)], timeout=timeout, max_chars=_max_chars(args))
    return _error("INVALID_ARGS", f"unknown clipboard action {action!r}", allowed=["get", "set", "clear"])


def desktop_batch(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    commands = args.get("commands")
    if not isinstance(commands, list) or not commands:
        return _error("INVALID_ARGS", "batch needs a non-empty 'commands' array of {command, args}")
    payload = json.dumps(commands, ensure_ascii=False)
    flags = cli.flags(stop_on_error=bool(args.get("stop_on_error")), timeout_ms=args.get("timeout_ms"))
    # the batch budget is the tool's own wall clock; the process must outlive it,
    # or the kill lands before the batch can report what it did
    budget = _timeout(args, 60.0)
    return cli.run("batch", flags, [payload], timeout=budget + 30.0, max_chars=_max_chars(args))


def desktop_install(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    action = str(args.get("action") or "status").strip().lower()
    if action == "status":
        return json.dumps(install.status(), ensure_ascii=False)
    if action == "verify":
        return json.dumps(install.verify(), ensure_ascii=False)
    if action == "install":
        outcome = install.install(
            version=args.get("version") or None,
            force=bool(args.get("force")),
        )
        return json.dumps(outcome, ensure_ascii=False)
    return _error("INVALID_ARGS", f"unknown install action {action!r}", allowed=["status", "install", "verify"])
