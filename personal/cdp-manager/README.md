# CDP Manager

<div align="center">
  <img src="docs/hero.png" width="100%" alt="CDP Manager" />
</div>

Statusbar plugin + `cdp` agent tool for managing local Chrome DevTools
Protocol (CDP) debug ports on 127.0.0.1.

- Statusbar plug glyph opens the port dialog: live state, browser, pid and
  latency per port, probed only while the dialog is open.
- Per-port glyph buttons: launch (starts Chrome with
  `--remote-debugging-port`, no visible terminal, windowed or headless), stop
  (clean `Browser.close` over the endpoint's WebSocket), recheck. Changing the
  mode of a live port restarts it in the new mode.
- A profile picker per port: Hermes (isolated), a personal Chrome profile
  (your cookies, when that Chrome is closed), or Guest. The choice is
  remembered and reused on restart.
- One port can be managed: a backend supervisor keeps it up, auto-starting it
  when down and force-rebooting it after repeated launch failures.
- The `cdp` agent tool lets the agent do all of the above from chat:
  `status`, `launch`, `stop`, `recheck`, `prefer`, `wedged`, `unwedge` - no
  bash, no PowerShell. It targets the managed port when none is given, then
  the sole live port.
- Launches always pass a startup URL, so an isolated profile never boots into
  Chrome's profile picker; `wedged` detects that stuck state on a live port and
  `unwedge` repairs it with a stop and relaunch.

## Install

```
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/cdp-manager
```

Then enable it:

```
hermes plugins enable cdp-manager --no-allow-tool-override
```

The desktop dialog needs a full Hermes quit/reopen the first time (the
Python backend routes mount with the dashboard server). The `cdp` tool is
usable from the next session after enabling.

## Files

- `desktop/plugin.js` - statusbar chip + dialog
- `dashboard/plugin_api.py` - FastAPI routes at `/api/plugins/cdp-manager/`
- `cdp_core.py` - probe/launch/stop logic, config
- `cdp_tools.py` + `schemas.py` - the `cdp` agent tool
