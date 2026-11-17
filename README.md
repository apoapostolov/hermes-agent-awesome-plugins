<!-- markdownlint-disable MD033 -->

<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent">
    <img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" />
  </a>
</div>

<div align="center">

  <h1>Hermes Agent Awesome Plugins</h1>

  <p>Give Hermes Desktop useful tools for provider limits, long sessions, feeds, memory, and the Windows desktop itself. Twenty-three plugins, twenty-two of them with a public edition.</p>

  <p>
    <a href="#readme"><img src="https://img.shields.io/badge/Type-Plugin%20pack-555" alt="Type: Plugin pack"></a>
    <a href="./package.json"><img src="https://img.shields.io/badge/Language-JavaScript-555" alt="Language: JavaScript"></a>
    <a href="https://github.com/apoapostolov/hermes-agent-awesome-plugins/releases"><img src="https://img.shields.io/badge/Pack-1.27.18-blue" alt="Pack: 1.27.17"></a>
    <a href="https://github.com/apoapostolov/hermes-agent-awesome-plugins/releases"><img src="https://img.shields.io/badge/Last%20release-2026--11--16-blue" alt="Last release: 2026-10-31"></a>
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-MIT-green" alt="License: MIT"></a>
  </p>

</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Hermes Agent Awesome Plugins" />
</div>

## Latest plugin update
**Session Retitler 1.1.3** retitles a session after 10 titleable user messages by default, down from 20, so the name catches up with a topic change sooner. Nothing else moves: the delta trigger, the user-title wall, the digest and the `sessionretitler_title` auxiliary slot are the same as in 1.1.2, and a per-profile `interval` setting still overrides the default. Both editions ship it; update and restart the backend once for the new default to load.

**Session Retitler 1.1.2** no longer depends on the session count landing exactly on a multiple of its interval. The count is read from the live history each turn, and compaction, an interrupted turn or a long tool loop can move it by more than one message, so a boundary missed once used to be lost for good. The trigger is now a delta from the last rename, and a count that compaction pulls backwards is rebased. A rename that came back from the model but could not be written restores the previous name instead of leaving the session untitled, and tries again on the next turn; a session whose title has no recorded provenance is treated as one you set and left alone. The interval, the digest size and the auxiliary slot are unchanged. Update both editions and restart the backend when convenient.

**Radio Plus 1.5.4** writes its station log under the active Hermes home's `plugin-data/radio-plus` directory and checks every outbound stream address and redirect with Hermes' URL-safety policy, so a profile-scoped backend cannot log to the wrong home and the probe and track-title routes cannot be used to reach a private network. Nothing in the picker changes. Reinstall or update both editions; the backend restart is still yours.

**Next Steps 1.0.4** fixes two things under the chips that only showed up in a long session, and its catalog edition **hermes-next-steps 1.1.1** carries the same fixes. The renderer held one state entry for every options block it had ever drawn and one carry queue for every session, and released neither, so a window left open for hours kept the state of replies that had long since scrolled away; both maps now drop what nobody is watching once they pass 64 blocks or 16 sessions, and never a block that is mid-click or still subscribed. Separately, a reply whose options arrived pre-ticked by the decision classifier lost those ticks when the window reloaded, because the first selection was only ever applied in memory; it is written now, like a click. Nothing visible changes: the chips, the Recommended tag, the RISKY pill and the carried-forward row all behave as before. Update if you keep a session open for hours; the pack pin moves with it.

**Catalog Redesign 1.0.12** turns the Capabilities page into a wide, one-row-per-item list for skills, plugins, connectors and tools. Each row carries a thumbnail, the name with its description, and one column that matters for that kind (tags or the short name). Artwork is real: a published plugin borrows the catalog's hero image, and a plugin outside the catalog uses a logo its own folder ships, so rows stop showing initials where the plugin has a face. Hover a row for a preview, click for a detail panel that slides in from the right with the hero image across its header, a 44px section rail, and the on/off switch beside Close. It adds its own route, sidebar row and palette entry and leaves the native Capabilities page alone. The online catalog now loads reliably, the default view is online, and there's an "Update all" button in the header. See [its README](personal/catalog-redesign/README.md).

**Queue Container Fix 1.0.0** moves the per-message controls of a queued prompt from the end of its row to the start of its first line, where they stay on screen. Steer, edit, remove and send now sit before the text, resting at half strength and coming to full on hover or keyboard focus. The control column takes only the width of the buttons a row actually has, so a gateway-owned entry with no controls keeps its message at the left margin. Background commands, subagents and artifact rows are untouched. It ships personal-only (catalog review can't take a stylesheet over app markup). Enable it in Capabilities, Plugins, and the change lands without a restart.

**Radio Plus 1.0.0** is an extended edition of the Radio plugin bundled with Hermes Desktop: keep the oscilloscope, transport, artist links and dictation-aware pause, and make the rest work for any station. The list is editable (name and stream address together), any `http` or `https` stream can be added and is checked before it is saved, the picker searches Radio Browser, its popular list, the Shoutcast directory and TuneIn, a Cyrillic query is also sent transliterated so `Хоризонт` finds `BNR Horizont`, HLS stations play through a bundled `hls.js` 1.6.15, and a station that won't play says why in the panel. A settings page adds "start the last station on launch" (off by default). Disable the bundled Radio plugin first (same status-bar slot). Enable Radio Plus in Capabilities, Plugins, toggle it off and on so the renderer loads the new module, then restart once so the dashboard mounts its routes.

**Next Steps 1.0.1** makes the chips actually show up. The plugin's prompt rule (the one that asks a reply to end in chips instead of "say the word and I'll…") used to measure 2,335 characters with a decision classifier loaded, past Hermes' 2,200-character cap, so Hermes dropped the whole rule and the chips only appeared when the model chose them. The rule is terser now (1,828 characters with recommendations), `MAX_CHARS` sits at 2,100, and the section drops its optional paragraphs rather than overflowing. Tick several chips and one send delivers them together, a Recommended tag marks the options worth taking now, an amber RISKY pill flags the ones that could damage something, a dim second line explains a label that alone would misread, and carried-forward options from earlier replies ride along with an age label and a dismiss cross. Update if you installed 1.0.0; the tools were never affected.

Restart Hermes Desktop after updating; the Python and desktop halves do not reload in place.

## In the app

These are captures from the running app of the parts that only make sense in place: the providers dialog, the reader, the memory review queue, skills presets, the session list, the turn meter and the composer queue. Ten plugins carry one; the settings for every plugin that has a settings page live under Settings, Plugins, and each plugin README shows its own.

<div align="center">
<table>
  <tr>
    <td align="center" valign="top" width="33%"><a href="personal/provider-status"><img src="personal/provider-status/docs/screenshot.png" width="260" alt="Provider Status providers dialog with quota dots, extra keys and key rotation" /></a><br /><sub><a href="personal/provider-status"><strong>Provider Status</strong></a><br />The providers dialog: quota dots, extra keys, rotation</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/rss-reader"><img src="personal/rss-reader/docs/screenshot.png" width="260" alt="RSS Reader three-column layout with folders, article list and reader pane" /></a><br /><sub><a href="personal/rss-reader"><strong>RSS Reader</strong></a><br />Three columns: folders, article list, reader pane</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/memory-review"><img src="personal/memory-review/docs/screenshot.png" width="260" alt="Memory Review dialog with staged writes, All selected, Reject and Approve" /></a><br /><sub><a href="personal/memory-review"><strong>Memory Review</strong></a><br />Staged memory writes waiting for Approve or Reject</sub></td>
  </tr>
  <tr>
    <td align="center" valign="top" width="33%"><a href="personal/better-capabilities"><img src="personal/better-capabilities/docs/screenshot-presets.png" width="260" alt="Skills presets dialog listing a saved All On preset above the capabilities list" /></a><br /><sub><a href="personal/better-capabilities"><strong>Better Capabilities</strong></a><br />Skills presets saved from the current on/off set</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/better-session-appearance"><img src="personal/better-session-appearance/docs/screenshot.png" width="260" alt="Better Session Appearance color picker, Bold Session, icon grid and Auto Rules" /></a><br /><sub><a href="personal/better-session-appearance"><strong>Better Session Appearance</strong></a><br />Color picker, icon grid and Auto Rules</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/iteration-budget-meter"><img src="personal/iteration-budget-meter/docs/iteration-budget-meter.png" width="260" alt="Iteration Budget Meter showing per-turn usage and request statistics" /></a><br /><sub><a href="personal/iteration-budget-meter"><strong>Iteration Budget Meter</strong></a><br />Per-turn usage and request statistics</sub></td>
  </tr>
  <tr>
    <td align="center" valign="top" width="33%"><a href="personal/next-steps"><img src="personal/next-steps/docs/screenshot.png" width="260" alt="Next Steps row under a reply with unanswered options carried forward, age labels, a dismiss cross and Clean Old Proposals" /></a><br /><sub><a href="personal/next-steps"><strong>Next Steps</strong></a><br />Unanswered options carried under a later reply</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/radio-plus"><img src="personal/radio-plus/docs/screenshot-tags.png" width="260" alt="Radio Plus station picker with country:uk typed in the search field, the All, Popular, Shoutcast and TuneIn chips, UK stations and the transport row" /></a><br /><sub><a href="personal/radio-plus"><strong>Radio Plus</strong></a><br />Listen to your own radios, search by country or genre.</sub></td>
    <td align="center" valign="top" width="33%"><a href="personal/queue-container-fix"><img src="personal/queue-container-fix/docs/screenshot.png" width="260" alt="Two queued prompts above the composer, controls drawn at the start of the long row and the short row starting at the left margin" /></a><br /><sub><a href="personal/queue-container-fix"><strong>Queue Container Fix</strong></a><br />Queued prompt controls at the start of the line</sub></td>
  </tr>
  <tr>
    <td align="center" valign="top" width="33%"><a href="personal/catalog-redesign"><img src="personal/catalog-redesign/docs/screenshot.png" width="260" alt="Catalog list on the left with the detail panel open on a plugin whose hero image fills the panel header" /></a><br /><sub><a href="personal/catalog-redesign"><strong>Catalog Redesign</strong></a><br />Four kinds in one list, panel open on a hero</sub></td>
  </tr>
</table>
</div>

## Personal and public

This repository keeps two trees.

**[personal/](personal/README.md)** is the full-featured edition I run. These builds may reach into Hermes Desktop internals: app DOM, persisted app keys, raw bridge calls. A Desktop update can break them. They sit outside the plugin SDK contract, so install them only if you accept that risk. The pack pins this tree.

**[public/](public/README.md)** is the catalog edition. These builds stay inside the Hermes plugin SDK (`ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`) so they can be listed. When Desktop has no hook yet, the public copy drops that surface. All but Queue Container Fix have one, because that plugin is entirely a restyle of app markup.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/<id>
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/<id>
```

The pack command in [Install](#install) pulls `personal/<id>`.

Agent rules for these trees live in [AGENTS.md](AGENTS.md). Catalog blockers for the personal editions live in each plugin's `LIMITATIONS.md`.

## What's in the Pack

Each row links the personal edition you get from the pack, plus the public catalog edition where one exists.

Nineteen plugins are pinned in `hermes-pack.yaml` (pack version 1.27.22). **better-capabilities**, **prompt-enhance** and **voice-gate** live in this repo but are **not** in the pack, so install any of them separately if you want it. The pack pins the personal tree for all nineteen.

### Status Bar

| Plugin | What you get |
| --- | --- |
| [Provider Status](personal/provider-status/README.md) · [public](public/provider-status/README.md) | Status-bar quota used/remaining. DeepSeek and GLM peak/off-peak gauges with countdowns. Multi-account. Rotate on low quota or reset day. Grok/Codex OAuth. Providers: Tavily, OpenCode Go, DeepSeek, GLM (z.ai), OpenRouter, Grok (xAI), Codex (OpenAI), OpenAI, Anthropic, Groq, Cerebras, Moonshot Kimi, MiniMax, Google Gemini, Hugging Face, Mistral, Qwen. |
| [Iteration Budget Meter](personal/iteration-budget-meter/README.md) · [public](public/iteration-budget-meter/README.md) | Per-turn N/budget while work runs. Hover and click for request stats. |
| [Reasoning Switch](personal/reasoning-switch/README.md) · [public](public/reasoning-switch/README.md) | Cycle reasoning effort from the status bar, with colors and per-level prompt demote. |
| [Radio Plus](personal/radio-plus/README.md) · [public](public/radio-plus/README.md) | Live radio with a station list you own: edit a name and a stream address, add any stream, search Radio Browser, its popular list, the Shoutcast directory and TuneIn, see the track the stream announces, play HLS through a bundled hls.js (personal edition), and read why a station failed. An extended edition of the bundled Radio plugin. |

### Tools and Memory

| Plugin | What you get |
| --- | --- |
| [Intelligent Tool Break](personal/intelligent-tool-break/README.md) · [public](public/intelligent-tool-break/README.md) | `/break`, `/break {msg}`, and `/again`. Desktop strip. Turn stays alive. |
| [Vercel Agent Desktop Support](personal/vercel-agent-desktop-support/README.md) · [public](public/vercel-agent-desktop-support/README.md) | Operate Windows apps through the accessibility tree: click, fill, select, toggle, scroll, key combos, windows, clipboard. Headless by default, so it never takes focus or the cursor. **Windows only.** |
| [Memory Review](personal/memory-review/README.md) · [public](public/memory-review/README.md) | Checkbox staged memory writes. Approve or reject from a dialog. |
| [CDP Manager](personal/cdp-manager/README.md) · [public](public/cdp-manager/README.md) | Launch, stop, and recheck local Chrome CDP ports from the status bar, with a profile per port and one port a backend supervisor keeps alive. The `cdp` tool does the same from chat and repairs a Chrome profile-picker launch. |
| [Jev Routing](personal/hermes-jev-routing/README.md) · [public](public/hermes-jev-routing/README.md) | Per-turn model routing from TypeSafe Jev. The listed edition rewrites the model and the reasoning level on the request the turn is already bound to, and reports a pick on another provider rather than sending it; the personal edition moves the live session and also reads the provider catalogue, Codex quota and private pricing. |

### Capabilities and catalog

| Plugin | What you get |
| --- | --- |
| [Catalog Redesign](personal/catalog-redesign/README.md) · [public](public/catalog-redesign/README.md) | One wide row per skill, plugin, connector and tool, with a hover preview, real artwork from the catalog or the plugin's own folder, and a detail panel that carries the hero image, a section rail and the on/off switch. Switches on plugins, skills, toolsets and connectors. Leaves the native Capabilities page alone. |

### Sessions and Sidebar

| Plugin | What you get |
| --- | --- |
| [Better Session Appearance](personal/better-session-appearance/README.md) · [public](public/better-session-appearance/README.md) | Idle color, bold, and icons: one for the idle dot, or one for each of the six status dots. A settings switch lets the in-progress dots wear the session color. Auto Rules by title keywords. |
| [Sidebar Manager](personal/sidebar-manager/README.md) · [public](public/sidebar-manager/README.md) | Hide and reorder nav rows and session sections. |
| [Drag to Pin Session](personal/drag-to-pin-session/README.md) · [public](public/drag-to-pin-session/README.md) | Drag pin/unpin with lasting order. |
| [Session Retitler](personal/sessionretitler/README.md) · [public](public/sessionretitler/README.md) | Retitles the session every N titleable user messages, from the latest exchanges. A title you set yourself is never touched. |
| [Scroll on Switch](personal/scroll-on-switch/README.md) · [public](public/scroll-on-switch/README.md) | Snap to bottom on session switch. Does not fight streaming. |

### Composer

| Plugin | What you get |
| --- | --- |
| [Opaque Composer](personal/opaque-composer/README.md) · [public](public/opaque-composer/README.md) | Solid composer while the transcript scrolls behind it. |
| [Queue Container Fix](personal/queue-container-fix/README.md) | Moves a queued prompt's expand, edit, steer and send controls from the end of the row to the start of its first line, visible without hovering. Personal only: it restyles app markup. |
| [Next Steps](personal/next-steps/README.md) · [public](public/hermes-next-steps/README.md) | Clickable next steps under a reply: tick several and one send delivers them together, a Recommended tag on the options worth taking now, an amber RISKY pill on the ones that could damage something, a dim second line where a label alone would misread, and carried-forward options from earlier replies. The personal edition animates the chip border while a reply works and jumps back to the reply that offered a carried option. |
| [Prompt Enhance](personal/prompt-enhance/README.md) · [public](public/prompt-enhance/README.md) | Rewrite a composer draft from a saved prompt library and put the finished prompt back in the field. **Not in the pack; enable separately.** |

### Writing

| Plugin | What you get |
| --- | --- |
| [Voice Gate](personal/voice-gate/README.md) · [public](public/voice-gate/README.md) | Reviews changed prose with 75 mechanical families and optional model review against all 110 humanizer patterns. Protects source material, limits revision requests to two opportunities, and supports Vale from an executable you approved, file exceptions, writing contexts, and a grouped settings page. Personal also loads approved writing profiles, drafts profiles from curated samples, and records bounded local diagnostics. **Not in the pack; install separately.** |

### Reading and posting

| Plugin | What you get |
| --- | --- |
| [RSS Reader](personal/rss-reader/README.md) · [public](public/rss-reader/README.md) | Three-column reader. Folders, mute/search, capture. Optional Hermes tools and ticker. |
| [Reddit](personal/reddit/README.md) · [public](public/reddit/README.md) | Account access, a searchable local save library with source summaries and notes, a Desktop browser, background cleanup and 22 reading/management tools. Standalone release; catalog admission is blocked by missing host OAuth transport. |

Three plugins in this repo are not in the pack and are installed separately: **better-capabilities**, **prompt-enhance** (Composer table), and **voice-gate** (Writing table). Every other plugin above is pinned by the pack.

Retired and on-hold plugins live in [RETIRED.md](RETIRED.md).

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

For a single plugin, follow that plugin's README. For **reasoning-switch** and **prompt-enhance**, use the README because the pack does not install them.

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
- [Provider Status](personal/provider-status/README.md)
- [Intelligent Tool Break](personal/intelligent-tool-break/README.md)
- [Iteration Budget Meter](personal/iteration-budget-meter/README.md)
- [Reasoning Switch](personal/reasoning-switch/README.md) (not in the pack)
- [Better Session Appearance](personal/better-session-appearance/README.md)
- [Sidebar Manager](personal/sidebar-manager/README.md)
- [Drag to Pin Session](personal/drag-to-pin-session/README.md)
- [Scroll on Switch](personal/scroll-on-switch/README.md)
- [Opaque Composer](personal/opaque-composer/README.md)
- [Queue Container Fix](personal/queue-container-fix/README.md)
- [Prompt Enhance](personal/prompt-enhance/README.md) (not in the pack)
- [Memory Review](personal/memory-review/README.md)
- [CDP Manager](personal/cdp-manager/README.md)
- [RSS Reader](personal/rss-reader/README.md)
- [Session Retitler](personal/sessionretitler/README.md)
- [Radio Plus](personal/radio-plus/README.md)

## Support

Report problems or follow releases through [@ApoMakesMods](https://x.com/ApoMakesMods) on X.

## License

[MIT](LICENSE) © Apostol Apostolov

This is an independent community project. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or Hermes Agent. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
