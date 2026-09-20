# LIMITATIONS

Personal edition of **Session Retitler** (`sessionretitler`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115964](https://github.com/NousResearch/hermes-agent/pull/115964)

## Blockers

### 1. Direct core-adjacent imports

- **Personal behavior:** imports `agent.title_generator` and `hermes_state.SessionDB` directly, and calls the private-ish `_persist_session_title` helper.
- **Why it fails:** touching core internals outside the plugin SDK contract. A core rename or refactor silently breaks title persistence, and a listing cannot carry that coupling.
- **Needed hook:** a public, SDK-level way to write an `llm`-rank session title (the plugin genuinely needs an llm rank write plus llm-to-llm rewrite). Until that exists, there is no public edition: `public/sessionretitler/` does not exist and personal is held from the catalog.

### 2. Structured LLM call routed through an aux task

- **Personal behavior:** `ctx.llm.complete_structured(..., task="title_generation")` must run with `plugins.entries.sessionretitler.llm.allow_task_override: true` (nested under `llm.`; a flat key is silently ignored and every rename no-ops). The README carries this manual config requirement.
- **Why it fails:** the trust contract is per-install wiring, not a catalogable capability.
- **Confirmed route for public:** `ctx.register_auxiliary_task("sessionretitler_title", ...)` (SDK, probe-safe) makes the key plugin-owned, and an owned key passes the task gate with no trust config. Verified against the host source (`hermes_cli/plugins.py`, `agent/plugin_llm.py`). The public edition must use the owned key, never the built-in `title_generation` slot.
- **Needed hook:** none for this blocker anymore. The write side (blocker 1) is the remaining wall.

## Checklist before listing personal

- [ ] No direct `agent.*` / `hermes_state.SessionDB` imports; an SDK-level llm-rank title write exists and is used.
- [ ] The public edition registers its own auxiliary task (e.g. `sessionretitler_title`) and routes through the owned key; no `allow_task_override` requirement in the README.
- [ ] `hermes plugins validate --install-deps public/sessionretitler` passes (probe runs, hooks match, scan `safe`).
- [ ] Re-pin the catalog `sha:` to a clean public tree once one exists.