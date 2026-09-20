# LIMITATIONS

Personal edition of **CDP Manager** (`cdp-manager`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115969](https://github.com/NousResearch/hermes-agent/pull/115969)

## Blockers

### 1. Backend spawns a local browser (disclosure, not a code block)

- **Personal behavior:** the plugin backend starts local Chrome with `--remote-debugging-port` on 127.0.0.1 (per-port profiles under the Hermes home directory) and closes it with a clean `Browser.close` over the endpoint WebSocket. A supervisor thread auto-starts the managed port when it is down (including on backend boot) and force-reboots it after repeated failed launches. The supervisor only touches ports the user explicitly marked managed.
- **Why it needs disclosure:** a listed plugin that starts OS processes, even loopback-only ones the user asked it to manage, must say so in the catalog description. There is no network exfiltration, no secret handling, and no process kill: stop is always the clean CDP close path.
- **Needed hook:** none. Keep a `Disclosure` line in the catalog description.
- **Public edition:** same behavior, disclosure is in `plugin.yaml` / README. Keep it on any catalog pin.

### 2. Personal Chrome profile reuse (disclosure, not a code block)

- **Personal behavior:** a port can run on a profile from the real Chrome User Data dir (`chrome:<dirname>`), so automation reuses your cookies. The backend refuses before spawning when that dir is locked by a running Chrome (spawning would only pop a stray window in that Chrome) or already served by another live port (one debug port per user-data-dir, verified). The choice is remembered per port and reused by supervisor auto-starts.
- **Why it needs disclosure:** automation running with the user's own cookies must be named in the catalog description.
- **Needed hook:** none. Keep the `Disclosure` line covering personal profiles in the catalog description.
- **Public edition:** same behavior, disclosure is in `plugin.yaml` / README. Keep it on any catalog pin.

### 3. No other reach-in

- **Personal behavior:** statusbar chip plus dialog built only from SDK components (`Dialog`, `Input`, `Button`, `Codicon`, `Tip`), backend reached through `ctx.rest`, one external link through `ctx.os.openExternal`. State lives in the plugin's own `config.json`. No Hermes `.env` or `config.yaml` writes, no vendor credentials, no secrets, no app DOM selectors, no `localStorage` keys.
- **Public edition:** identical. Nothing to drop.

## Checklist before listing personal

- [x] No app-owned DOM selectors, fiber props, or `localStorage` keys.
- [x] No Hermes `.env` or `config.yaml` writes.
- [x] No vendor credentials or secrets.
- [x] Backend spawns loopback-only Chrome the user asked it to manage; catalog description carries the disclosure.
- [x] Stop path is clean `Browser.close`, never a process kill.
- [x] Re-pin catalog `sha:` to the clean tree.
