"""Tool schema for the cdp-manager plugin's `cdp` tool."""

CDP = {
    "name": "cdp",
    "description": (
        "Manage local Chrome DevTools Protocol (CDP) servers on 127.0.0.1 "
        "without bash or PowerShell. Actions: status (probe the known ports "
        "plus health, modes, and profile selections, default), profiles "
        "(list every launchable profile with locked/served state), launch "
        "(start Chrome with --remote-debugging-port on a profile), restart "
        "(stop then launch, the way to switch mode or profile), stop "
        "(close the listener cleanly via Browser.close), recheck "
        "(re-probe), prefer (mark a port as managed: a backend supervisor "
        "keeps it up, auto-starting it when down and force-rebooting it "
        "after repeated launch failures; pass port 0 to unmanage). Uses "
        "the managed port when no port is given; falls back to the sole "
        "live port."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["status", "profiles", "launch", "restart", "stop", "recheck", "prefer"],
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
            "mode": {
                "type": "string",
                "enum": ["headful", "headless"],
                "description": (
                    "Launch or restart mode (default headful): headful "
                    "shows a Chrome window, headless runs --headless=new "
                    "with no window. Remembered per port."
                ),
            },
            "profile": {
                "type": "string",
                "description": (
                    "Launch or restart profile (default hermes): hermes "
                    "runs an isolated per-port profile, guest runs "
                    "ephemeral, chrome:<dirname> reuses a profile from "
                    "your real Chrome (cookies included) when that Chrome "
                    "is not running. Launches onto a locked or "
                    "already-served profile are refused. Remembered per "
                    "port and reused next time."
                ),
            },
        },
        "required": [],
    },
}
