<!-- markdownlint-disable MD033 -->

<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent">
    <img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" />
  </a>
</div>

<div align="center">

  <h1>Hermes Agent Awesome Plugins</h1>

  <p>Give Hermes Desktop useful tools for provider limits, long sessions, feeds, and memory.</p>

  <p>
    <a href="#readme"><img src="https://img.shields.io/badge/Type-Plugin%20pack-555" alt="Type: Plugin pack"></a>
    <a href="./package.json"><img src="https://img.shields.io/badge/Language-JavaScript-555" alt="Language: JavaScript"></a>
    <a href="https://github.com/apoapostolov/hermes-agent-awesome-plugins/releases/tag/v1.22.0"><img src="https://img.shields.io/badge/Version-v1.22.0-blue" alt="Version: v1.22.0"></a>
    <a href="https://github.com/apoapostolov/hermes-agent-awesome-plugins/releases/tag/v1.22.0"><img src="https://img.shields.io/badge/Last%20release-2026--09--24-blue" alt="Last release: 2026-09-24"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License: MIT"></a>
  </p>

</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Hermes Agent Awesome Plugins" />
</div>

## Latest plugin update

Provider Status 1.5.10 fixes a frustrating loop: deleting a saved key in the
personal edition now keeps it deleted after the next status poll. The public
edition no longer shows a per-key delete control it cannot safely honor. Restart
Hermes Desktop after updating; the Python side does not reload in place.

The pack remains at 1.22.0. See the [changelog](CHANGELOG.md) for plugin-level
updates and the distinction between personal and public builds.

## Personal and public

This repository keeps two trees.

**[personal/](personal/README.md)** is the full-featured edition I run. These builds may reach into Hermes Desktop internals: app DOM, persisted app keys, raw bridge calls. A Desktop update can break them. They sit outside the plugin SDK contract, so install them only if you accept that risk. The pack pins this tree.

**[public/](public/README.md)** is the catalog edition. These builds stay inside the Hermes plugin SDK (`ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`) so they can be listed. When Desktop has no hook yet, the public copy drops that surface. Not every personal plugin has a public copy: `better-capabilities` stays personal until a catalog hook exists.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/<id>
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/<id>
```

The pack command in [Install](#install) pulls `personal/<id>`.

### Public listing status

| Plugin | Public copy |
| --- | --- |
| [memory-review](public/memory-review) | Ready: pending-id gate, palette + dialog. No shell-menu inject, no hidden composer submit. |
| [intelligent-tool-break](public/intelligent-tool-break) | Ready: hooks and slash commands. No process-wide Popen patch, no private CLI rebind, no descendant SIGKILL, no composer insert. |
| [provider-status](public/provider-status) | Ready: quota chips, probes, plugin-owned config. No vendor CLI auth files, no token refresh on poll, no automatic Hermes `.env` / `config.yaml` writes, no `library.env` copy. |
| [cdp-manager](public/cdp-manager) | Ready: port chips, launch/stop/recheck, managed port, `cdp` tool. Launches loopback-only Chrome the user asked it to manage; plugin-owned config only. |
| better-capabilities | None. Kept in [personal](personal/better-capabilities) until a catalog hook exists. |
| [sidebar-manager](public/sidebar-manager) | Held until a sidebar hide/reorder hook exists. |
| [drag-to-pin-session](public/drag-to-pin-session) | Held until `host.sessions.pin` / reorder exists. |
| [sessionretitler](personal/sessionretitler) | Not in public. Held until an SDK-level llm-rank title write / catalog-safe `title_generation` route exists (see [LIMITATIONS](personal/sessionretitler/LIMITATIONS.md)). |
| [better-session-appearance](public/better-session-appearance) | Held until a session-row decoration / color hook exists. |
| Remaining plugins | Same as personal at the split. Review before a catalog pin. |

Agent rules for these trees live in [AGENTS.md](AGENTS.md). Catalog blockers for the personal editions live in each plugin's `LIMITATIONS.md`.

## What's in the Pack

Fourteen plugins are pinned in `hermes-pack.yaml` (pack version 1.22.0). **reasoning-switch** lives in this repo but is **not** in the pack and stays off by default, so install it separately if you want it.

### Status Bar

| Plugin | What you get |
| --- | --- |
| [provider-status](personal/provider-status/README.md) | Status-bar quota used/remaining. DeepSeek and GLM peak/off-peak gauges with countdowns. Multi-account. Rotate on low quota or reset day. Grok/Codex OAuth. Providers: Tavily, OpenCode Go, DeepSeek, GLM (z.ai), OpenRouter, Grok (xAI), Codex (OpenAI), OpenAI, Anthropic, Groq, Cerebras, Moonshot Kimi, MiniMax, Google Gemini, Hugging Face, Mistral, Qwen. |
| [iteration-budget-meter](personal/iteration-budget-meter/README.md) | Per-turn N/budget while work runs. Hover and click for request stats. |
| [reasoning-switch](personal/reasoning-switch/README.md) | Cycle reasoning effort from the status bar, with colors and per-level prompt demote. **Not in the pack; enable separately.** |

### Tools and Memory

| Plugin | What you get |
| --- | --- |
| [intelligent-tool-break](personal/intelligent-tool-break/README.md) | `/break`, `/break {msg}`, and `/again`. Desktop strip. Turn stays alive. |
| [memory-review](personal/memory-review/README.md) | Checkbox staged memory writes. Approve or reject from a dialog. |
| [better-capabilities](personal/better-capabilities/README.md) | Delete plugins/skills. Zip a skill. On/off presets. |
| [cdp-manager](personal/cdp-manager/README.md) | Launch, stop, and recheck local Chrome CDP ports from the status bar. The `cdp` tool does the same from chat, on your preferred port. |

### Sessions and Sidebar

| Plugin | What you get |
| --- | --- |
| [better-session-appearance](personal/better-session-appearance/README.md) | Idle color, bold, and icon. Auto Rules by title keywords. |
| [sidebar-manager](personal/sidebar-manager/README.md) | Hide and reorder nav rows and session sections. |
| [drag-to-pin-session](personal/drag-to-pin-session/README.md) | Drag pin/unpin with lasting order. |
| [sessionretitler](personal/sessionretitler/README.md) | Retitles the session every N titleable user messages, from the latest exchanges. A title you set yourself is never touched. |
| [scroll-on-switch](personal/scroll-on-switch/README.md) | Snap to bottom on session switch. Does not fight streaming. |

### Composer

| Plugin | What you get |
| --- | --- |
| [opaque-composer](personal/opaque-composer/README.md) | Solid composer while the transcript scrolls behind it. |
| [compact-reasoning-label](personal/compact-reasoning-label/README.md) | Model pill shows the name only. Effort stays in the reasoning pill. |

### Reading

| Plugin | What you get |
| --- | --- |
| [rss-reader](personal/rss-reader/README.md) | Three-column reader. Folders, mute/search, capture. Optional Hermes tools and ticker. |

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Each plugin keeps its own capability consent. Packs do not bulk-grant. Secrets stay `requires_env` and are never embedded in the pack.

Verify:

```bash
hermes plugins list
hermes plugins pack show https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

For a single plugin, follow that plugin's README. For **reasoning-switch**, use its README because the pack does not install it.

## How It Works

`hermes-pack.yaml` pins each pack entry to `repo` + `subdir` + an exact 40-character commit. Hermes expands those into ordinary plugin installs. What you get matches the pinned SHAs, not whichever tip happens to be on `main` that day.

Most plugins are desktop-only. Check the individual README for platform and surface limits.

## Requirements and Limits

- Hermes Agent **0.21.0 or newer** for shareable plugin packs.
- Windows, macOS, or Linux for the pack itself.
- Individual plugins may need a narrower desktop surface or a full Desktop quit/reopen after first install.
- Provider services keep their own usage limits and costs.

This is an independent community project. It does not change Hermes Agent core, bulk-grant capabilities, or silently send plugin data elsewhere. Per-plugin data handling is in each README.

## Documentation

- [Personal editions](personal/README.md)
- [Public editions](public/README.md)
- [AGENTS.md](AGENTS.md): personal/public backport and version rules
- [provider-status](personal/provider-status/README.md)
- [intelligent-tool-break](personal/intelligent-tool-break/README.md)
- [iteration-budget-meter](personal/iteration-budget-meter/README.md)
- [reasoning-switch](personal/reasoning-switch/README.md) (not in the pack)
- [better-session-appearance](personal/better-session-appearance/README.md)
- [sidebar-manager](personal/sidebar-manager/README.md)
- [drag-to-pin-session](personal/drag-to-pin-session/README.md)
- [scroll-on-switch](personal/scroll-on-switch/README.md)
- [opaque-composer](personal/opaque-composer/README.md)
- [compact-reasoning-label](personal/compact-reasoning-label/README.md)
- [memory-review](personal/memory-review/README.md)
- [better-capabilities](personal/better-capabilities/README.md)
- [cdp-manager](personal/cdp-manager/README.md)
- [rss-reader](personal/rss-reader/README.md)
- [Maintainer sync skill](skills/hermes-awesome-plugins-sync/SKILL.md)

## Support

Report problems or follow releases through [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov

This is an independent community project. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or Hermes Agent. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
