"""Tool schemas for the desktop tools.

Descriptions carry the rules a caller needs before acting: refs belong to one
snapshot, actions are headless unless ``headed`` is set, and only a
``disposition.retry`` of ``safe`` permits a repeat.
"""

from __future__ import annotations

from typing import Any, Dict

_APP = {
    "type": "string",
    "description": "Application name exactly as list-apps reports it, e.g. 'Discord.exe'.",
}

_WINDOW_ID = {
    "type": "string",
    "description": "Window id from desktop_apps/list-windows, e.g. 'w-7145470'. Use it when several windows match.",
}

_REF = {
    "type": "string",
    "description": (
        "Qualified ref from a snapshot: '@<snapshot_id>:eN'. Refs belong to that one snapshot; "
        "after any UI change take a new snapshot (STALE_REF means the ref no longer matches)."
    ),
}

_TIMEOUT_MS = {
    "type": "integer",
    "minimum": 1000,
    "maximum": 120000,
    "description": "How long the whole call may take, in milliseconds (default 30000).",
}

_MAX_CHARS = {
    "type": "integer",
    "minimum": 2000,
    "maximum": 200000,
    "description": "Cap on returned JSON characters (default 30000). A larger tree is trimmed, never silently dropped.",
}

_HEADED = {
    "type": "boolean",
    "description": (
        "Deliver through physical input instead of the accessibility API. This moves the cursor and can take "
        "focus, so it interrupts Apo's work: set it only when he asked for physical input, or when a headless "
        "action returned POLICY_DENIED and there is no semantic alternative. Default false."
    ),
}

STATUS: Dict[str, Any] = {
    "name": "desktop_status",
    "description": (
        "Check that desktop automation is usable before relying on it: the agent-desktop version, the OS, the "
        "permission state (on Windows 'accessibility: granted' and 'automation: not_required' is normal, there is "
        "no permission dialog), the state directory, and the surfaces this platform can snapshot (window, focused, "
        "menu, taskbar, system-tray, start-menu, action-center). Cheap, read-only, no UI side effects. Call it once "
        "when a desktop task starts or after an unexpected failure."
    ),
    "parameters": {"type": "object", "properties": {}},
}

APPS: Dict[str, Any] = {
    "name": "desktop_apps",
    "description": (
        "See what is running and what windows exist, before snapshotting anything. Returns the apps that own a "
        "window (name, pid) and, with include_windows or an app filter, each window's id, title, bounds, and "
        "whether it is focused, visible or minimized. A tray-only process has no window and will not appear here, "
        "and a minimized window cannot be driven until it is restored. Read-only."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "app": {**_APP, "description": _APP["description"] + " Narrows the window list to this app."},
            "include_windows": {
                "type": "boolean",
                "description": "Also return the window inventory (default false: apps only).",
            },
        },
    },
}

SNAPSHOT: Dict[str, Any] = {
    "name": "desktop_snapshot",
    "description": (
        "Read an app's real UI structure as JSON: role, accessible name, states, available actions and a ref for "
        "every element that can be acted on. This is how the desktop is seen without screenshots or pixels. Start "
        "narrow: on a dense app take a --skeleton overview (skeleton=true), then drill into one region with root. "
        "Pass surface='focused' for whatever is in front, or 'menu', 'start-menu', 'taskbar', 'system-tray', "
        "'action-center' for shell surfaces. After acting, snapshot again to verify. Headless and read-only: it "
        "does not take focus or move the cursor."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "app": _APP,
            "window_id": _WINDOW_ID,
            "surface": {
                "type": "string",
                "enum": [
                    "window",
                    "focused",
                    "menu",
                    "sheet",
                    "alert",
                    "taskbar",
                    "system-tray",
                    "system-tray-overflow",
                    "start-menu",
                    "action-center",
                ],
                "description": "Which surface to read (default 'window').",
            },
            "root": {
                "type": "string",
                "description": "Drill into one subtree: the ref of the container, from the same or an earlier snapshot.",
            },
            "max_depth": {"type": "integer", "minimum": 1, "maximum": 40, "description": "Tree depth limit (default 10)."},
            "interactive_only": {
                "type": "boolean",
                "description": "Only elements that can be acted on (default false). Use it to keep the output small.",
            },
            "compact": {
                "type": "boolean",
                "description": "Collapse single-child unnamed nodes to cut depth (default false; usually worth true).",
            },
            "skeleton": {
                "type": "boolean",
                "description": "Shallow overview with children_count on truncated containers (default false).",
            },
            "include_bounds": {"type": "boolean", "description": "Include each element's x/y/width/height."},
            "wait_for": {
                "type": "string",
                "description": "Poll until an element matching a 'role:text' selector appears, then return the snapshot.",
            },
            "wait_timeout_ms": {"type": "integer", "description": "Budget for wait_for (default 30000)."},
            "timeout_ms": _TIMEOUT_MS,
            "max_chars": _MAX_CHARS,
        },
    },
}

FIND: Dict[str, Any] = {
    "name": "desktop_find",
    "description": (
        "Find elements by role, name, value, text or automation id and get their refs, without reading the whole "
        "tree. Use it when the role or the label is known ('the Save button', 'the search field'); use "
        "desktop_snapshot when you need to understand the layout first. Set exact=true for a case-insensitive "
        "whole-string match. An empty match list means the element is not in the current tree: it may be in a menu "
        "or sheet that is not open, or the app has not settled."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "app": _APP,
            "window_id": _WINDOW_ID,
            "role": {
                "type": "string",
                "description": "Accessibility role as a snapshot prints it: button, textfield, checkbox, listitem, menuitem, tab, link...",
            },
            "name": {"type": "string", "description": "Accessible name or label."},
            "value": {"type": "string", "description": "Current value of the element."},
            "text": {"type": "string", "description": "Substring of name, value, title or description."},
            "description": {"type": "string", "description": "Accessible description."},
            "native_id": {"type": "string", "description": "Native automation id."},
            "exact": {"type": "boolean", "description": "Require a case-insensitive exact match (default false)."},
            "limit": {"type": "integer", "minimum": 0, "maximum": 500, "description": "Max matches (default 50, 0 = all)."},
            "timeout_ms": _TIMEOUT_MS,
            "max_chars": _MAX_CHARS,
        },
    },
}

ACT: Dict[str, Any] = {
    "name": "desktop_act",
    "description": (
        "Do one thing to one element, or send one key combo. Semantic by default: through the accessibility API it "
        "does not take focus, move the cursor, synthesize keystrokes or touch the clipboard, and it fails closed "
        "instead of guessing. 'set-value' is the headless way to fill a field ('type' is refused headless on "
        "Windows). 'select' picks a list/dropdown option, 'toggle'/'check' handle checkboxes, 'scroll' takes "
        "direction and amount, 'press' sends a combo such as 'ctrl+s' or 'return'. Verify by reading the element "
        "again afterwards. Retry only when the returned disposition says retry is safe: anything else may already "
        "have landed, and a blind repeat can click or submit twice."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "click",
                    "double-click",
                    "triple-click",
                    "right-click",
                    "focus",
                    "set-value",
                    "clear",
                    "select",
                    "toggle",
                    "check",
                    "uncheck",
                    "expand",
                    "collapse",
                    "scroll",
                    "scroll-to",
                    "hover",
                    "press",
                ],
                "description": "What to do. 'press' sends 'keys'; 'set-value' and 'select' need 'value'; 'scroll' uses direction and amount.",
            },
            "ref": _REF,
            "value": {"type": "string", "description": "The text to set, or the option label to select."},
            "keys": {"type": "string", "description": "Key combo for press, e.g. 'ctrl+s', 'return', 'escape', 'shift+tab'."},
            "direction": {"type": "string", "enum": ["up", "down", "left", "right"], "description": "Scroll direction (default down)."},
            "amount": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Scroll units (default 3)."},
            "window_id": {**_WINDOW_ID, "description": _WINDOW_ID["description"] + " Needed by press to target a non-frontmost app."},
            "force": {"type": "boolean", "description": "For press: allow combos the adapter blocks (alt+f4, win+l, ctrl+shift+esc...). Default false."},
            "headed": _HEADED,
            "timeout_ms": _TIMEOUT_MS,
            "max_chars": _MAX_CHARS,
        },
        "required": ["action"],
    },
}

WINDOW: Dict[str, Any] = {
    "name": "desktop_window",
    "description": (
        "Manage apps and windows without touching their content: launch an app, quit one, focus, resize, move, "
        "minimize, maximize or restore a window. 'restore' is the fix for a minimized window, which cannot be "
        "driven at all. 'focus' brings a window to the front and takes the foreground away from Apo, so prefer "
        "leaving a window behind another one: a covered window is still drivable. 'launch' takes a bare name that "
        "exists under System32/Windows ('notepad') or an absolute path, not a display name, and refuses when the "
        "app is already running."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["launch", "close", "focus", "resize", "move", "minimize", "maximize", "restore"],
                "description": "The window operation: launch or close an app, or act on a window's placement and state.",
            },
            "app": {**_APP, "description": _APP["description"] + " For launch: a bare System32/Windows name or an absolute path."},
            "window_id": _WINDOW_ID,
            "app_args": {"type": "array", "items": {"type": "string"}, "description": "Command-line arguments for launch."},
            "activate": {"type": "boolean", "description": "For launch: bring the app forward and wait for its window (takes focus). Default false."},
            "no_attach": {"type": "boolean", "description": "For launch: force a fresh instance. Note the pre-check still refuses when the app is running."},
            "force": {"type": "boolean", "description": "For close: terminate instead of quitting gracefully."},
            "x": {"type": "integer", "description": "For move: new left edge in pixels."},
            "y": {"type": "integer", "description": "For move: new top edge in pixels."},
            "width": {"type": "integer", "description": "For resize: new width in pixels."},
            "height": {"type": "integer", "description": "For resize: new height in pixels."},
            "timeout_ms": _TIMEOUT_MS,
            "max_chars": _MAX_CHARS,
        },
        "required": ["action"],
    },
}

CLIPBOARD: Dict[str, Any] = {
    "name": "desktop_clipboard",
    "description": (
        "Read, replace or clear the system clipboard. Clipboard content is private: do not paste it into logs, "
        "commits, public messages or uploads, and do not overwrite what Apo copied unless the task needs it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["get", "set", "clear"], "description": "Default 'get'."},
            "text": {"type": "string", "description": "For set: the text to put on the clipboard."},
            "timeout_ms": _TIMEOUT_MS,
            "max_chars": _MAX_CHARS,
        },
    },
}

BATCH: Dict[str, Any] = {
    "name": "desktop_batch",
    "description": (
        "Run several agent-desktop commands in one process, sequentially, in one call: the efficient path when a "
        "task needs more than one step, and the escape hatch for commands without a dedicated tool (wait, get, is, "
        "screenshot, list-displays, notifications, trace). Each entry is {command, args}, where args holds the CLI "
        "flags in camelCase or snake_case. The batch is not atomic: with stop_on_error it halts at the first "
        "failure, and results so far are still returned."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "commands": {
                "type": "array",
                "description": "Array of {command, args}, e.g. [{\"command\":\"snapshot\",\"args\":{\"app\":\"Discord.exe\",\"compact\":true}}].",
                "items": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "agent-desktop command name."},
                        "args": {"type": "object", "description": "Flags for that command."},
                    },
                    "required": ["command"],
                },
            },
            "stop_on_error": {"type": "boolean", "description": "Halt at the first failed command (default false)."},
            "timeout_ms": {**_TIMEOUT_MS, "description": "Wall-clock budget for the whole batch (default 60000)."},
            "max_chars": _MAX_CHARS,
        },
        "required": ["commands"],
    },
}

INSTALL: Dict[str, Any] = {
    "name": "desktop_install",
    "description": (
        "Install or check the agent-desktop binary this plugin drives. The plugin bundles no binary: "
        "action='install' downloads the official release archive from the upstream GitHub release for this "
        "Windows target, verifies its sha256 against a digest pinned in the plugin (a release without a pinned "
        "digest is refused), extracts only the expected executable "
        "into the plugin's bin directory, and then proves the install by running 'version' and 'status' "
        "against it. Re-running is safe and reports already_installed. action='status' shows the settings, "
        "the resolved paths and the pinned versions without touching the network. action='verify' probes the "
        "binary that would actually be used. Run install when any tool returns BINARY_NOT_FOUND."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "install", "verify"], "description": "What to do (default 'status')."},
            "force": {"type": "boolean", "description": "Reinstall even when a working binary is already present."},
        },
    },
}

ALL = {
    "desktop_status": STATUS,
    "desktop_apps": APPS,
    "desktop_snapshot": SNAPSHOT,
    "desktop_find": FIND,
    "desktop_act": ACT,
    "desktop_window": WINDOW,
    "desktop_clipboard": CLIPBOARD,
    "desktop_batch": BATCH,
    "desktop_install": INSTALL,
}
