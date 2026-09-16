![Hermes Agent](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/assets/banner.png)

# Hermes Agent Awesome Plugins

**Small plugins for a more capable Hermes Desktop.**

[Install the pack](#install) · [Explore the plugins](#the-pack) · [Understand how it works](#how-it-works)

[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-0.21.0%2B-6f42c1)](https://github.com/NousResearch/hermes-agent)
[![Plugins](https://img.shields.io/badge/plugins-11-2ea44f)](#the-pack)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

## A better Hermes Desktop, one useful capability at a time

This is a maintained community pack of Hermes Agent plugins. Each plugin solves one focused desktop problem: provider visibility, session control, reading, memory review, or interface polish.

The pack is pinned and reproducible. Every entry in `hermes-pack.yaml` identifies a repository, subdirectory, and exact commit. Install the pack when you want the collection, or open an individual plugin README when you want one capability.

## The pack

| Plugin | What it gives you |
| --- | --- |
| [provider-status](plugins/provider-status/README.md) | Provider quota tracking, OAuth status, multiple accounts, and key rotation in the status bar. |
| [intelligent-tool-break](plugins/intelligent-tool-break/README.md) | Stop a stalled tool call, send a correction, or make it try again with `/break`, `/break {message}`, and `/again`. |
| [better-session-appearance](plugins/better-session-appearance/README.md) | More readable session names, colors, emphasis, and idle-state icons. |
| [drag-to-pin-session](plugins/drag-to-pin-session/README.md) | Reorganize pinned sessions with drag-and-drop. |
| [opaque-composer](plugins/opaque-composer/README.md) | Keep the desktop composer readable while the transcript scrolls behind it. |
| [scroll-on-switch](plugins/scroll-on-switch/README.md) | Keep the active session transcript at the bottom when switching sessions. |
| [reasoning-switch](plugins/reasoning-switch/README.md) | Rotate reasoning effort from the status bar with per-level controls and prompt limits. |
| [iteration-budget-meter](plugins/iteration-budget-meter/README.md) | See the focused session's tool-call budget live in the status bar. |
| [memory-review](plugins/memory-review/README.md) | Review staged memory writes and approve or reject them from a dialog. |
| [rss-reader](plugins/rss-reader/README.md) | Read, organize, search, summarize, and grade RSS and Atom feeds in a three-column reader. |

## Start with the problem in front of you

### You want to see what your providers are doing

Open **Provider Status** from the desktop status bar. See quota use, account health, and rotation state without opening provider dashboards.

### A tool call is stuck

Use **Intelligent Tool Break** to stop the call or send a correction. `/again` retries the last tool action when repetition is the right fix.

### Your session list is hard to scan

Use **Better Session Appearance**, then pin and arrange sessions with **Drag to Pin Session**. **Scroll on Switch** keeps the active transcript in a predictable place.

### You want a quieter writing surface

**Opaque Composer** keeps transcript text from bleeding through the composer. **Reasoning Switch** and **Iteration Budget Meter** expose the controls and limits that matter while you work.

### You need to review memory before it lands

**Memory Review** puts staged writes in a dialog so you can inspect and approve them deliberately.

### Your reading list is becoming another job

**RSS Reader** keeps feeds in a local library with folders, nested folders, saved stories, mute rules, reader-mode capture, unread handling, and explicit Hermes actions for summaries, discussions, evidence checks, and optional grading.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

Install the pinned pack:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Each plugin keeps its own capability consent. Installing a pack does not bulk-grant capabilities, and secrets remain `requires_env` values rather than being embedded in the pack.

Verify the installation:

```bash
hermes plugins list
hermes plugins pack show https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

To install one plugin, use its individual README and the normal Hermes plugin installer.

## How it works

`hermes-pack.yaml` is the source of truth. It pins `repo`, `subdir`, and a full 40-character `ref` for every plugin. Hermes expands those entries into ordinary plugin installs.

Each plugin lives under `plugins/<name>/` and carries its own `plugin.yaml`, README, and implementation. Most plugins are desktop-only. RSS Reader also includes a Python dashboard API for its feed, article, grading, and preference operations.

The pack is maintained independently from Hermes Agent. Plugin behavior and compatibility follow the version requirements documented in each plugin.

## Requirements

- Hermes Agent **0.21.0 or newer** for shareable plugin packs.
- Windows, macOS, or Linux for the pack itself.
- Individual plugins may have narrower platform requirements. Check their README before installing.

## Documentation

Every plugin has its own README:

- [Provider Status](plugins/provider-status/README.md)
- [Intelligent Tool Break](plugins/intelligent-tool-break/README.md)
- [Better Session Appearance](plugins/better-session-appearance/README.md)
- [Drag to Pin Session](plugins/drag-to-pin-session/README.md)
- [Opaque Composer](plugins/opaque-composer/README.md)
- [Scroll on Switch](plugins/scroll-on-switch/README.md)
- [Reasoning Switch](plugins/reasoning-switch/README.md)
- [Iteration Budget Meter](plugins/iteration-budget-meter/README.md)
- [Memory Review](plugins/memory-review/README.md)
- [RSS Reader](plugins/rss-reader/README.md)
- [Maintainer sync skill](skills/hermes-awesome-plugins-sync/SKILL.md)

## Support and contributions

Report problems, suggest focused improvements, or follow releases through [@ApoMakesMods](https://x.com/ApoMakesMods) on X. Keep changes scoped to the plugin they improve and update that plugin's documentation with user-facing behavior.

## License

[MIT](LICENSE) © Apostol Apostolov

This is an independent community project. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or Hermes Agent. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
