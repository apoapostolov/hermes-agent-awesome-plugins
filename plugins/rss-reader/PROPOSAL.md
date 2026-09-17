# Proposal: AI-first RSS Reader

**Goal:** Turn this plugin into a reader where the model is a first-class part of inbox, not a button you remember to press.

**Now:** Three-column Hermes Desktop plugin. Local IndexedDB library. Feed refresh + optional background capture. Discuss / Summary / Evidence open Hermes chats. Keyboard j/k/s/d. OPML, mute, saved searches.

---

## Already in place (do not rebuild)

- Subscriptions with folders, drag reorder, OPML import/export
- Unread / saved / all views, mute rules, saved searches
- Reader-mode capture queue (2 concurrent, persisted, skip already captured)
- Full-text cache until the article leaves the list
- Rich HTML/markdown (lists, tables, images, lead image + list thumbnail)
- Discuss, summarize, check sources as explicit Hermes actions
- Google Reader keys, compact Filters/Settings chrome

## Missing for an AI-first reader

Ranked by leverage. Each item is one shippable slice.

### 1. Inbox that the model triages

Today every new post is equal. An AI-first inbox scores or buckets on arrival: read now / later / noise, using title + excerpt (and captured body when present). Show the bucket on the card. Keep a “skip model” path so refresh never blocks on LLM.

Needs: a small on-device or cheap-model classifier, stored `triage` on the article, one filter chip.

### 2. Briefing, not only per-article chat

Discuss is one post at a time. Missing: a morning/interval digest (“what landed since last open”) that cites titles and links, written into a Hermes session. Auto-refresh already knows `lastRefresh`. The digest should be opt-in and never run from a silent cron without a setting.

### 3. Memory of taste

First cut is shipped: Settings **Preference Report** exports saved vs
read vs mute stats to `%LOCALAPPDATA%/hermes/rss-reader/saved.json` and a
review markdown next to it. Hermes can read those files. The report does
does not edit `rss-reader-plugin`.

Still missing: “more like this / less like this” on a card. That later
slice writes the same files and the same rubric suggestions. Do not add a
second taste profile.

### 4. Capture that informs the model

Capture is body-only. Missing: a structured extract after capture (entities, claims, “is this a changelog / essay / news brief”) written onto the article so Summary/Evidence start from facts, not a raw dump. Run after capture, in the same queue, off by default.

### 5. Search that is not `indexOf`

List search is literal lowercase includes on title+body. Missing: full-text index (even lunr/flexsearch in the plugin) and optional semantic search over captured bodies. Literal search stays as the fallback.

### 6. Reading session that stays in RSS

Discuss jumps to a Hermes chat. Missing: an inline composer in the article pane that streams into the current article’s thread without stealing the whole window. Keep “open in Hermes” as an escape hatch.

### 7. Multi-item actions

No select-many. Missing: mark read / save / capture / “brief these” on a checked set. Keyboard should extend (shift+j/k) without breaking single-item j/k.

### 8. Feed intelligence

Feeds are URLs. Missing: per-feed health (fail streak, last useful item), suggested related feeds, and a “this feed is all reprints” warning. Health can be derived from existing `feed.error` and `refreshed_at` without new network.

### 9. Sync and backup

Library is one browser IndexedDB. Missing: export/import of the article store (not only OPML), and optional sync to the lifestyle repo or another device. Until then, a “download library JSON” button is the backup.

### 10. Accessibility and density

Cards are tall (18px padding, 56px thumbs). Missing: a compact density setting, and a real listbox keyboard model (aria-activedescendant) so j/k is not a window-level keydown.

---

## Out of scope (on purpose)

- Paywall-bypass services as a product feature
- Replacing the fetch/SSRF hardening with a random proxy
- Splitting the 2.6k-line bundle until the inbox/triage slice forces a module cut

## Suggested order

1. Per-feed health + library JSON export (no model, unblocks trust)
2. Triage buckets on refresh (the AI-first tell)
3. Opt-in digest session
4. Inline composer
5. Full-text index
6. Multi-select + taste buttons

Each step should land as a plugin.yaml patch bump, pack commit, no index PR unless asked.
