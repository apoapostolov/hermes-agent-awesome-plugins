# Changelog

## [rss-reader 1.1.0] - Unreleased

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
