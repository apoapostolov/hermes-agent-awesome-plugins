"""Skip a hung Hermes tool call without aborting the turn.

Port of pi-break for this agent process:

- ``/break`` kills the newest in-flight spawned child tree and keeps the turn
- ``/break --id {id}`` kills that specific spawn
- ``/break {message}`` same, then that text rides in the broken tool result
  (ahead of any later /steer drain)
- ``/again`` same kill, tells the model to reissue that exact call once
- ``/again {hint}`` same, with a tweak
- ``/again`` is refused after two uses of the same (name, args) this session

Desktop ``slash.exec`` already runs plugin commands while a turn is live.
Classic CLI queues every slash until the turn ends, so this plugin patches
``HermesCLI._should_handle_steer_command_inline`` to also dispatch /break
and /again on the UI thread. Gateway messaging still rejects unknown
busy-slash commands; use desktop or wait.

In-process hangs (web_search, a silent stream) get marked. If they never
return, Escape / interrupt is still the way out.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

PID_POLL_MS = 0.2
PID_POLL_FOR_S = 2.5
SPAWN_TOOLS = frozenset({"terminal", "process"})
SALVAGE_MAX = 8192
MAX_AGAIN = 2

_lock = threading.Lock()
_inflight: dict[str, dict[str, Any]] = {}
_broken: dict[str, dict[str, Any]] = {}
_again_by_fp: dict[str, int] = {}
_cli_patched = False
_popen_patched = False
_orig_popen = subprocess.Popen


def _attach_spawned_pid(pid: int) -> None:
    if not pid or pid <= 1:
        return
    with _lock:
        target = None
        for item in _inflight.values():
            if target is None or item["started_at"] > target["started_at"]:
                target = item
        if not target:
            return
        seen: set[int] = target["seen"]
        pids: list[int] = target["pids"]
        if pid in seen or pid == os.getpid():
            return
        pids.append(pid)
        seen.add(pid)


class _TrackingPopen(_orig_popen):  # type: ignore[valid-type,misc]
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        try:
            _attach_spawned_pid(int(getattr(self, "pid", 0) or 0))
        except Exception:
            pass


def _install_popen_hook() -> None:
    global _popen_patched
    if _popen_patched:
        return
    subprocess.Popen = _TrackingPopen  # type: ignore[misc,assignment]
    _popen_patched = True


def _fmt_duration(ms: float) -> str:
    s = max(0, int(ms / 1000))
    if s < 60:
        return f"{s}s"
    m, rem = divmod(s, 60)
    if m < 60:
        return f"{m}m{rem:02d}s" if rem else f"{m}m"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _format_args(args: Any) -> str:
    try:
        return json.dumps(args, indent=2, default=str)
    except Exception:
        return str(args)


def _fingerprint(name: str, args: Any) -> str:
    try:
        blob = json.dumps(args, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:
        blob = str(args)
    return f"{name}:{blob}"


def _salvage(prior: str) -> str:
    text = (prior or "").strip()
    if len(text) <= SALVAGE_MAX:
        return text
    return text[-SALVAGE_MAX:]


def _content_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, str):
        text = result.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except Exception:
                return text
            if isinstance(parsed, dict):
                for key in ("output", "error", "message", "content"):
                    val = parsed.get(key)
                    if isinstance(val, str) and val.strip():
                        return val.strip()
                return text
        return text
    return str(result).strip()


def _win_parent_map() -> dict[int, list[int]]:
    try:
        import ctypes
        from ctypes import wintypes
    except Exception:
        return {}

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(wintypes.ULONG)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    TH32CS_SNAPPROCESS = 0x00000002
    kernel32 = ctypes.windll.kernel32
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (-1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return {}
    by_parent: dict[int, list[int]] = {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snap, ctypes.byref(entry)):
            return {}
        while True:
            parent = int(entry.th32ParentProcessID)
            child = int(entry.th32ProcessID)
            if child > 1 and child != parent:
                by_parent.setdefault(parent, []).append(child)
            if not kernel32.Process32NextW(snap, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snap)
    return by_parent


def _posix_direct_children(pid: int) -> list[int]:
    ids: set[int] = set()
    try:
        task_dir = f"/proc/{pid}/task"
        for tid in os.listdir(task_dir):
            try:
                raw = open(f"{task_dir}/{tid}/children", encoding="utf-8").read().strip()
            except OSError:
                continue
            if not raw:
                continue
            for tok in raw.split():
                n = int(tok) if tok.isdigit() else 0
                if n > 1:
                    ids.add(n)
    except OSError:
        pass
    return list(ids)


def _descendants(pid: int) -> list[int]:
    """Full descendant tree. Direct-only misses bash -c sleep grandchildren."""
    out: list[int] = []
    seen: set[int] = set()
    if sys.platform == "win32":
        by_parent = _win_parent_map()
        stack = list(by_parent.get(pid, []))
        while stack:
            child = stack.pop()
            if child in seen or child == pid:
                continue
            seen.add(child)
            out.append(child)
            stack.extend(by_parent.get(child, []))
        return out
    stack = _posix_direct_children(pid)
    while stack:
        child = stack.pop()
        if child in seen or child == pid:
            continue
        seen.add(child)
        out.append(child)
        stack.extend(_posix_direct_children(child))
    return out


def _children_of(pid: int) -> list[int]:
    return _descendants(pid)


def _kill_tree(pid: int) -> None:
    if pid in {os.getpid(), os.getppid(), 0, 1}:
        return
    if sys.platform == "win32":
        try:
            subprocess.Popen(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) or 0x08000000,
            )
        except Exception:
            pass
        return
    for child in _children_of(pid):
        _kill_tree(child)
    try:
        os.kill(-pid, 9)
    except OSError:
        pass
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def _claimed_pids() -> set[int]:
    claimed: set[int] = set()
    for item in _inflight.values():
        claimed.update(item.get("pids") or [])
    return claimed


def _newest() -> Optional[dict[str, Any]]:
    pick = None
    for item in _inflight.values():
        if pick is None or item["started_at"] > pick["started_at"]:
            pick = item
    return pick


def _attach_pids(item: dict[str, Any]) -> None:
    claimed = _claimed_pids()
    seen: set[int] = item["seen"]
    pids: list[int] = item["pids"]
    for pid in _children_of(os.getpid()):
        if pid in seen or pid in claimed:
            continue
        pids.append(pid)
        seen.add(pid)


def _pid_alive(pid: int) -> bool:
    if pid <= 1 or pid in {os.getpid(), os.getppid()}:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            try:
                code = wintypes.DWORD()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return int(code.value) == 259
                return True
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _watch_pids(item: dict[str, Any]) -> None:
    def _tick() -> None:
        with _lock:
            live = _inflight.get(item["id"])
            if live is None:
                item["poll"] = None
                return
            _attach_pids(live)
        timer = threading.Timer(PID_POLL_MS, _tick)
        timer.daemon = True
        item["poll"] = timer
        timer.start()

    timer = threading.Timer(PID_POLL_MS, _tick)
    timer.daemon = True
    item["poll"] = timer
    timer.start()


def _drop(tool_call_id: str) -> None:
    item = _inflight.pop(tool_call_id, None)
    if not item:
        return
    poll = item.get("poll")
    if poll is not None:
        try:
            poll.cancel()
        except Exception:
            pass


def _rewrite(mark: dict[str, Any], prior: str) -> str:
    waited = _fmt_duration((time.monotonic() - mark["started_at"]) * 1000)
    name = mark["name"]
    if mark["again"]:
        lines = [
            f"Broken by /again after {waited} ({name}).",
            "Reissue this exact call once. Do not loop. The previous attempt was killed; it may have left partial work.",
            "",
            f"Call: {name}",
            "Args:",
            _format_args(mark.get("args")),
        ]
    else:
        lines = [
            f"Broken by /break after {waited} ({name}).",
            "The call was stopped so the turn can continue. Do not retry the same call.",
        ]
    hint = mark.get("hint")
    if hint:
        lines.extend(["", "Tweak:" if mark["again"] else "Steer (before any other queued steer):", hint])
    if prior:
        chunk = _salvage(prior)
        if chunk:
            lines.extend(["", "Partial output (last 8KB):", chunk])
    return "\n".join(lines)


def _registry_sessions(started_wall: float) -> list[Any]:
    try:
        from tools.process_registry import process_registry
    except Exception:
        return []
    try:
        running = list(getattr(process_registry, "_running", {}).values())
    except Exception:
        return []
    out = []
    for session in running:
        started = float(getattr(session, "started_at", 0) or 0)
        if started < started_wall - 1:
            continue
        if getattr(session, "exited", False):
            continue
        out.append(session)
    return out


def _killable(target: dict[str, Any]) -> bool:
    tracked = list(target.get("pids") or [])
    if any(_pid_alive(pid) for pid in tracked):
        return True
    if any(_pid_alive(pid) for pid in _kill_list_for(target)):
        return True
    return bool(_registry_sessions(float(target.get("started_wall") or 0)))


def _newest_killable() -> Optional[dict[str, Any]]:
    pick = None
    for item in _inflight.values():
        if not _killable(item):
            continue
        if pick is None or item["started_at"] > pick["started_at"]:
            pick = item
    return pick


def _newest_spawn() -> Optional[dict[str, Any]]:
    pick = None
    for item in _inflight.values():
        if item.get("name") not in SPAWN_TOOLS:
            continue
        if pick is None or item["started_at"] > pick["started_at"]:
            pick = item
    return pick


def _newest_visible() -> Optional[dict[str, Any]]:
    return _newest_killable() or _newest_spawn()


def _visible_items() -> list[dict[str, Any]]:
    items = [
        item
        for item in _inflight.values()
        if _killable(item) or item.get("name") in SPAWN_TOOLS
    ]
    items.sort(key=lambda item: float(item.get("started_at") or 0), reverse=True)
    return items


def _kill_list_for(target: dict[str, Any]) -> list[int]:
    now = set(_descendants(os.getpid()))
    later_new: set[int] = set()
    for item in _inflight.values():
        if item["started_at"] > target["started_at"]:
            later_new |= now - set(item.get("seen") or [])
    return sorted((now - set(target.get("seen") or [])) - later_new)


def _kill_registry_since(started_wall: float) -> int:
    n = 0
    for session in _registry_sessions(started_wall):
        sid = getattr(session, "id", None)
        pid = getattr(session, "pid", None)
        if pid:
            _kill_tree(int(pid))
        if not sid:
            continue
        try:
            from tools.process_registry import process_registry

            process_registry.kill_process(sid, source="tool-break")
            n += 1
        except Exception:
            pass
    return n


def _break_oldest(*, hint: Optional[str], again: bool, tool_call_id: Optional[str] = None) -> str:
    with _lock:
        target = _inflight.get(tool_call_id) if tool_call_id else _newest_visible()
        if not target:
            return "Nothing in flight"
        if not _killable(target) and target.get("name") not in SPAWN_TOOLS:
            return "Nothing in flight"
        fp = _fingerprint(str(target.get("name") or ""), target.get("args"))
        used = int(_again_by_fp.get(fp, 0))
        if again and used >= MAX_AGAIN:
            return "Again used twice on this call. Break instead."
        if again:
            _again_by_fp[fp] = used + 1
        mark = {
            "name": target["name"],
            "args": target.get("args"),
            "started_at": target["started_at"],
            "hint": hint,
            "again": again,
        }
        _broken[target["id"]] = mark
        kill_list = [pid for pid in _kill_list_for(target) if _pid_alive(pid)]
        for pid in target.get("pids") or []:
            if _pid_alive(pid) and pid not in kill_list:
                kill_list.append(pid)
        started_wall = float(target.get("started_wall") or 0)
    for pid in kill_list:
        _kill_tree(pid)
    _kill_registry_since(started_wall)
    waited = _fmt_duration((time.monotonic() - mark["started_at"]) * 1000)
    extra = ""
    if again:
        extra = " · again + hint" if hint else " · again"
    elif hint:
        extra = " · hint queued in the tool result"
    return f"Broke {target['name']} {waited}{extra}"


def _parse_args(raw_args: str) -> tuple[Optional[str], Optional[str]]:
    text = (raw_args or "").strip()
    if not text:
        return None, None
    if text.startswith("--id "):
        rest = text[5:].strip()
        tool_id, _, hint = rest.partition(" ")
        return tool_id or None, hint.strip() or None
    return None, text


def _on_pre_tool_call(**kwargs: Any) -> None:
    tool_call_id = str(kwargs.get("tool_call_id") or "") or f"{kwargs.get('tool_name')}-{time.monotonic()}"
    name = str(kwargs.get("tool_name") or "tool")
    item = {
        "id": tool_call_id,
        "name": name,
        "args": kwargs.get("args"),
        "started_at": time.monotonic(),
        "started_wall": time.time(),
        "pids": [],
        "seen": set(_descendants(os.getpid())),
        "poll": None,
        "session_id": str(kwargs.get("session_id") or ""),
    }
    with _lock:
        _inflight[tool_call_id] = item
    _watch_pids(item)


def _on_post_tool_call(**kwargs: Any) -> None:
    tool_call_id = str(kwargs.get("tool_call_id") or "")
    if not tool_call_id:
        return
    with _lock:
        _drop(tool_call_id)


def _on_transform_tool_result(**kwargs: Any) -> Optional[str]:
    tool_call_id = str(kwargs.get("tool_call_id") or "")
    with _lock:
        mark = _broken.pop(tool_call_id, None)
    if not mark:
        return None
    prior = _content_text(kwargs.get("result"))
    return _rewrite(mark, prior)


def _on_session_start(**_kwargs: Any) -> None:
    with _lock:
        for item in list(_inflight.values()):
            poll = item.get("poll")
            if poll is not None:
                try:
                    poll.cancel()
                except Exception:
                    pass
        _inflight.clear()
        _broken.clear()
        _again_by_fp.clear()


def _on_session_end(**kwargs: Any) -> None:
    _on_session_start(**kwargs)


def _handle_break(raw_args: str) -> str:
    tool_id, hint = _parse_args(raw_args)
    with _lock:
        empty = not _inflight
    if empty:
        if hint:
            return (
                "Nothing in flight. Hermes plugin commands cannot start a turn. "
                f"Send this as a normal message:\n{hint}"
            )
        return "Nothing in flight"
    return _break_oldest(hint=hint, again=False, tool_call_id=tool_id)


def _handle_again(raw_args: str) -> str:
    tool_id, hint = _parse_args(raw_args)
    with _lock:
        empty = not _inflight
    if empty:
        return "Nothing in flight to reissue"
    return _break_oldest(hint=hint, again=True, tool_call_id=tool_id)


def _tool_label(item: dict[str, Any]) -> str:
    name = str(item.get("name") or "tool")
    args = item.get("args")
    extra = ""
    if isinstance(args, dict):
        extra = str(args.get("command") or args.get("cmd") or args.get("query") or "").strip()
    elif isinstance(args, str):
        extra = args.strip()
    extra = " ".join(extra.split())
    if extra:
        extra = extra[:48]
        return f"{name} {extra}"
    return name


def _tool_status(item: dict[str, Any]) -> dict[str, Any]:
    fp = _fingerprint(str(item.get("name") or ""), item.get("args"))
    again_count = int(_again_by_fp.get(fp, 0))
    killable = _killable(item) or item.get("name") in SPAWN_TOOLS
    return {
        "id": item["id"],
        "name": item["name"],
        "label": _tool_label(item),
        "killable": bool(killable),
        "pids": len([pid for pid in _kill_list_for(item) if _pid_alive(pid)]),
        "started_wall": float(item.get("started_wall") or 0),
        "elapsed_ms": int((time.monotonic() - item["started_at"]) * 1000),
        "again_count": again_count,
        "again_disabled": again_count >= MAX_AGAIN,
    }


def _status_payload() -> dict[str, Any]:
    with _lock:
        tools = [_tool_status(item) for item in _visible_items()]
        if not tools:
            return {"inflight": False, "killable": False, "tools": []}
        target = tools[0]
        return {
            "inflight": True,
            "killable": bool(target.get("killable")),
            "pids": target.get("pids") or 0,
            "id": target["id"],
            "name": target["name"],
            "label": target["label"],
            "started_wall": target["started_wall"],
            "elapsed_ms": target["elapsed_ms"],
            "again_count": target["again_count"],
            "again_disabled": target["again_disabled"],
            "tools": tools,
        }


def _handle_status(_raw_args: str) -> str:
    return json.dumps(_status_payload(), separators=(",", ":"))


def _install_cli_busy_dispatch() -> None:
    """Make classic CLI dispatch /break and /again while a turn is running.

    Desktop slash.exec already does this. CLI otherwise queues every slash
    behind chat(), which is exactly the hang we are trying to cut.
    """
    global _cli_patched
    if _cli_patched:
        return
    try:
        import cli as cli_mod
    except Exception:
        return
    cls = getattr(cli_mod, "HermesCLI", None)
    orig = getattr(cls, "_should_handle_steer_command_inline", None)
    if cls is None or orig is None:
        return

    def _wrapped(self, text, has_images=False):
        try:
            if orig(self, text, has_images=has_images):
                return True
        except TypeError:
            if orig(self, text):
                return True
        if has_images or not text:
            return False
        if not getattr(self, "_agent_running", False):
            return False
        base = text.split(None, 1)[0].lower().lstrip("/")
        return base in {"break", "again"}

    cls._should_handle_steer_command_inline = _wrapped
    _cli_patched = True


def register(ctx: Any) -> None:
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("transform_tool_result", _on_transform_tool_result)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_command(
        "break",
        handler=_handle_break,
        description="Skip the stalled tool call. /break {message} steers first after the break.",
        args_hint="[message]",
    )
    ctx.register_command(
        "again",
        handler=_handle_again,
        description="Skip the stalled tool call and reissue it once. /again {hint} tweaks the retry.",
        args_hint="[hint]",
    )
    ctx.register_command(
        "break-status",
        handler=_handle_status,
        description="JSON: newest in-flight spawn plus the full killable list.",
    )
    _install_cli_busy_dispatch()
    _install_popen_hook()
