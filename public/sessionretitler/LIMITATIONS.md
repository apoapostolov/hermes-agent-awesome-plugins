# LIMITATIONS

Listed edition of **Session Retitler** (`sessionretitler`).

## Catalog bar

- Admission rules: catalog README in `NousResearch/hermes-agent`. A listed plugin extends Hermes through public hooks, `ctx.register_*`, and the Desktop SDK.
- Shared hook wishlist: [NousResearch/hermes-agent#116305](https://github.com/NousResearch/hermes-agent/issues/116305)

## Disclosed surfaces

### 1. Title write through the published storage interface

- **Listed behavior:** opens the active profile's store with `persistence_assembly.open_persistence(persistence_assembly.profile_scope())` and writes at `llm` rank through `store.sessions.set_auto_title`. An `llm` to `llm` rewrite lowers the row to `derived` first, and a failed write puts the previous title and its provenance back. A user-set name is a hard wall, and a title source that cannot be read skips the write entirely.
- **Why it is disclosed:** no plugin SDK method writes an `llm`-rank session title. The plugin uses the storage interface the core exposes rather than private title helpers; it imports no `agent.title_generator` or `hermes_state.SessionDB`.
- **Needed hook:** a public `ctx` method to write an `llm`-rank session title (including llm-to-llm rewrite). Until that exists, this disclosure stays.

### 2. Auxiliary task (cleared)

- Registers `sessionretitler_title` with `inherit_from="title_generation"`. No `allow_task_override` trust flag.
