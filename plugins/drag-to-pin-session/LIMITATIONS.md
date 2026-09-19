# LIMITATIONS

Personal edition of **Drag to Pin Session** (`drag-to-pin-session`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115963](https://github.com/NousResearch/hermes-agent/pull/115963)

## Blockers

### 1. React fiber walk to pin and reorder

- **Personal behavior:** walks `__reactFiber$` on session rows to harvest `onTogglePin` / `onReorderSessions`, then calls those props on drop.
- **Why it fails:** fiber internals and prop names are not a contract. Any app build can rename them. Rule 8 treats this as reaching into internal stores.
- **Needed hook:** `host.sessions.pin` / `reorder` ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 3). This plugin is the clearest use case for that hook.
- **Public edition:** held snapshot. Stripping the fiber walk leaves no product.

## Checklist before listing personal

- [ ] No `__reactFiber$` (or other fiber key) walks.
- [ ] Pin and reorder go through `host.sessions` (item 3 in #116305 is merged).
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115963.
