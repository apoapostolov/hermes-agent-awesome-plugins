<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Session Retitler</h1>
  <strong>Keep the session list readable as the topic drifts.</strong>
  <p>Every N titleable user messages, retitles the session from the latest exchanges. A title you set yourself is never touched.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.1.1-2ea44f" alt="Version 1.1.1" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

## What You Can Do

- Counts titleable user messages (not completed turns), so break- and steer-heavy chats still advance the counter.
- Every `interval` messages, builds a digest of the latest exchanges and asks the plugin's own `sessionretitler_title` auxiliary slot for a fresh 3-6 word title. The slot inherits the host `title_generation` route until you pin a different model under Settings, Models, Auxiliary.
- Rewrites at `llm` rank only. A user-set name (`title_source == user`) is a hard wall and is never overwritten.
- `derived` / untitled sessions upgrade straight to the new `llm` title; `llm` to `llm` rewrites clear the row first so the core's rank-gated write does not no-op.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Or install just this plugin:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/sessionretitler
```

Enable **Session Retitler** under **Capabilities → Plugins**.

## Requirements / Limits

Backend-only (Python hooks). The plugin registers its own `sessionretitler_title` auxiliary slot, so renaming no longer needs `allow_task_override`. Pin a cheap fast model for it under Settings, Models, Auxiliary if you want it off the default title-generation route.

## License

[MIT](../../LICENSE)