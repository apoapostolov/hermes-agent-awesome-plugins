# RSS Reader — TODO

Working list for this plugin. Ideas and rejected scope live in `PROPOSAL.md`,
the code audit in `AUDIT.md`.

- Live copy: `%LOCALAPPDATA%/hermes/plugins/rss-reader/`
- Repo: `C:/git/hermes-agent-awesome-plugins/plugins/rss-reader/`
- Ship a slice: edit live → `node --check` a `.mjs` copy → `node scripts/lint-plugin.mjs <live plugin.js>` → copy live to the repo → commit and push `main` → toggle the plugin in Capabilities. Do not bump `plugin.yaml` version unless Apo asks.

---

## Done

- **Drag reorder with a live gap.** The subscription list previews the landing
  spot while a row is in the air. `previewFeedOrder` and `feedDropIndex` are
  module-scope helpers; a grab with no movement skips the round trip.
- **Folders in the left nav.** Feeds group under folder headings with unread
  counts. Empty folder is Ungrouped. Headers collapse. Pencil mode drags a
  feed between open folders and onto a closed header (lands at the top).
  `previewNavFeeds` keeps the source row mounted; `applyFeedMove` writes
  folder plus order through `POST /feeds/reorder`. OPML import/export already
  nested outlines, so grouped nav round-trips the same nesting. Pencil mode
  also creates, renames, and deletes folders (delete moves feeds to Ungrouped
  or another folder).
- **Mute rules and list funnel.** Phrase plus folder/feed scope, hit counts,
  filter glyph in the list head.
- **AI tagging.** Preference skill `rss-reader-grading` (old slug
  `rss-importance-grading` still maps). Pills and card tints from the skill
  tag table. Grades cache by url/identity and are not sent again. Order by
  Importance sorts by tag rank 0-100, then date.
- **Load More and list jump.** Load More stays centered and does not reset
  the middle column. Past the twentieth card, a square arrow jumps to the top
  and can return.

---

## Still open

Audit against the live plugin. Only leftover items from this file.

### 1. Saved → Hermes preference analysis

**Status:** not started. Saved works in-app; Hermes cannot see it.

`is_saved` is live: star on the card and article pane, `saved` view, saved
posts survive unsubscribe and the 300-post trim. Nothing outside the plugin
reads that set.

Still missing:

- Expose the saved set to Hermes. The library is one IndexedDB blob
  (`hermes-rss-library`, store `libraries`, keyed per profile). A skill cannot
  read it. Needs an export path (saved articles as JSON through the plugin
  shell bridge) or a Hermes-side reader for that store.
- Preference analysis: turn saved vs read vs ignored into a profile (feeds,
  authors, topics, mute history) and feed it into grading. The rubric lives in
  `rss-reader-grading`. First cut should be a review report, not an unattended
  skill edit.
- Decide whether this is the same system as “more like this / less like this”
  in `PROPOSAL.md` §3, or two systems. Do not build both.

---

## Not in this file

AI-first slices that were never on this TODO live in `PROPOSAL.md`: digest,
inline composer, full-text index, multi-select, feed health, library JSON
backup, compact density. Do not treat those as open items here until they
are added on purpose.
