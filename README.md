<div align="center">

  <a href="https://github.com/NousResearch/hermes-agent">
    <img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" />
  </a>

  <h1>Hermes Agent Awesome Plugins</h1>

  <strong>Focused plugins for a more capable Hermes Desktop.</strong>

  A maintained community pack for provider visibility, session control, reading, memory review, and interface polish.

  [![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-0.21.0%2B-6f42c1)](https://github.com/NousResearch/hermes-agent)
  [![Plugins](https://img.shields.io/badge/plugins-13-2ea44f)](#the-pack)
  [![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

  [Install the pack](#install) &nbsp;·&nbsp; [Explore the plugins](#the-pack) &nbsp;·&nbsp; [Understand the pinning model](#how-it-works)

</div>

## What this pack is for

Hermes Agent Awesome Plugins adds small, focused capabilities to Hermes Desktop. Each plugin owns one desktop problem and documents its own behavior, requirements, and checks.

The pack is pinned and reproducible. Every entry in `hermes-pack.yaml` names a repository, subdirectory, and exact commit, so the collection can be installed without guessing which source revision was used.

## The pack

### Status bar

<table>
<thead>
<tr>
<th nowrap>Plugin</th>
<th>What it gives you</th>
</tr>
</thead>
<tbody>
<tr>
<td nowrap><a href="plugins/provider-status/README.md">provider‑status</a></td>
<td>Track provider quotas, OAuth status, multiple accounts, and key rotation in the status bar.</td>
</tr>
<tr>
<td nowrap><a href="plugins/reasoning-switch/README.md">reasoning‑switch</a></td>
<td>Rotate reasoning effort from the status bar with per-level controls and prompt limits.</td>
</tr>
<tr>
<td nowrap><a href="plugins/iteration-budget-meter/README.md">iteration‑budget‑meter</a></td>
<td>See the focused session's tool-call budget live in the status bar.</td>
</tr>
</tbody>
</table>

### Tool calls, memory, and capabilities

<table>
<thead>
<tr>
<th nowrap>Plugin</th>
<th>What it gives you</th>
</tr>
</thead>
<tbody>
<tr>
<td nowrap><a href="plugins/intelligent-tool-break/README.md">intelligent‑tool‑break</a></td>
<td>Stop a stalled tool call, send a correction, or retry the last action with <code>/break</code>, <code>/break {message}</code>, and <code>/again</code>.</td>
</tr>
<tr>
<td nowrap><a href="plugins/memory-review/README.md">memory‑review</a></td>
<td>Inspect staged memory writes and approve or reject them from a dialog.</td>
</tr>
<tr>
<td nowrap><a href="plugins/better-capabilities/README.md">better‑capabilities</a></td>
<td>Delete a plugin or skill from Capabilities, zip a learned skill, save on/off presets, and apply them with /preset.</td>
</tr>
</tbody>
</table>

### Sessions and sidebar

<table>
<thead>
<tr>
<th nowrap>Plugin</th>
<th>What it gives you</th>
</tr>
</thead>
<tbody>
<tr>
<td nowrap><a href="plugins/better-session-appearance/README.md">better‑session‑appearance</a></td>
<td>Make session names easier to scan with colors, emphasis, and idle-state icons.</td>
</tr>
<tr>
<td nowrap><a href="plugins/sidebar-manager/README.md">sidebar‑manager</a></td>
<td>Hide and reorder sidebar nav rows and session sections from a dim glyph next to New session.</td>
</tr>
<tr>
<td nowrap><a href="plugins/drag-to-pin-session/README.md">drag‑to‑pin‑session</a></td>
<td>Reorganize pinned sessions with drag-and-drop.</td>
</tr>
<tr>
<td nowrap><a href="plugins/scroll-on-switch/README.md">scroll‑on‑switch</a></td>
<td>Keep the active transcript at the bottom when switching sessions.</td>
</tr>
</tbody>
</table>

### Composer

<table>
<thead>
<tr>
<th nowrap>Plugin</th>
<th>What it gives you</th>
</tr>
</thead>
<tbody>
<tr>
<td nowrap><a href="plugins/opaque-composer/README.md">opaque‑composer</a></td>
<td>Keep the desktop composer readable while the transcript scrolls behind it.</td>
</tr>
<tr>
<td nowrap><a href="plugins/compact-reasoning-label/README.md">compact‑reasoning‑label</a></td>
<td>Show the model name only in the model pill and leave the thinking level to the reasoning pill beside it.</td>
</tr>
</tbody>
</table>

### Reading

<table>
<thead>
<tr>
<th nowrap>Plugin</th>
<th>What it gives you</th>
</tr>
</thead>
<tbody>
<tr>
<td nowrap><a href="plugins/rss-reader/README.md">rss‑reader</a></td>
<td>Read, organize, search, summarize, and grade RSS and Atom feeds in a three-column reader.</td>
</tr>
</tbody>
</table>

## Why these plugins belong together

The pack follows the way a Hermes session actually feels: understand the system state, keep the session moving, reduce visual friction, and make room for deeper work. The plugins remain independent, so you can install the pack or choose only the capabilities you need.

RSS Reader is the largest workflow in the pack. It keeps a local reading library with folders, nested folders, saved stories, mute rules, reader-mode capture, delayed unread handling, and explicit Hermes actions for summaries, discussions, evidence checks, and optional grading.

## What's current

The individual plugin manifests are the version authority. The current pack includes:

- **Provider Status 1.5.7:** quota visibility, multi-account support, and key rotation controls.
- **Intelligent Tool Break 1.3.2:** `/break`, correction messages, and `/again` retry handling.
- **RSS Reader 1.0.1:** local Python API transport, nested folders, improved unread behavior, and compact handling for small full-article images.
- **Memory Review 1.2.1:** staged-write review and approval controls.
- **Compact Reasoning Label 1.0.0:** the composer's model pill shows only the model name; the effort word lives only in the reasoning pill.
- **Better Capabilities 1.0.0:** delete plugins and skills from Capabilities, and zip a learned skill folder.
- **Sidebar Manager 1.0.0:** hide and reorder sidebar nav rows and session sections from a dim list-ordered glyph next to New session.

See each plugin README for the complete behavior and the repository changelog for pack-level history.

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

To install one plugin instead, follow its individual README and use the normal Hermes plugin installer.

## How it works

`hermes-pack.yaml` is the source of truth. Each entry pins:

- `repo`: the source repository
- `subdir`: the plugin directory within that repository
- `ref`: the exact 40-character commit to install

Hermes expands those entries into ordinary plugin installs. Each plugin lives under `plugins/<name>/` with its own `plugin.yaml`, README, implementation, and tests where applicable.

Most plugins are desktop-only. RSS Reader also includes a Python dashboard API for feed, article, grading, and preference operations. Better Capabilities uses a Python API for Recycle Bin delete and skill zip downloads. Check the individual README before assuming that a plugin works on every Hermes surface or operating system.

## Requirements and limits

- Hermes Agent **0.21.0 or newer** for shareable plugin packs.
- Windows, macOS, or Linux for the pack itself.
- Individual plugins may have narrower platform or desktop-version requirements.
- Provider services, search providers, and model accounts retain their normal usage limits and costs.

This is an independent community project. It does not change Hermes Agent core, bulk-grant capabilities, or silently send plugin data to another service. Plugin-specific data handling is documented in each plugin README.

## Documentation

Every plugin has a dedicated README:

- [Provider Status](plugins/provider-status/README.md)
- [Reasoning Switch](plugins/reasoning-switch/README.md)
- [Iteration Budget Meter](plugins/iteration-budget-meter/README.md)
- [Intelligent Tool Break](plugins/intelligent-tool-break/README.md)
- [Memory Review](plugins/memory-review/README.md)
- [Better Capabilities](plugins/better-capabilities/README.md)
- [Better Session Appearance](plugins/better-session-appearance/README.md)
- [Sidebar Manager](plugins/sidebar-manager/README.md)
- [Drag to Pin Session](plugins/drag-to-pin-session/README.md)
- [Scroll on Switch](plugins/scroll-on-switch/README.md)
- [Opaque Composer](plugins/opaque-composer/README.md)
- [Compact Reasoning Label](plugins/compact-reasoning-label/README.md)
- [RSS Reader](plugins/rss-reader/README.md)
- [Maintainer sync skill](skills/hermes-awesome-plugins-sync/SKILL.md)

## Support and contributions

Report problems, suggest focused improvements, or follow releases through [@ApoMakesMods](https://x.com/ApoMakesMods) on X. Keep changes scoped to the plugin they improve and update that plugin's documentation with user-facing behavior.

## License

[MIT](LICENSE) © Apostol Apostolov

This is an independent community project. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or Hermes Agent. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
