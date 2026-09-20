"""Tool schema for the cdp-manager plugin's `cdp` tool."""

CDP = {
    "name": "cdp",
    "description": (
        "Manage the local Chrome DevTools Protocol (CDP) server on 127.0.0.1 "
        "without bash or PowerShell. Actions: status (probe the known ports, "
        "default), launch (start Chrome with --remote-debugging-port), stop "
        "(close the listener cleanly via Browser.close), recheck (re-probe), "
        "prefer (mark a port as managed: a backend supervisor keeps it up, "
        "auto-starting it when down and force-rebooting it after repeated "
        "launch failures; pass port 0 to unmanage). Uses the managed port "
        "when no port is given; falls back to the sole live port."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "launch", "stop", "recheck", "prefer"],
                "description": "What to do. Default status.",
            },
            "port": {
                "type": "number",
                "description": (
                    "Target port. Optional: omitted means the managed "
                    "(preferred) port, then the sole live port. For prefer "
                    "it marks this port as managed (0 clears the mark)."
                ),
            },
        },
        "required": [],
    },
}
