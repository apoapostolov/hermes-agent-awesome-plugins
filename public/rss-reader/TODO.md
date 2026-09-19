# RSS Reader — TODO

Working list for this plugin. Ideas and rejected scope live in `PROPOSAL.md`,
the code audit in `AUDIT.md`.

- Live copy: `%LOCALAPPDATA%/hermes/plugins/rss-reader/`
- Repo: `C:/git/hermes-agent-awesome-plugins/plugins/rss-reader/`
- Ship a slice: edit live → `node --check` a `.mjs` copy → `node scripts/lint-plugin.mjs <live plugin.js>` → copy live to the repo → commit and push `main` → toggle the plugin in Capabilities. Do not bump `plugin.yaml` version unless Apo asks.

---

## Still open

No current items. Add new implementation slices here when they are approved.
New AI-first ideas belong in `PROPOSAL.md` first.

---

## Not in this file

AI-first slices that were never on this TODO live in `PROPOSAL.md`: digest,
inline composer, full-text index, multi-select, feed health, library JSON
backup, compact density. Do not treat those as open items here until they
are added on purpose.
