"""Tool schema for the cdp-manager plugin's `cdp` tool."""

CDP = {
    "name": "cdp",
    "description": (
        "Manage the local Chrome DevTools Protocol (CDP) server on 127.0.0.1 "
        "without bash or PowerShell. Actions: status (probe the known ports, "
        "default), launch (start Chrome with --remote-debugging-port), stop "
        "(close the listener cleanly via Browser.close), recheck (re-probe), "
        "prefer (mark a port as the preferred default for future calls). "
        "Uses the preferred port when no port is given; falls back to the "
        "sole live port."
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
                    "Target port. Optional: omitted means preferred port, "
                    "then the sole live port. For prefer it marks this port "
                    "as preferred (0 clears the mark)."
                ),
            },
        },
        "required": [],
    },
}
