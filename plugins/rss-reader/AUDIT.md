# RSS Reader code audit (2026-09-16)

Live file: `%LOCALAPPDATA%/hermes/plugins/rss-reader/desktop/plugin.js` (~2.6k lines, one bundled module). Fork of [Adolanium/hermes-rss](https://github.com/Adolanium/hermes-rss).

## Fixed in this pass

- List cards were `display:block` with a later `flex-direction:row` that did nothing, so thumbnails could not sit on the row. Cards are `display:flex; flex-direction:row`.
- Auto-refresh treated `lastRefresh === 0` as “just now”, so the first open after a Hermes start never pulled. Opening RSS now marks the session visited, refreshes if the period has elapsed (including never), and the 15s timer only runs after that first visit.
- Article detail polled every 5s forever. Polling stops once `captured` is true (library-changed still invalidates).
- j/k listener re-bound on every render (including filter typing). It now depends on list/selection/article.
- Unsubscribing a feed left `articleCache` entries for deleted posts. DELETE now prunes the cache.
- List excerpts ran `plainText()` (DOM parse) per row. `cheapExcerpt` strips tags with a regex.
- Discuss / Check sources always labeled the payload as a feed excerpt. Captured posts now say captured text, still untrusted.

## Stale code (leave for a later removal pass)

Do not delete these in a drive-by. They are unused or leftover names, not load-bearing.

| Item | Why it is stale |
| --- | --- |
| `createLibrary(..., captureFn = null)` | Capture no longer runs inside `/feeds/:id/refresh`. The argument is ignored. |
| `withLeadImage` | One-line alias of `dedupeArticleImages`. Call sites can use the real name. |
| `.rss-tabs` (not `.rss-tabs-pills`) | Old full-width tab bar CSS. The live row uses `rss-tabs rss-tabs-pills`. |
| `readHtml` redirect `for` loop | `curl --location` already follows redirects; the loop always `break`s on HTTP 200. |
| `rss-tabs-pills` class name | Pill UI was rejected; the class only holds underline styles. |
| Paywall mirror block (`PAYWALL_SERVICES`, cooldown map, settings checkbox) | Wired, testing-only. Keep or strip as a product decision, not a drive-by. Do not expand it. |

## Remaining risks (not patched here)

- IndexedDB key is `JSON.stringify([connectionId, profile])`. A connection id that flips `undefined` vs a real id after login looks like an empty library.
- `applyCachedBody` can set `image` in memory on GET/list without writing IndexedDB. Capture POST does persist the lead image.
- `mergeFeed` `Object.assign` still copies feed fields onto captured articles; body/image are restored afterward, but other fields can churn.
- Capture and feed download share the gateway `shell.exec` path (curl + gzip + base64). Fine for a few feeds; painful at 200 subscriptions.
- No tests. `node --check` on a `.mjs` copy is the only automated gate.
- One file holds library, fetch, capture, markdown, CSS, and React. Splitting is a later refactor, not a bugfix.

## Quality snapshot

The reader is a working three-column app: OPML, mute/search, capture queue, rich HTML/markdown, Discuss/Summary/Evidence. The main cost is the monolith and the gateway round-trip per page capture. The fixes above are the cheap correctness/perf wins. Feature gaps live in `PROPOSAL.md`.
