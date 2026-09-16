# RSS Reader — TODO

Working list for this plugin. Ideas and rejected scope live in `PROPOSAL.md`,
the code audit in `AUDIT.md`.

- Live copy: `%LOCALAPPDATA%/hermes/plugins/rss-reader/`
- Repo: `C:/git/hermes-agent-awesome-plugins/plugins/rss-reader/`
- Ship a slice: edit live → `node --check` a `.mjs` copy → `node scripts/lint-plugin.mjs <live plugin.js>` → copy live to the repo → commit and push `main` → toggle the plugin in Capabilities.

---

## Done

- **Drag reorder with a live gap.** The subscription list previews the landing
  spot while a row is in the air, so the rows around it move aside instead of
  the order only changing after the drop. Technique follows
  `AI-Provider-Library-for-Foundry-VTT/scripts/ui/route-drag.mjs`: the source
  slot closes and the destination slot opens. Here it rides the HTML5 drag
  events the list already had. `previewFeedOrder` and `feedDropIndex` are
  module-scope helpers; the dragged row is rendered styled at the insertion
  index; a grab with no movement skips the round trip. Verified on the real
  helpers (13 order cases) and by measuring the stack in a render: every shift
  is a whole row, no overlap or hole, exact restore on abort.

## 1. Folders

**Status:** the data exists, the UI does not.

`feed.folder` is real and already round-trips: OPML import writes it, `POST /feeds`
accepts `{ url, folder }`, feed titles read `folder / title`, and OPML export
rebuilds the nested outlines. The left nav ignores all of it and maps
`library.feeds` to a flat `.rss-feed-row` list with grip-reorder and trash, so a
folder you imported is invisible and unmanageable.

- Nav: group feeds under folder headings with the folder's unread count, feeds
  with no folder staying loose. Keep the heading style consistent with the
  existing `rss-nav-heading` row that holds the pencil toggle.
- Edit mode: drag a feed into another folder. The drag already persists as
  `POST /feeds/reorder` with `{ order }`, so the payload has to carry the folder
  as well. Add rename, create, and delete for a folder in the same mode.
- OPML must round-trip through the grouped nav: import → grouped → export gives
  the same nesting.
- No regressions in filter/search, the `.rss-nav button` width, or the pencil
  alignment (both were fixed deliberately, see the skill).

First slice: render the nav from a `folder → feeds` map with headings only, no
drag or folder management. That is a pure render change on existing data.

## 2. Saved → Hermes preference analysis

**Status:** not started. Saved works in-app; Hermes cannot see it.

`is_saved` is a live feature: the star on a card and in the article pane, the
`saved` view, and saved posts survive both unsubscribe and the 300-post
retention trim. Nothing outside the plugin ever reads it, so the strongest
signal Apo produces (what he stars, what he lets fall away) never reaches the
model.

- Expose the saved set to Hermes first. The whole library is one IndexedDB blob
  (`hermes-rss-library`, store `libraries`, keyed per profile), which a Hermes
  skill cannot read: this needs an export path (saved articles as JSON through
  the plugin's shell bridge) or a Hermes-side reader for that store. Nothing
  downstream is possible until this exists.
- Preference analysis: turn saved vs read vs ignored into a profile (feeds,
  authors, topics, mute history) and feed it into grading. The rubric and tag
  table already live in a skill (`rss-importance-grading`), so that is where the
  loop closes: what Apo saves should move the rubric.
- Decide the write path: auto-update the rubric, or emit a review report for Apo
  to apply. A model pass that edits a skill unattended needs a guard, so the
  first cut should be the report.
- Decide whether this is the same system as the "more like this / less like this"
  taste profile in `PROPOSAL.md` §3, or two systems. Do not build both.
