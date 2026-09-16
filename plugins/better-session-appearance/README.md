<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Better Session Appearance</h1>
  <strong>Make the session list easier to scan.</strong>
  <p>Give sessions readable colors, optional emphasis, and a personal idle icon without changing Hermes' working and unread indicators.</p>
  [![Version](https://img.shields.io/badge/version-1.1.5-2ea44f)](plugin.yaml) [![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)
</div>

## What it does

- **Color session titles.** Use the Appearance color with lightness adjusted for the active theme.
- **Emphasize important chats.** Toggle **Bold Session** per conversation.
- **Pick an idle icon.** Search the full Codicon set and replace the idle bullet while keeping working and finished-unread dots intact.
- **Keep choices per session.** Colors, bold state, and glyphs are stored by session id.

## Install

Install the pack, enable **Better Session Appearance**, then reload desktop plugins:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Open a session's Appearance controls to choose its color, weight, and idle icon.

## How it works

A desktop `MutationObserver` watches session-list rows and applies the stored presentation. The plugin uses the picker's own color-change callback and namespaces its session data.

## Compatibility

Desktop-only. The plugin reads Hermes session-list and picker surfaces. If a future Hermes release changes those surfaces, it should go quiet rather than alter unrelated session status.

## Files and license

`desktop/plugin.js` owns the overlay and picker. `plugin.yaml` contains metadata and `__init__.py` registers the desktop plugin. Licensed under [MIT](../../LICENSE).
