# LIMITATIONS

Personal edition of **Provider Quota Status** (`provider-status`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

Before you pin personal to the catalog, or copy a personal feature into `public/`, walk every blocker below. Either still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you target.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md). A listed Desktop bundle stays inside `ctx.register*`, `host.state` / `host.request`, `ctx.storage`, `ctx.rest`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM selectors, React fiber props, app `localStorage` keys, and raw bridge calls (`apps/desktop/src/contrib/runtime-loader.ts`).
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)
- Catalog intake PR: [NousResearch/hermes-agent#115969](https://github.com/NousResearch/hermes-agent/pull/115969)

## Blockers

### 1. Vendor credential store (request-changes)

- **Personal behavior:** reads `~/.grok/auth.json` and can refresh the Grok CLI refresh token on poll, persisting the rotated token only to the plugin's `config.json`. A poll can burn the CLI login. The same class applies to any Codex/Claude refresh path that consumes a rotating token without writing it back to the vendor store.
- **Why it fails:** listed plugins do not write vendor credential stores they do not own. Consuming a rotating token without writing it back is worse than writing.
- **Needed hook:** none. Read-only: use a valid access token, otherwise tell the user to re-login with the vendor CLI or route through Hermes' own OAuth pool.
- **Public edition:** no vendor CLI auth-file read, no refresh on poll. Expired tokens require a new login.

### 2. Automatic writes to Hermes config (request-changes)

- **Personal behavior:** non-user-initiated writes to `$HERMES_HOME/.env` on exhaust/renewal rotation, including deleting `PRIMARY_N` lines. `/config` save can rewrite `config.yaml` and strip comments (credential-pool strategies).
- **Why it fails:** listed plugins do not silently rewrite Hermes config. Comment-stripping rewrites are extra damage.
- **Needed hook:** none for the policy. Make `.env` / config rewrites an explicit user action, preserve comments, and only touch keys the plugin owns. Disclose those writes in the catalog description.
- **Public edition:** no automatic `.env` or `config.yaml` writes. No "Apply Changes to Hermes .env" control.

### 3. Vendor CLI client identity (disclosure, not a code block)

- **Personal behavior:** Codex `client_id` plus `User-Agent: codex-cli/…`, and the Grok CLI client id, against undocumented or CLI-compatible endpoints.
- **Why it fails:** OAuth-client-reuse is admissible only with a disclosure sentence in the catalog description.
- **Needed hook:** none. Keep a `Disclosure` line in the catalog description. No code change asked on the intake.
- **Public edition:** disclosure is in `plugin.yaml` / README. Keep it on any catalog pin.

### 4. Lifestyle path, secret copy, bind port (LOW)

- **Personal behavior:** hard-coded `C:/git/lifestyle/.env`. Hermes `.env` secrets copied into plaintext `library.env` inside the plugin tree on poll. `/codex/browser/start` binds a caller-chosen loopback port.
- **Why it fails:** machine-specific paths, plaintext secret copies, and caller-chosen bind ports are listing defects.
- **Needed hook:** none. Drop the lifestyle path, drop `library.env` copies, and do not bind a caller-chosen port from a listed build.
- **Public edition:** lifestyle path and `library.env` copy removed.

## Checklist before listing personal

- [ ] No read/refresh of `~/.grok/auth.json` or other vendor CLI stores.
- [ ] No token refresh that burns a rotating CLI refresh token.
- [ ] No automatic `$HERMES_HOME/.env` or `config.yaml` writes. User-initiated only, comments preserved, owned keys only.
- [ ] Catalog description has the Codex/Grok client-identity disclosure.
- [ ] No `C:/git/lifestyle/.env`. No `library.env` secret copy.
- [ ] No caller-chosen loopback bind for Codex browser start.
- [ ] Re-pin catalog `sha:` to the clean tree and comment on #115969.
