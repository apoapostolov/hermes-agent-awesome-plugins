# LIMITATIONS

**Intelligent Tool Break** (`intelligent-tool-break`). This file records the behaviors that keep the plugin off the catalog as-is, and what the listed edition drops from personal. Both editions carry the same copy.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

The intake marked these as request-changes (not a separate policy class). A listing still cannot carry them.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115964](https://github.com/NousResearch/hermes-agent/pull/115964)

## Blockers

### 1. Process-wide Popen patch and private CLI rebind

- **Personal behavior:** `register()` sets `subprocess.Popen = _TrackingPopen` and rebinds private `cli.HermesCLI._should_handle_steer_command_inline`.
- **Why it fails:** a listing cannot carry private-method rebinding. It breaks silently on any core change. `VALID_HOOKS`-only wiring is admissible today.
- **Needed hook:** public steer-interception if the existing tool-call hooks are not enough. Name the missing hook on the core list. Do not patch `Popen` or private CLI methods.
- **Public edition:** removed, including the dead helpers (`_TrackingPopen`, `_install_popen_hook`, `_install_cli_busy_dispatch`). Hooks, `/break`, `/again`, and status commands stay.

### 2. Unscoped descendant SIGKILL

- **Personal behavior:** `/break` SIGKILLs every descendant started after the target, with no session filter. In gateway mode session A can kill session B's terminals, MCP servers, and subagents. In-process tools are only relabelled, so the UI over-promises.
- **Why it fails:** cross-session process kill is unsafe in gateway mode.
- **Needed hook:** none for the policy. Key the registry by session id at `Popen` time and only kill that session's entries, or drop process kill and keep hook relabel. A public process-kill path needs a session-scoped core API.
- **Public edition:** no descendant SIGKILL. Dead kill helpers (`_kill_tree`, `_kill_registry_since`) stripped. Hooks relabel the in-flight call.

### 3. Composer insert via execCommand and app events

- **Personal behavior:** `document.execCommand('insertText')` into the app composer, plus app-internal composer events, to prefix `/break`.
- **Why it fails:** app-composer reach-in.
- **Needed hook:** composer draft / insert API ([#116305](https://github.com/NousResearch/hermes-agent/issues/116305) item 1).
- **Public edition:** notification tells the user to type `/break` in the composer.

### 4. Native status-row decoration (app-owned DOM)

- **Personal behavior:** the desktop half queries the app's composer status stack (`[data-slot="composer-status-stack"]`, `.codicon-server-process`, `.truncate`), inserts elapsed pills and Break / Message / Again buttons into app status rows with `insertAdjacentElement`, restyles the app's title span, and mounts a gear on app section headers via a `MutationObserver` repainter.
- **Why it fails:** app-owned DOM. A class or slot rename in any Desktop release breaks it silently, and the plugin runs in the renderer with full app authority. Same class the `desktop surface` lint blocks (catalog rule 8).
- **Needed hook:** a registered slot for per-tool status row actions. Not in the SDK today. It is on the [#116305](https://github.com/NousResearch/hermes-agent/issues/116305) wishlist; an `apps/desktop` PR adding it is the fast route.
- **Public edition:** all status-stack decoration removed. The strip renders in the plugin's own `COMPOSER_AREAS.top` contribution only.

## Checklist before listing personal

- [ ] No `subprocess.Popen` monkeypatch.
- [ ] No private `HermesCLI` method rebind. `VALID_HOOKS` only, or a public steer hook that exists in the target core.
- [ ] Process kill is session-scoped, or removed.
- [ ] No `execCommand` / app composer events unless item 1 in #116305 is merged and used.
- [ ] No selectors on app-owned DOM (status stack, status rows, section headers) unless a per-tool status slot from #116305 exists and is used.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115964.
