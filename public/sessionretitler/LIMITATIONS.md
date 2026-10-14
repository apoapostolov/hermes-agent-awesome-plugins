# LIMITATIONS

Listed edition of **Session Retitler** (`sessionretitler`).

## Catalog bar

- Admission rules: catalog README in `NousResearch/hermes-agent`. A listed plugin extends Hermes through public hooks, `ctx.register_*`, and the Desktop SDK.
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)

## Disclosed surfaces

### 1. Direct core-adjacent imports for the title write

- **Listed behavior:** imports `agent.title_generator` and `hermes_state.SessionDB`, and calls `_persist_session_title` so an `llm`-rank rewrite can replace an earlier `llm` title. A user-set name is still a hard wall.
- **Why it is disclosed:** no plugin SDK method writes an `llm`-rank session title. Without that write the plugin has no product, so the listed edition keeps the guarded imports rather than shipping a no-op.
- **Needed hook:** a public `ctx` method to write an `llm`-rank session title (including llm-to-llm rewrite). Until that exists, catalog CI reports these as private-core-import warnings.

### 2. Auxiliary task (cleared)

- Registers `sessionretitler_title` with `inherit_from="title_generation"`. No `allow_task_override` trust flag.
