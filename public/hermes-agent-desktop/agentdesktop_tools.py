"""Tool handlers: observe and operate desktop apps through the accessibility tree.

Every handler returns the agent-desktop JSON envelope as text. Refs are
qualified (``@<snapshot_id>:eN``) and valid for one snapshot, so the loop is
observe, act on a ref, observe again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from . import agentdesktop_cli as cli
from . import agentdesktop_config as settings
from . import agentdesktop_install as install
from . import agentdesktop_schemas as schemas

# the tools this plugin registers: a hook sees every tool in the process, so the
# auto-install check below must not fire for someone else's call
_OWN_TOOLS = frozenset(schemas.ALL)

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
    parsed_apps = json.loads(apps_raw)
    parsed_windows = json.loads(windows_raw)
    # a failed half must surface as a failure: an empty list under ok:true reads
    # as "nothing is running", which is a wrong answer, not a missing one
    if not parsed_apps.get("ok"):
        return apps_raw
    if not parsed_windows.get("ok"):
        return windows_raw
    apps_payload = parsed_apps.get("data") or {}
    apps = apps_payload.get("apps", []) if isinstance(apps_payload, dict) else apps_payload
    return json.dumps(
        {
            "ok": True,
            "command": "list-apps+list-windows",
            "data": {"apps": apps, "windows": parsed_windows.get("data") or []},
        },
        ensure_ascii=False,
    )[: _max_chars(args)]


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


# batch commands that start or stop a program: the same reach as desktop_window launch/close
_BATCH_GATED = {"launch", "close-app"}


def _approval_message(tool_name: str, args: Dict[str, Any]) -> Any:
    """The prompt text for a call that starts, stops or installs a program, else ``None``."""
    action = str(args.get("action") or "").strip().lower()
    if tool_name == "desktop_window" and action in {"launch", "close"}:
        app_args = " ".join(str(a) for a in args.get("app_args") or [])
        return f"desktop_window {action} {args.get('app')!r}" + (
            f" with arguments {app_args!r}" if app_args else ""
        )
    if tool_name == "desktop_install" and action == "install":
        return f"desktop_install: download and run agent-desktop {settings.get('version')} from GitHub"
    if tool_name == "desktop_batch" and any(
        isinstance(c, dict) and str(c.get("command") or "").strip().lower() in _BATCH_GATED
        for c in args.get("commands") or []
    ):
        return "desktop_batch starts or stops a program: " + json.dumps(
            args.get("commands"), ensure_ascii=False
        )[:400]
    return None


def approval_gate(tool_name: str = "", args: Any = None, **kwargs: Any) -> Any:
    """pre_tool_call: send program launches and binary installs to Hermes's approval prompt.

    These are the calls that run a program the user did not start: launch takes
    any executable and arguments, install downloads and runs a binary, and with
    ``auto_install`` on, any tool call on a missing binary downloads one first.
    """
    args = args if isinstance(args, dict) else {}
    message = _approval_message(tool_name, args) or _auto_install_message(tool_name)
    return {"action": "approve", "message": message} if message else None


def _auto_install_message(tool_name: str) -> Any:
    """A read-only call still fetches and runs a binary when auto_install fills a gap."""
    if tool_name not in _OWN_TOOLS or not settings.as_bool("auto_install"):
        return None
    if cli.resolve_binary():
        return None
    return (
        f"{tool_name} will first download and run agent-desktop {settings.get('version')} "
        "from GitHub: auto_install is on and no binary is installed"
    )


def desktop_install(args: Dict[str, Any], **kwargs: Any) -> str:
    args = _args(args)
    action = str(args.get("action") or "status").strip().lower()
    if action == "status":
        payload = install.status()
        payload["resolved_binary"] = cli.resolve_binary()
        return json.dumps(payload, ensure_ascii=False)
    if action == "verify":
        # probe the binary the tools would actually use, not only the plugin's
        # own copy: a host that already had agent-desktop on PATH must verify true
        resolved = cli.resolve_binary()
        return json.dumps(install.verify(Path(resolved) if resolved else None), ensure_ascii=False)
    if action == "install":
        outcome = install.install(force=bool(args.get("force")))
        return json.dumps(outcome, ensure_ascii=False)
    return _error("INVALID_ARGS", f"unknown install action {action!r}", allowed=["status", "install", "verify"])
