<div align="center">

  <a href="https://github.com/NousResearch/hermes-agent">
    <img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" />
  </a>

  <h1>Hermes Agent Awesome Plugins</h1>

  <strong>Focused plugins for a more capable Hermes Desktop.</strong>

  Provider visibility, session control, reading, memory review, and interface polish — each plugin owns one job.

  [![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-0.21.0%2B-6f42c1)](https://github.com/NousResearch/hermes-agent)
  [![Plugins](https://img.shields.io/badge/plugins-13-2ea44f)](#whats-in-the-pack)
  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

  [Install the pack](#install) &nbsp;·&nbsp; [Explore the plugins](#whats-in-the-pack) &nbsp;·&nbsp; [Pinning model](#how-it-works)

</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Hermes Agent Awesome Plugins" />
</div>

## What's in the Pack

Twelve plugins are pinned in `hermes-pack.yaml` (pack version 1.14.0). **reasoning-switch** lives in this repo but is **not** in the pack and stays off by default — install it separately if you want it.

### Status Bar

| Plugin | What you get |
| --- | --- |
| [provider-status](plugins/provider-status/README.md) | Status-bar quota used/remaining. Multi-account. Rotate on low quota or reset day. Grok/Codex OAuth. Providers: tavily, opencode, deepseek, glm, openrouter, grok, codex. |
| [iteration-budget-meter](plugins/iteration-budget-meter/README.md) | Per-turn N/budget while work runs. Hover and click for request stats. |
| [reasoning-switch](plugins/reasoning-switch/README.md) | Cycle reasoning effort from the status bar, with colors and per-level prompt demote. **Not in the pack; enable separately.** |

### Tools and Memory

| Plugin | What you get |
| --- | --- |
| [intelligent-tool-break](plugins/intelligent-tool-break/README.md) | `/break`, `/break {msg}`, and `/again`. Desktop strip. Turn stays alive. |
| [memory-review](plugins/memory-review/README.md) | Checkbox staged memory writes. Approve or reject from a dialog. |
| [better-capabilities](plugins/better-capabilities/README.md) | Delete plugins/skills. Zip a skill. On/off presets. |

### Sessions and Sidebar

| Plugin | What you get |
| --- | --- |
| [better-session-appearance](plugins/better-session-appearance/README.md) | Idle color, bold, and icon. Auto Rules by title keywords. |
| [sidebar-manager](plugins/sidebar-manager/README.md) | Hide and reorder nav rows and session sections. |
| [drag-to-pin-session](plugins/drag-to-pin-session/README.md) | Drag pin/unpin with lasting order. |
| [scroll-on-switch](plugins/scroll-on-switch/README.md) | Snap to bottom on session switch. Does not fight streaming. |

### Composer

| Plugin | What you get |
| --- | --- |
| [opaque-composer](plugins/opaque-composer/README.md) | Solid composer while the transcript scrolls behind it. |
| [compact-reasoning-label](plugins/compact-reasoning-label/README.md) | Model pill shows the name only. Effort stays in the reasoning pill. |

### Reading

| Plugin | What you get |
| --- | --- |
| [rss-reader](plugins/rss-reader/README.md) | Three-column reader. Folders, mute/search, capture. Optional Hermes tools and ticker. |

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Each plugin keeps its own capability consent. Packs do not bulk-grant. Secrets stay `requires_env` — not embedded in the pack.

Verify:

```bash
hermes plugins list
hermes plugins pack show https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

For a single plugin, follow that plugin's README. For **reasoning-switch**, use its README — it is not installed by the pack.

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

- [provider-status](plugins/provider-status/README.md)
- [intelligent-tool-break](plugins/intelligent-tool-break/README.md)
- [iteration-budget-meter](plugins/iteration-budget-meter/README.md)
- [reasoning-switch](plugins/reasoning-switch/README.md) — not in the pack
- [better-session-appearance](plugins/better-session-appearance/README.md)
- [sidebar-manager](plugins/sidebar-manager/README.md)
- [drag-to-pin-session](plugins/drag-to-pin-session/README.md)
- [scroll-on-switch](plugins/scroll-on-switch/README.md)
- [opaque-composer](plugins/opaque-composer/README.md)
- [compact-reasoning-label](plugins/compact-reasoning-label/README.md)
- [memory-review](plugins/memory-review/README.md)
- [better-capabilities](plugins/better-capabilities/README.md)
- [rss-reader](plugins/rss-reader/README.md)
- [Maintainer sync skill](skills/hermes-awesome-plugins-sync/SKILL.md)


## Support

Report problems or follow releases through [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov

This is an independent community project. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or Hermes Agent. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
