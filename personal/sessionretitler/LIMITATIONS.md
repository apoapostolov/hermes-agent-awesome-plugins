# LIMITATIONS

Personal edition of **Session Retitler** (`sessionretitler`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115964](https://github.com/NousResearch/hermes-agent/pull/115964)

## Blockers

### 1. Title write through the published storage interface

- **Personal behavior:** opens the active profile's store with `persistence_assembly.open_persistence(persistence_assembly.profile_scope())` and writes at `llm` rank through `store.sessions.set_auto_title`. No `agent.*` or `hermes_state.SessionDB` imports remain.
- **Why it used to fail:** the old write went through private core title helpers, so a core rename or refactor could silently break persistence or stamp an automatic rename as a user title. The storage interface is the supported path.
- **Needed hook:** a public, SDK-level way to write an `llm`-rank session title (the plugin genuinely needs an llm rank write plus llm-to-llm rewrite). Until that exists, the listed edition discloses the storage interface (catalog rule 13) because without the write there is no product.

### 2. Structured LLM call routed through an aux task

- **Personal behavior:** `ctx.llm.complete_structured(..., task="sessionretitler_title")` after `ctx.register_auxiliary_task("sessionretitler_title", inherit_from="title_generation")`. The owned key passes the task gate with no `allow_task_override` trust flag. The operator can pin a different model under Settings, Models, Auxiliary.
- **Why it used to fail:** the old call used the built-in `title_generation` slot, which needed per-install `plugins.entries.sessionretitler.llm.allow_task_override: true`. That trust contract is not a catalogable capability.
- **Status:** cleared. Blocker 1 now uses the published storage interface; the remaining wall is the absence of an SDK-level title write.

## Checklist before listing personal

- [x] No direct `agent.*` / `hermes_state.SessionDB` imports; the write goes through the published persistence interface. An SDK-level llm-rank title write would still be preferable.
- [x] The plugin registers its own auxiliary task (`sessionretitler_title`, inherits `title_generation`) and routes through the owned key; no `allow_task_override` requirement in the README.
- [x] `hermes plugins validate --install-deps public/sessionretitler` passes (probe runs, hooks match, scan `safe`); no private-core-import warnings for the title write remain.
- [ ] Re-pin the catalog `sha:` to the public tree.