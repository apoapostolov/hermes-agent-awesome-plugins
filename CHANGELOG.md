# Changelog

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
