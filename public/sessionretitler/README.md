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

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Session Retitler" />
</div>

## What You Can Do

- Counts titleable user messages (not completed turns), so break- and steer-heavy chats still advance the counter.
- Every `interval` messages, builds a digest of the latest exchanges and asks the plugin's own `sessionretitler_title` auxiliary slot for a fresh 3-6 word title. The slot inherits the host `title_generation` route until you pin a different model under Settings, Models, Auxiliary.
- Rewrites at `llm` rank only. A title you set yourself is never overwritten.
- Untitled sessions upgrade straight to the new `llm` title; an earlier `llm` title is rewritten in place.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/sessionretitler
```

Enable **Session Retitler** under **Capabilities → Plugins**.

## Requirements / Limits

Backend-only (Python hooks). The plugin registers its own `sessionretitler_title` auxiliary slot, so renaming does not need `allow_task_override`. Pin a cheap fast model for it under Settings, Models, Auxiliary if you want it off the default title-generation route.

Disclosure: the rename writes through `agent.title_generator` and `hermes_state.SessionDB` because Hermes has no plugin SDK title-write seam yet. Those imports are guarded; a failed write is logged and the turn continues. Catalog rule 13.

## License

[MIT](../../LICENSE)
