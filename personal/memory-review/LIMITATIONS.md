# LIMITATIONS

Personal edition of **Memory Review** (`memory-review`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115966](https://github.com/NousResearch/hermes-agent/pull/115966)

## Blockers

### 1. Hidden composer submit on accept

- **Personal behavior:** after approve, the plugin dispatches `hermes:composer-submit` with a hidden prompt so the session runs memory compaction for the user.
- **Why it fails:** submitting on the user's behalf is app-composer reach-in. There is no catalog-safe composer API yet.
- **Needed hook:** `host.composer.submit` / draft API ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 1). Until that lands, listing requires a Disclosure line in the catalog description if any remaining submit path stays.
- **Public edition:** removed. Palette + dialog remain. The user runs compaction from the session.

### 2. Synthetic item in the app shell dropdown

- **Personal behavior:** injects a menu row into the app-owned shell dropdown (`data-slot="dropdown-menu-content"`).
- **Why it fails:** mutating app-owned chrome. A class or slot rename in any Desktop release breaks the plugin or corrupts the menu.
- **Needed hook:** a registered command or menu slot from [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).
- **Public edition:** removed. Command palette still opens the dialog.

### 3. Unvalidated pending ids (security, already fixed)

- **Personal behavior (before the fix):** `/decide` built `pending_dir / f"{pid}.json"` from request ids, then unlinked or applied the file. `../../` could delete or apply arbitrary user `*.json` under `HERMES_HOME`.
- **Standing rule:** keep the hex-id gate (`^[0-9a-f]{8}$` or resolve-then-`relative_to(pending_dir)`). Do not list a build without it.
- **Tracker:** [apoapostolov/hermes-agent-awesome-plugins#1](https://github.com/apoapostolov/hermes-agent-awesome-plugins/pull/1). Present in personal and public.

## Checklist before listing personal

- [ ] Pending ids are still gated. Traversal test still passes.
- [ ] No `hermes:composer-submit` unless item 1 in #116305 is merged and used.
- [ ] No shell-dropdown inject unless a registered slot exists and is used.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115966.
