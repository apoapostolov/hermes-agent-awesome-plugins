# Changelog

## [1.0.0] - 2026-08-30

First pack. Two Hermes Agent plugins, pinned to exact SHAs.

### Added

- **provider-status:** quota chips across providers, Grok/Codex OAuth, key-pool rotation, and per-key reset-day rotation.
- **hermes-break:** `/break` and `/again` kill a hung spawn without aborting the turn. `/again` reissues that call once.

### Upgrade notes

- Hermes Agent `>= 0.3`.
- Install with `hermes plugins pack install` of the raw `hermes-pack.yaml` URL. There is no GitHub Release for this pack.
