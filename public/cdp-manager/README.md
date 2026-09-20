# CDP Manager

<div align="center">
  <img src="docs/hero.png" width="100%" alt="CDP Manager" />
</div>

Statusbar plugin plus `cdp` agent tool for managing local Chrome DevTools
Protocol (CDP) debug ports on 127.0.0.1.

## What You Can Do

- See every CDP port's health in the status bar: normal when down, bold when up, amber on issues, red when a port needs a reboot.
- Launch, stop, and recheck each port from the dialog, with a Windowed or Headless launch mode per port. Changing the mode on a live port restarts it in the new mode.
- Mark one port as managed: a backend supervisor keeps it up, auto-starting it when down and force-rebooting it after repeated launch failures.
- Pick a profile per port: Hermes (isolated), a personal Chrome profile (your cookies, when that Chrome is closed), or Guest (ephemeral). The choice is remembered and reused on restart.
- Use the `cdp` agent tool from chat (`status`, `launch`, `stop`, `recheck`, `prefer`) with no shell. It targets the managed port when none is given.

## Install

```
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/cdp-manager
```

Then enable it:

```
hermes plugins enable cdp-manager --no-allow-tool-override
```

The desktop dialog needs a full Hermes quit and reopen the first time (the
Python backend routes mount with the dashboard server). The `cdp` tool is
usable from the next session after enabling.

## Files

- `desktop/plugin.js` - statusbar chip plus dialog
- `dashboard/plugin_api.py` - FastAPI routes at `/api/plugins/cdp-manager/`
- `cdp_core.py` - probe, launch, stop, health, supervisor
- `cdp_tools.py` plus `schemas.py` - the `cdp` agent tool

**Disclosure:** this plugin launches local Chrome on 127.0.0.1 only, with
per-port profiles under the Hermes home directory, and closes it with a
clean `Browser.close`. A personal Chrome profile runs automation with your
cookies; pick it only when that Chrome is closed, and note one debug port
per profile. The supervisor only touches ports you explicitly
marked managed. State lives in the plugin's own config file. No Hermes
config writes, no credentials, no telemetry.
