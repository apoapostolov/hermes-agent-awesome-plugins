# LIMITATIONS

Personal edition of **Sidebar Manager** (`sidebar-manager`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115973](https://github.com/NousResearch/hermes-agent/pull/115973)

## Blockers

### 1. Hide and reorder core nav by mutating app DOM

- **Personal behavior:** injected CSS hides core nav rows. The plugin re-parents React-owned sidebar children, `insertBefore`s into app-owned rows, and runs a body-wide `MutationObserver` to re-assert after re-renders.
- **Why it fails:** this is the reach-in class rule 8 blocks. There is no SDK hook for hiding or reordering core nav.
- **Needed hook:** `host.sidebar.hide(navId)` / `setOrder(navIds)` ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 4).
- **Public edition:** held snapshot. Stripping the reach-in leaves no product.

### 2. Plugin state in a raw `localStorage` key

- **Personal behavior:** hide/order state lives in an app-visible `localStorage` key. Uninstall does not clear it.
- **Why it fails:** listed plugins keep namespaced state in `ctx.storage`, which is cleaned with the plugin.
- **Needed hook:** none. Move to `ctx.storage` before any listing attempt. This is a now-fix, independent of item 4.
- **Public edition:** still a snapshot. Fix this on personal before a catalog pin even after the sidebar hook lands.

## Checklist before listing personal

- [ ] No injected CSS that hides app-owned nav.
- [ ] No re-parent / `insertBefore` / body `MutationObserver` on the sidebar.
- [ ] Hide/order goes through `host.sidebar` (item 4 in #116305 is merged).
- [ ] State is in `ctx.storage`, not raw `localStorage`.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115973.
