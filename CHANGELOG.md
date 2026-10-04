# Changelog

The pack and its plugins have separate version numbers. Entries below name
the component that changed; a plugin patch does not imply a new pack release.

## [Unreleased]

### Added

- hermes-jev-routing 0.1.0. Personal edition switches the live session before the client sends. Public edition rewrites the model only inside the provider already bound to the request. Neither edition is in the pack.

### Changed

- hermes-jev-routing. A Codex row is skipped when a live reading is below the stricter of the provider floor and the row floor. A missing, stale, or reset reading follows onUnknown. A confirm tier is held when onTimeout is reject. `/jev-routing suggest` previews a scores file and can save a generated layer that does not override a named hand chain.

- The chip refuses a click on a new chat instead of silently swallowing it, and its tooltip names the door that works there: the composer's Thinking menu, whose pick ships with `session.create`. A remembered pick could never be applied, because `session.create` reads the app's composer atom and not a plugin's variable.
- Removed the pending-pick machinery, which was unreachable once the chip stopped pretending.

Tracked upstream: https://github.com/NousResearch/hermes-agent/issues/132697


## [reasoning-switch 1.1.4] - 2026-10-03

Two more defects from a live report.

### Fixed

- The chip is inert on a brand-new chat, before its first send. A draft has no runtime session id until then and `config.set reasoning` is session-scoped, so there is nothing to scope the write to. See Unreleased for the honest behavior that replaced a pending-pick mechanism which could not land.




## [reasoning-switch 1.1.3] - 2026-10-03

Two defects from a live report.

### Fixed

- Clicking the chip on a session running a level outside the rotation no longer does nothing. The session's level comes from the gateway, so an external pick (`/reasoning`, the composer menu) or a row unchecked in the dialog left `displayed` absent from the rotation; the old code bailed out and the chip was dead until the dialog was reopened. It now steps up to the nearest rotation entry, or to the bottom when the session sits above every entry, so there is always a way off.
- The chip label no longer wraps on `Extra High`. The statusbar reuses the app's own compact spellings (`XHigh`, `Med`, `Min`, `Off`) and the label and counter carry `whitespace-nowrap`. The dialog keeps the full names.


## [reasoning-switch 1.1.2] - 2026-10-03

The chip now reads the level the session is actually running, instead of guessing it from a read it could not trust.

### Fixed

- Clicking the chip no longer looks like it worked when the gateway refused the write. `config.set` answers the value it accepted, so a refusal leaves the chip on the real level.
- The 4-second reconciler no longer paints the profile default back over a pick the user just made. It cannot tell a pinned session override from an inherited default, so `session.info` is now the signal that repaints the chip.
- A pick changed elsewhere (the composer reasoning menu, `/reasoning`) updates the chip and the dialog's current marker, so the prompt-limit bookkeeping follows the session.
- Switching sessions clears the previous chat's level while the new read is in flight, so the chip never shows the other session's effort.
- A clamped pick reads as both ends (`Ultra→Max`) and the tooltip names the wire level, so a Hermes-internal step is never presented as a wire level the route does not have.
- Overlapping reads share one promise per session, so a slow read started before a click cannot repaint a level the user rotated away from.

The auto-demote path settles on the accepted level for the same reason.


### Changed

- **provider-status:** personal extra accounts live in plugin `library.env`. The plugin does not read or write lifestyle `.env`. Hermes `.env` still gets the active runtime key, and numbered siblings for native providers when Apply Changes is on. Tavily extras stay in the library; only the active Tavily key is written to Hermes `.env`.

### Removed

- **compact-reasoning-label:** removed from personal and public. The Desktop model pill no longer includes the reasoning effort. That word lives on the reasoning pill, so the plugin's strip did nothing on current builds. The old trees stay in git history.

## [intelligent-tool-break 1.3.4] - 2026-10-03

The public edition keeps its settings in `ctx.storage` instead of `window.localStorage`, so it stays inside the plugin SDK.

### Changed

- Public edition: color grades and the hidden-tools list read and write through `ctx.storage`, captured in `register(ctx)` and released in `ctx.onDispose`.
- Public edition: the settings dialog subscribes to a store version counter, so a change made in one surface re-renders the others. `better-session-appearance` already used this pattern.
- Personal edition is unchanged and keeps its `localStorage` behavior.

Stored values are treated as untrusted: a wrong type, a null, an out-of-range number, or a storage backend that throws all fall back to the defaults instead of breaking the strip. When `ctx.storage` is unavailable the change stays session-local.

Verified against the migrated helpers with a fake storage backend: defaults with no backend, round-trips for both keys, values stored as objects rather than JSON strings, five corrupt-input cases, the 3600-second clamp, a throwing backend, and the React subscriber notification. 18 checks, all passing.

## [provider-status 1.5.12] - 2026-10-03

z.ai renamed the quota limit type to `CREDIT_LIMIT`, so the GLM fetcher stopped matching any window and the chip reported a full quota while the account was close to its weekly cap.

### Fixed

- Both editions: `CREDIT_LIMIT` is accepted next to `TOKENS_LIMIT`, and `unit` still decides the window (3 = 5h, 6/4 = weekly, 5/7 = monthly).
- Both editions: quota windows are emitted only when the API actually reported them. The `0.0` defaults used to append a phantom monthly row reading 100% remaining.
- Both editions: the headline percentage is omitted when no burst window was reported. Sending `null` was the wrong fix, because the desktop fallback reads `Number(null)` as `0` and would have drawn a full 5h window.
- Public edition: the weekly window reaches the status-bar chip. GLM now uses the multi-window renderer already used by OpenCode Go and Codex, so both the burst and the weekly allowance are visible.
- Personal and public versions are aligned at 1.5.12. They had drifted (personal 1.5.10, public 1.5.11).

Personal keeps its single-value GLM chip, so its chip still shows the 5-hour headline and the weekly allowance stays in the Providers dialog.

## [prompt-enhance 1.1.1] - 2026-10-01

The listed edition reads and writes the composer through the draft API, so enhance, undo, and replace keep working when the Desktop markup moves.

### Changed

- Public edition: enhance, undo, and replace use the composer draft API.
- Public edition: Add on a saved prompt appends to the draft. Personal Add still inserts at the caret.

## [prompt-enhance 1.1.0] - 2026-09-22

The library header can set a thinking level for the enhance call. The session model stays as it is.

## [better-session-appearance 1.2.2] - 2026-10-01

Saved Auto Rules now reach the sessions they were written for.

### Fixed

- Personal edition: a rule applied only when a session's title changed, so it
  never reached the sessions already in the list. The applied-state check now
  tracks the matched rule instead of a title diff, and a rule lands as soon as
  its row exists. Saving or removing a rule in the panel applies it right away
  instead of waiting for the title to change.
- A session that already carried a rule is left alone on further observer
  passes, so the sidebar list does not rewrite stored state while idle.

## [sidebar-manager 1.0.1] - 2026-10-01

Sidebar Manager keeps working after a Hermes desktop update changed how the sidebar nav buttons are marked.

### Fixed

- Personal edition: the editor glyph reappears next to New session and nav rows become clickable again. Every nav row now wraps its button in a context-menu trigger, which replaced the button's own `data-slot` value, so the editor's selector matched nothing and the plugin did nothing at all. Nav buttons are now matched on the attribute that survives.
- Personal edition: the README's nav row list named a row the app does not have.

### Changed

- Public edition: its README described the personal editor, including session-section hiding, drag grips and the edit-mode glyph. None of that is in the listed edition, which drives core nav rows through the SDK's sidebar prefs area from a statusbar dialog. The README now matches the shipped behavior and states the section limit.

## [provider-status 1.5.10] - 2026-09-30

Deleting a saved key in the personal Providers dialog now stays deleted. The
next status poll no longer restores it from the local credential files.

### Fixed

- Personal edition: a removed key is cleared from the library and Hermes
  carriers. A fingerprint prevents a stale file from importing it again,
  without storing the raw key in the removal record.
- The active key and numbered slots stay valid after a deletion, including
  when a middle key is removed.
- Public edition: the per-key delete control is gone because this build cannot
  update the personal credential files. Removing a whole provider row remains
  available.

Restart Hermes Desktop after updating; the Python component does not hot-reload.

## [rss-reader 1.1.0] - 2026-09-24

RSS Reader moves browser frames and ticker events onto the desktop SDK, restores the headline ticker at launch, and tightens YouTube cookie handling.

### Changed

- **rss-reader:** Use the desktop plugin event bridge instead of a commands-file poll, and the sandboxed frame API for the browser and YouTube player.

### Fixed

- **rss-reader:** Restore the marquee class on the ticker track when reduced motion is off, so headlines scroll at launch.

### Security

- **rss-reader:** YouTube cookie settings accept pasted header or Netscape export text. Unix-rooted and Windows drive-rooted paths are rejected, so the dashboard no longer reads local files or forwards their contents to YouTube.

## [provider-status 1.5.9] - 2026-09-24

DeepSeek's pricing period and GLM's peak/off-peak schedule now appear beside their status values, each with a countdown to the next change.

### Added

- **provider-status:** A color-coded speedometer shows whether DeepSeek is in peak hours. Its native hover shows the time until the next period change. Peak hours are 01:00–04:00 and 06:00–10:00 UTC on weekdays. Weekends and listed 2025 and 2026 Chinese public holidays are off-peak. The built-in holiday calendar ends on 2026-12-31.
- **provider-status:** GLM chips show a peak/off-peak speedometer and countdown based on Z.AI's documented Coding Plan schedule, even when the quota response omits a weekly window. Peak hours are Monday-Friday 14:00-18:00 Singapore time (UTC+8); off-peak model use consumes half the standard credit rate.

### Changed

- **provider-status:** Personal, public, and pack overview documentation now lists all 17 registered providers.

## [rss-reader 1.0.9] - 2026-09-23

Tighter grading calibration, a reader-interests skill block, and a `reclassify` action that re-judges up to 720 articles per run.

### Added

- **rss-reader:** version `1.0.9` (both editions). The grading skill gains a Reader interests block: an editable ```interests fence where the reader lists their own topics, one per line. Grading treats a strong interest match carrying something usable (product, tool, opportunity, resource) as interesting; bare topic mentions stay normal and interests never escalate to important. The in-plugin scaffold that seeds a missing skill includes the same block.
- **rss-reader:** `reclassify` Hermes tool action (both editions). Re-runs classification across up to 720 articles, including already-tagged ones, so rubric changes apply retroactively. It processes distinct batches and reports when more articles remain for a later run.
- **rss-reader:** the duplicate `mute` tool action is removed (both editions); `add_filter` is the single rule-creation path for keyword and tag mutes. The `/rss mute <keyword>` slash command is unchanged.
- **sessionretitler** (formerly `session-retitler`): version `1.1.0`. Retitles the session every N titleable user messages from the latest exchanges (llm-rank rewrites, user titles untouchable). Now pinned in the pack (pack `1.16.0`).

### Changed

- **rss-reader:** tightened grading calibration against over-flagging. Important now requires a fact that changes the reader's own decision or action within days (direct security, privacy, legal, or financial threat, or first-party news about products they use); general money, law, and politics news without that tie is explicitly excluded. Interesting requires durable insight; ordinary coverage, opinion takes, and trend roundups excluded. New scarcity rule: roughly 1-2 important and 4-6 interesting per day, more than 2 or 6 in a batch means re-judge the weakest flags as normal. Applies to the skill, the scaffold, and the fallback rubric in both editions.

### Fixed

- **rss-reader:** Unread or Starred can now be combined with a feed or folder. Switching views keeps the selected scope, and selecting a feed or folder keeps the current view. Feed and folder changes return the article list to the top.
- **cdp-manager:** version `1.0.0` (the pre-release `1.0.1` tag is retired, never shipped). `config.json` now writes inside the plugin directory instead of the shared `$HERMES_HOME/plugins/` folder, and the default Chrome profile path derives from `%LOCALAPPDATA%` instead of a hardcoded personal path. The public edition's repo link points at `public/cdp-manager`. Pack re-pinned to the fix commit (pack `1.17.0`); catalog entry updated with `platforms: [windows]` and corrected profile-path wording.

## [rss-reader 1.0.8] - 2026-09-22

YouTube videos play in the reader, playlists run oldest first, Reddit chips subscribe, and Settings Advanced covers User-Agent plus YouTube cookies.

### Added

- **rss-reader:** version `1.0.8`. YouTube posts play in a 16:9 pane with chapter timestamps when the feed description lists them. Playlist feeds list oldest first. Settings Advanced adds a User-Agent preset and a YouTube cookie field used on YouTube HTTP fetches. Subscribe chips include YouTube and Substack rows, plus Google AI in Popular starters.

### Fixed

- **rss-reader:** Reddit community chips subscribe through the subreddit Atom feed. VentureBeat AI 429'd on the default User-Agent and is replaced by Google AI.

### Changed

- **rss-reader:** the public listing edition keeps the 1.0.8 YouTube player, playlists, User-Agent, cookies, Reddit Atom, and starter chips. Self-improvement, paywall mirrors, webview, layout-store reads, and the private gateway preview import stay personal-only.

## [rss-reader 1.0.7] - 2026-09-20

Subscribe accepts YouTube and Substack pages, a folder view includes nested feeds, and each feed has its own capture and ticker settings.

### Added

- **rss-reader:** version `1.0.7`. Paste a YouTube channel, `@handle`, `/user/`, playlist, or a Substack page into Subscribe. Opening a folder shows that folder and its children. Edit mode adds a pencil per feed: name, full-article download, paywall checks, ticker visibility, and an optional refresh override.

### Changed

- **rss-reader:** Settings Main **Default View** sits in Reading, above Mark Articles Read When Opened. The Subscribe hint is two lines, with Folder and New folder lined up to the URL field.

## [rss-reader 1.0.6] - 2026-09-20

Folder order is yours to set, and old posts leave when the feed no longer lists them.

### Added

- **rss-reader:** version `1.0.6`. Edit mode adds a gripper on named folders so you can drag them into a new order. That order is saved and used after reload. Ungrouped stays first. Feeds inside a folder keep their own order. Settings Main **Keep Articles** (7 to 365 days, default 14) drops posts older than that limit when the live feed no longer lists them, and deletes their full-article cache. Starred posts stay. Slow feeds that still list an old item keep it.

## [1.14.0] - 2026-09-18

### Added

- **better-session-appearance:** version `1.2.0`. Auto Rules on the Icon header save the current color, bold, and idle icon against title keywords (comma or space, all words must match, case-insensitive). Each rule row has Edit and Remove. Future sessions whose titles contain those words pick up that look. The Appearance submenu grows so the icon grid is no longer trapped behind the old 320px cap.

## [1.13.1] - 2026-09-17

### Added

- **rss-reader:** version `1.0.3`. Optional Register Hermes Tools adds one `rss` tool so Hermes can read and find posts, tag or untag them, manage keyword and tag filters, and change subscriptions. `/rss find` returns matching titles and post text. `/rss tag`, `/rss untag`, `/rss mute tag`, and `/rss unmute` cover the same library from chat.

## [1.12.1] - 2026-09-17

### Fixed

- **better-capabilities:** version `1.0.1`. Package (zip) uses the skill title currently shown in the detail pane, so switching from one learned skill to another no longer downloads the first skill the row was painted with.

## [1.12.0] - 2026-09-17

### Added

- **better-capabilities:** version `1.0.0`. Adds a delete control next to the Capabilities folder icon, a Package (zip) button between Edit and Archive on a learned skill, Recycle Bin delete, and a zip of the skill folder including references.

## [1.11.0] - 2026-09-17

### Added

- **compact-reasoning-label:** version `1.0.0`. The composer's model pill shows only the model name; the duplicated thinking-level word is stripped so it lives only in the reasoning pill beside it. Idempotent re-strip survives every React repaint without an observer loop.

## [1.10.3] - 2026-09-16

### Added

- **rss-reader:** version `1.0.0` → `1.0.1`. Adds `/rss refresh`, refresh-period settings, feed-wide mute commands, session-based grading refinement using the `rss-reader-plugin` skill, website/feed discovery for subscriptions, scoped unread triage, grouped digest sessions, and read-only feed health diagnostics. The legacy `rss-reader-grading` and `rss-importance-grading` skill slugs map to the new name.

## [1.10.2] - 2026-09-13

### Changed

- **memory-review:** 1.2.1. Approve skips dead replace/remove ops. An over-budget error shows Consolidate above Reject/Approve. Store meters refresh from `/state` without waiting on slash.

## [1.10.1] - 2026-09-13

### Changed

- **memory-review:** 1.1.0. Memory and User meters share one row. User sits on the right. A small bar follows the percent.

## [1.10.0] - 2026-09-13

### Changed

- **memory-review:** renamed from `memory-review-command`. Opens a review dialog instead of sending `/memory pending`. Rows show store and action glyphs, plus dim fill bars for each store.

## [1.9.0] - 2026-09-12

### Added

- **memory-review-command:** a native shell-menu command that sends `/memory pending` through the composer when a staged memory write is waiting or a store is full. The row stays grayed out when memory is clean and never approves or discards entries.

## [1.8.0] - 2026-09-08

### Added

- **iteration-budget-meter:** status-bar chip that shows the focused session's per-turn iteration usage (N/60) while a turn runs. Amber near the cap, red at cap. The popover shows average tool calls per request, the ratio of requests hitting the max, and a suggested new ceiling when the data supports raising it. Counts only the current turn, so the number can never exceed the cap.

## [1.7.0] - 2026-09-01

### Fixed

- **scroll-on-switch:** restore explicit activation tracking after removing transcript observers. Hidden-to-visible and newly mounted session switches now scroll correctly without reacting to new messages.

## [1.5.0] - 2026-09-01

### Fixed

- **scroll-on-switch:** only scrolls when switching to a session. New messages and AI streaming no longer interrupt manual scrolling.

## [1.4.0] - 2026-09-01

### Added

- **scroll-on-switch:** keeps active session transcripts at the newest message after switching sessions or receiving a new message. It handles newly mounted sessions and late-rendered message nodes without preventing manual scrolling after the update settles. Desktop-only.

## [1.3.0] - 2026-09-01

### Added

- **opaque-composer:** keeps the desktop composer solid while scrolling so conversation text stays readable. Desktop-only and upgrade-safe through a small reversible stylesheet plugin.

## [1.2.3] - 2026-09-01

### Fixed

- **tool-break:** version `1.2.1` → `1.2.2`. The backend pid watcher snapshotted the whole system process table every 200ms for the entire life of every tool call (~12ms of locked work per snapshot on Windows), which stalled tool start and made typing lag. The watcher now runs only for the first 2.5 seconds of a call, then stops; late spawns are still caught at `/break` time. Combined with the 1.2.1 desktop backoff, an idle session now does near-zero plugin work.

## [1.2.2] - 2026-09-01

### Changed

- **tool-break:** version `1.2.0` → `1.2.1`. Desktop bar no longer polls `/break-status` every second and re-renders 4x/second while idle: the poll backs off to 5s when nothing is in flight, and the elapsed-time clock runs only while tools are visible. Behavior while a tool is in flight is unchanged.

## [1.2.1] - 2026-09-01

### Changed

- **provider-status:** version `0.1.0` → `1.0.0`.

## [1.2.0] - 2026-09-01

`hermes-break` is now `tool-break`. The pack requires Hermes Agent 0.21.0.

### Changed

- **tool-break:** renamed from `hermes-break`. Commands stay `/break`, `/break {message}`, and `/again`.
- Plugin descriptions match the community-index copy.
- Manifests declare `manifest_version: 2`, `api_version: 1`, homepage, and tags.
- Install docs require Hermes Agent `>= 0.21.0` (shareable plugin packs).

### Upgrade notes

- Reinstall from the pack, or disable `hermes-break` and enable `tool-break`.
- Desktop strip settings live under `localStorage` keys `tool-break.grades` and `tool-break.hide` (old `hermes-break.*` keys are not read).

## [1.1.0] - 2026-08-30

Adds `drag-to-pin-session` to the pack.

### Added

- **drag-to-pin-session:** the Pinned section of the Sessions sidebar becomes a drag container. Drag a session row in to pin it, drag a pinned row out into Sessions to unpin it. Desktop-only, hot-reloads, no rebuild.

### Changed

- Pack description and README now cover four plugins.
- `hermes-awesome-plugins-sync` mirrors `drag-to-pin-session`, and relocates a root `plugin.js` to `desktop/plugin.js` for any plugin rather than only `better-colors`.

## [1.0.0] - 2026-08-30

First pack. Three Hermes Agent plugins, pinned to exact SHAs.

### Added

- **provider-status:** quota chips across providers, Grok/Codex OAuth, key-pool rotation, and per-key reset-day rotation.
- **hermes-break:** `/break` and `/again` kill a hung spawn without aborting the turn. `/again` reissues that call once.
- **better-colors:** session list appearance. Color and bold titles, extra Appearance colors, idle-bullet glyphs.

### Upgrade notes

- Hermes Agent `>= 0.3`.
- Install with `hermes plugins pack install` of the raw `hermes-pack.yaml` URL. There is no GitHub Release for this pack.
