# Retired and on hold

A plugin lands here when it stops being a pack plugin. Two states.

**Retired**: the Hermes code or interface the plugin was built on is gone or deprecated, so the plugin cannot work as written.

**On hold**: the plugin still describes a real need, but the surface it needs does not exist yet. It revives when Hermes ships that capability.

A retired or held plugin keeps its `personal/<id>/` tree so it can be revived. It is removed from `hermes-pack.yaml` so the pack stops installing it, and it carries no catalog entry.

| Plugin | State | Since | Why | Revives when |
| --- | --- | --- | --- | --- |
| _(none)_ | — | — | — | — |

**Revived:** [better-capabilities](personal/better-capabilities/README.md) came back on
2026-10-27 as a plugin-owned Settings ▸ Plugins page built only on the plugin SDK
(`ctx.registerSettingsPage`, `host.skills`, `host.toolsets`, `host.request`, `ctx.rest`,
`ctx.os`). Its rows no longer touch the Capabilities page's markup, which is what retired it.
The pack does not pin it yet.

Nothing here is deleted. A retired tree is read-only history that a future API can bring back.
