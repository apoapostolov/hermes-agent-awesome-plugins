# LIMITATIONS

**Jev Routing** (`hermes-jev-routing`). This file records the behaviors that keep
the plugin off the catalog as-is, and what the listed edition drops from personal.
Both editions carry the same copy.

Before you pin personal to the catalog, or copy a personal feature into
`public/`, walk every blocker below. Either still comply, or confirm the linked
Hermes issue or PR is resolved and the SDK hook exists in the Desktop build you
target.

Catalog intake: [NousResearch/hermes-agent#142074](https://github.com/NousResearch/hermes-agent/pull/142074).
Maintainer review at `ef98501c`: the personal behaviors below move sessions by
rebinding live agent internals, so the plugin cannot list as built. The rebuild
is `public/hermes-jev-routing` at 1.1.0.

## Catalog bar

- Admission rule: catalog README [rule 8](https://github.com/NousResearch/hermes-agent/blob/main/plugin-catalog/README.md).
  A listed plugin stays inside `ctx.register*`, `ctx.emit`, the observer hooks,
  the middleware kinds, and for the desktop half `host.state` / `host.request`.
- The `desktop surface` lint is the floor. Reviewers also reject app-owned DOM
  selectors, React fiber props and app `localStorage` keys.
- A listing may not patch a running agent, `gc`-walk to find one, or rebind a
  core method. Anything that cannot be done from the SDK needs a core issue that
  names the missing hook.

## Blockers

### 1. Session model rebind (the routing move itself)

- **Personal behavior:** `switch.py` finds the live agent by walking
  `sys._current_frames()` for locals, falls back to a `gc.get_objects()` scan for
  the agent cache, then calls `agent.switch_model(...)` mid-turn and writes
  `agent.reasoning_config`.
- **Why it fails:** a listing cannot reach into a running agent. The stack walk,
  the cache scan and the method call all break silently on any core refactor,
  and the plugin has no contract for any of them.
- **Needed hook:** none named by the reviewer beyond the existing middleware. A
  per-request model rewrite is the supported route; a *session* model move from a
  backend plugin needs a core API (see item 2, which is where the provider
  boundary actually bites).
- **Public edition:** `llm_request` rewrites `request["model"]` on the provider
  already bound to the turn, and rewrites `reasoning_effort` when the request
  carries that field. `switch.py` and the stack/`gc` walk are gone.

### 2. Cross-provider moves

- **Personal behavior:** `hermes_cli.model_switch.switch_model` resolves the
  destination credentials, then the agent is rebound to another provider
  mid-turn.
- **Why it fails:** the private CLI resolver is core-internal, and the
  middleware contract cannot change the provider of the request it is handed.
  `llm_request` sees provider-specific kwargs for an already-bound client.
- **Needed hook:** a public way to move one request to another provider, or a
  core issue naming the seam. Until then the decision is reported, not sent.
- **Public edition:** a pick on another provider is recorded as
  `blocked: cross-provider` and printed in the Jev line. The desktop approve row
  can still move the session, because `config.set` with a `model` value is a
  public `host.request`. A CLI or gateway session without the desktop gets no
  cross-provider move at all.

### 3. Stopping a send (hold, and the confirm gate's teeth)

- **Personal behavior:** `hold.py` sets `_interrupt_requested`, writes
  `_interrupt_message`, rebinds `agent._interruptible_api_call` with a wrapper
  that raises before the socket opens, and calls `agent.steer()` to queue the
  original prompt for a re-send on the approved model.
- **Why it fails:** `llm_request` middleware has no deny/block return. It can
  only replace the payload, and an exception from it is fail-open by contract.
  `pre_llm_call` can only inject context text. So a listing cannot stop a send.
- **Needed hook:** a block/deny result on `llm_request` or `pre_llm_call`. Ask
  for it explicitly if the hold is essential.
- **Public edition:** no hold. A confirm tier offers the approve row and leaves
  the turn that triggered it on the current model; approving moves the session
  for the following sends. `owed_prompt` is always empty, so nothing is
  re-submitted.

### 4. Host context and spend reads

- **Personal behavior:** `agent.usage_anchor.anchored_context_tokens` and
  `agent.turn_context._preflight_request_tokens` size the prompt;
  `agent.usage_pricing.estimate_usage_cost` / `normalize_usage` /
  `get_pricing_entry` price each routed turn; `agent.model_metadata`
  `get_model_capabilities` reports reasoning support.
- **Why it fails:** four private modules. An unpriced or mis-sized row changes a
  routing decision, so a silent break is a spend bug.
- **Needed hook:** a public usage/pricing accessor and a public context-size
  figure in the hook payload.
- **Public edition:** context is `characters / 4` (an estimate, labelled as
  one). Money comes from a `pricing` block the operator writes into the routing
  JSON; unpriced models record tokens but no dollars, and budget caps stay inert
  rather than guessing. Reasoning support is reported `False`.

### 5. Provider availability and Codex quota

- **Personal behavior:** `hermes_cli.models.cached_provider_model_ids` supplies
  the live model list, and `agent.account_usage.fetch_account_usage` supplies
  the Codex 5h/weekly reading the quota floors gate on.
- **Why it fails:** both are core-internal, and a stale or empty answer changes
  which model wins a chain.
- **Needed hook:** a public model-availability provider and a quota reading in
  the plugin SDK.
- **Public edition:** no live list, so every configured model stays eligible; no
  reading, so the quota gate follows `onUnknown` (`use` by default) and never
  blocks.

### 6. Config-chosen API key

- **Personal behavior:** the key name came from the routing JSON (`apiKeyEnv`)
  and was read from the process environment.
- **Why it fails:** the catalog wants the key declared, not discovered.
- **Needed hook:** none. This is available today.
- **Public edition:** `plugin.yaml` declares `requires_env: [TYPESAFE_API_KEY]`
  and the code reads it through `agent.secret_scope.get_secret`, so a profile
  scope wins. `apiKeyEnv` is no longer read.

### 7. Desktop reaches into app-owned DOM

- **Personal behavior:** `desktop/plugin.js` mounts the line under
  `[data-slot="aui_user-message-root"]`, keeps a per-turn line cache in
  `localStorage` / `sessionStorage`, inserts status pills and rewrites app nodes.
- **Why it fails:** app-owned DOM and app storage keys. Any Desktop release can
  rename a slot and break it silently.
- **Needed hook:** a registered slot for a per-message line. Not in the SDK
  today; `COMPOSER_AREAS` is the sanctioned place for this content.
- **Public edition:** one `COMPOSER_AREAS.underside` contribution and nothing
  else. No app DOM, no `localStorage`. An older turn does not keep its line; the
  strip follows the session's last routed turn.

## Checklist before listing personal

- [ ] No `agent.switch_model`, no stack/frame walk, no `gc` scan for the agent.
- [ ] No rebind of `_interruptible_api_call`, no `_interrupt_*` writes, no
      `agent.steer`.
- [ ] No imports from `agent.usage_anchor`, `agent.turn_context`,
      `agent.usage_pricing`, `agent.model_metadata`, `agent.account_usage`,
      `hermes_cli.models`, or `hermes_cli.model_switch`.
- [ ] Cross-provider routing either uses a public core API or is reported as
      blocked.
- [ ] Hold is either backed by a block/deny contract or removed.
- [ ] The Jev key is declared in `requires_env` and read through
      `agent.secret_scope`.
- [ ] No selector on app-owned DOM, no app `localStorage` / `sessionStorage`.
- [ ] Re-pin the catalog `sha:` to the clean tree and comment on #142074.

## What listable still does

Routing by tier and task kind, shadow / notify / auto / confirm modes, the
per-turn Jev line and approve row, `/jev-routing` commands, the token ledger with
an operator rate card, and stickiness. The parts that need a core hook are named
above, with the behavior the plugin falls back to.
