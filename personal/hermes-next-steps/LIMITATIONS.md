# LIMITATIONS

Personal edition of **Next Steps** (`hermes-next-steps`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115969](https://github.com/NousResearch/hermes-agent/pull/115969)

## Blockers

### 1. The renderer injects a stylesheet into the app

- **Personal behavior:** the chip border keeps Hermes' arc animating while a turn is working. The renderer half implements it by creating a `<style>` element with the keyframes and appending it to `document.head`, guarded by an id so it is injected once per window.
- **Why it needs a hook:** the SDK has no stylesheet registration, so the only way to ship the animation today is to write an app-owned DOM node. That is the exact surface reviewers reject, and it also means two plugins doing the same thing would fight over the same `head`.
- **Needed hook:** a renderer-side `ctx.styles(css)` or an SDK-provided class contract for animated borders, tracked in the shared hook wishlist above.
- **Public edition:** drops the injected stylesheet and the arc element, so the running state shows through the chip's disabled/sent state alone.

### 2. A carried label scrolls the window back to its reply

- **Personal behavior:** clicking the age label on a carried option scrolls the transcript back to the reply that offered it, reading `window.scrollY`, waiting a frame, then calling `scrollIntoView` on the transcript block when the scroll did not move.
- **Why it needs a hook:** reading and driving the app's scroll is app-owned DOM and window state. A plugin cannot know whether the transcript is virtualised, and a future transcript rewrite would break the behaviour silently.
- **Needed hook:** a transcript navigation call, for example `host.state.focusBlock(id)`, or a documented anchor the SDK scrolls for you.
- **Public edition:** the age label is plain text and the click does nothing, so the reply must be found by browsing.

### 3. No other reach-in

The agent half is clean: no subprocess, no shell, no network of its own, no `.env` or `config.yaml` writes, no secrets handling. It registers two tools (`next_steps`, `next_steps_recommend`) and one hook (`transform_llm_output`), stores its queue and per-block state through `ctx.storage`, and asks the classifier through the loaded classifier plugin. The classifier is optional and its absence is handled.

## Keeping this honest

If either hook lands, delete the matching blocker here in the same change that removes the reach-in, and make `public/` and `personal/` identical for that surface. Do not delete a blocker while the app-side code still exists.
