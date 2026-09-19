# LIMITATIONS

Personal edition of **Better Session Appearance** (`better-session-appearance`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115961](https://github.com/NousResearch/hermes-agent/pull/115961)

## Blockers

### 1. Direct write to the app session-color store

- **Personal behavior:** writes the app's persisted key `hermes.desktop.sessionColors`, bypassing the store atom.
- **Why it fails:** races with the app's own writer. App keys are not a plugin contract.
- **Needed hook:** session-row decoration / `setColor` ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 3). Plugin-owned extras stay in `ctx.storage`.
- **Public edition:** held snapshot.

### 2. Fiber-driven ColorPicker and marquee state

- **Personal behavior:** walks fiber to the app `ColorPicker` and calls its `onChange`. Removes the app's marquee state.
- **Why it fails:** React internals and app component props are not a contract.
- **Needed hook:** same `setColor` / decoration API. Do not drive app components through fiber.
- **Public edition:** held snapshot.

### 3. Controls injected into the Appearance dropdown

- **Personal behavior:** injects plugin controls into the app's Appearance menu.
- **Why it fails:** app-owned chrome. Slot names can change in any release.
- **Needed hook:** Appearance-menu slot ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 7).
- **Public edition:** held snapshot.

## Checklist before listing personal

- [ ] No writes to `hermes.desktop.sessionColors` or other `hermes.desktop.*` keys.
- [ ] No fiber walks, no app `ColorPicker.onChange`, no marquee-state removal.
- [ ] No inject into the Appearance dropdown unless item 7 in #116305 is merged and used.
- [ ] Color / decoration goes through the session-row API (item 3 in #116305 is merged).
- [ ] Plugin extras live in `ctx.storage`.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115961.
