# Retired and on hold

A plugin lands here when it stops being a pack plugin. Two states.

**Retired**: the Hermes code or interface the plugin was built on is gone or deprecated, so the plugin cannot work as written.

**On hold**: the plugin still describes a real need, but the surface it needs does not exist yet. It revives when Hermes ships that capability.

A retired or held plugin keeps its `personal/<id>/` tree so it can be revived. It is removed from `hermes-pack.yaml` so the pack stops installing it, and it carries no catalog entry.

| Plugin | State | Since | Why | Revives when |
| --- | --- | --- | --- | --- |
| [better-capabilities](personal/better-capabilities/README.md) | On hold | 2026-10-20 | The Capabilities page uninstalls a plugin itself now, which was the headline feature. What is left, deleting and zipping a skill folder and saving on/off presets, has no plugin seam: `host.skills` exposes `list` and `setEnabled` only, and presets have no API. Its dashboard half reaches desktop internals, so it cannot list as it stands. | The plugin SDK exposes skill file operations (delete, package) and a preset set, or Desktop grows a sanctioned seam for both. |

Nothing here is deleted. A retired tree is read-only history that a future API can bring back.
