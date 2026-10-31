<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Hermes Agent Desktop</h1>
  <strong>Hands on Windows apps without taking over the screen.</strong>
  <p>Read any app's real UI and act on it by ref: click, fill, select, toggle, scroll, key combos, windows, clipboard.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.0.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

## What You Can Do

- Ask Hermes to operate a desktop app that has no CLI: fill a field, press a button, tick a checkbox, pick a menu item, switch a tab, resize a window.
- Keep working while it does. Actions are semantic and headless by default, so they do not take focus, move the cursor, synthesize keystrokes or touch the clipboard.
- Verify instead of hoping. Every action reports whether it was delivered and verified, and whether a retry is safe.
- Read what an app actually shows, as text with roles and refs, instead of a screenshot.
- Run several steps in one call, and reach anything without a dedicated tool through `desktop_batch`.

## Requirements

- Windows 10 1809+ or Windows Server 2019+, x64 or ARM64, in the signed-in user's interactive session.
- The [`agent-desktop`](https://github.com/vercel-labs/agent-desktop) binary. This plugin does not bundle it and does not download it; install it once:

```powershell
npm install -g agent-desktop --allow-scripts=agent-desktop
```

  If npm blocks that install script, the package still works through a slower Node launcher. Link the native binary with:

```powershell
node "$env:APPDATA\npm\node_modules\agent-desktop\scripts\postinstall.js"
```

- Built and verified against Hermes Agent 0.22.5. It needs a build whose plugin host exposes `ctx.register_tool`, and it declares no Python dependencies.
- No permission grant is needed on Windows. `desktop_status` reporting `accessibility: granted` and `automation: not_required` is normal.

The plugin finds the binary on `PATH`, then through `AGENT_DESKTOP_BIN`, then at the npm global location.

## Install

```powershell
hermes plugins install hermes-agent-desktop
```

Or from this repository:

```powershell
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/hermes-agent-desktop
```

New tools land on the next session; the gateway rebuilds the tool registry rather than hot-loading it.

## Tools

| Tool | What it answers |
| --- | --- |
| `desktop_status` | Is automation usable: version, platform, permissions, supported surfaces |
| `desktop_apps` | What is running, and what windows exist with their ids, titles, bounds and minimized state |
| `desktop_snapshot` | What the UI contains: role, name, states and a ref per actionable element |
| `desktop_find` | Where is the element with this role, name, value or automation id |
| `desktop_act` | Do one thing to one element, or send one key combo |
| `desktop_window` | Launch or quit an app; focus, resize, move, minimize, maximize or restore a window |
| `desktop_clipboard` | Read, replace or clear the system clipboard |
| `desktop_batch` | Several commands in one process, and commands without a dedicated tool |

## The Loop

Observe, act on a ref, observe again. A ref is qualified (`@<snapshot_id>:eN`) and belongs to the snapshot that produced it.

```text
desktop_snapshot   {"app": "Discord.exe", "interactive_only": true, "compact": true}
desktop_act        {"action": "click", "ref": "@s3ngmv5nd3xp1a:e2"}
desktop_snapshot   {"app": "Discord.exe", "interactive_only": true, "compact": true}
```

`set-value` is the headless way to fill a field. `type` is refused headless on Windows because it synthesizes keystrokes; the tools pass `--headed` only when a call asks for it explicitly, and that call is the one that moves the cursor and can take focus.

## Limits Worth Knowing

- A minimized window cannot be driven: every element reports `offscreen`. `desktop_window` with `action: "restore"` fixes it. A window that is merely behind another one is still drivable, so `focus` is rarely needed.
- `list-apps` only lists apps that own a window. A tray-only process does not appear, and a snapshot of it returns `APP_NOT_FOUND`.
- Chromium and Electron apps read thin until they settle. Retry with a longer `timeout_ms` instead of concluding the tree is empty.
- Retry an action only when its `disposition.retry` is `safe`. Any other delivery value means it may have landed, and a repeat can click or submit twice.
- `launch` takes a bare name from `System32` or the Windows directory, or an absolute path, and refuses when the app is already running.
- An oversized snapshot is pruned to fit and reports `tree_nodes_dropped`; narrow the scope with `root`, `skeleton` or a lower `max_depth`.

## Disclosure

- The plugin runs the `agent-desktop` executable as a child process with the arguments it builds, and returns that program's JSON unchanged. That is the only shell execution it performs.
- It reads whatever the accessibility tree exposes: window titles, labels, field values, and the clipboard when asked. All of that can contain private content. It is returned to the model as tool output and is not written to disk by this plugin.
- No network calls, no telemetry, no credentials, no file writes outside what the binary itself keeps in `~/.agent-desktop`.
- Actions change the apps they target. `desktop_act`, `desktop_window` and `desktop_clipboard` are the tools that write.

## Verification

```powershell
hermes plugins validate --install-deps .
uv run --with pytest python -m pytest -q
```

The suite covers schema shape, flag rendering, envelope handling (missing binary, timeout, non-JSON output, oversized trees) and argument validation. Three tests are live against the real binary and skip when it is not installed.

## Attribution

Tool behaviour, command set and documentation belong to [vercel-labs/agent-desktop](https://github.com/vercel-labs/agent-desktop), licensed Apache-2.0. This plugin wraps the published CLI and ships no part of that binary.
