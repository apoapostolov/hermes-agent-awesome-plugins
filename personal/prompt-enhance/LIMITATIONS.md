# LIMITATIONS

Personal edition of **Prompt Enhance** (`prompt-enhance`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

The public edition is on the composer draft API. Do not copy the caret path from this tree into `public/`.

## Catalog bar

- Desktop surface lint refuses `document.querySelectorAll` on `[data-slot="composer-rich-input"]`, `execCommand('insertText')`, and synthetic input events. Catalog notice: [apoapostolov/hermes-agent-awesome-plugins#4](https://github.com/apoapostolov/hermes-agent-awesome-plugins/issues/4).
- `host.composer.getDraft` and `setDraft` cover reading a draft, replacing it, writing an enhancement back, and undo.
- `host.composer.insertText` only appends. Modes are `block`, `inline`, and `prefix`. None of them writes at the caret.

## Blocker

### Add on a saved prompt inserts at the caret

- **Personal behavior:** a prompt outside the Enhancers folder is inserted at the current selection. Enhancer prompts replace the whole draft, which `setDraft` can do.
- **Public behavior:** the same Add appends the prompt to the end of the draft. Enhance, undo, replace, import, and send use `getDraft` / `setDraft`.
- **Needed hook:** a composer insert that writes at the selection, or a draft API that returns and restores the caret.
- **Do not** copy this file's DOM helpers into `public/` to get the caret back. That fails the desktop surface check.

## Checklist before copying personal into public

- [ ] Add at the caret goes through a public composer API.
- [ ] No `document.querySelector` on app `data-slot` markup, no `execCommand`, no synthetic input events.
- [ ] Enhance, undo, and replace still use `getDraft` / `setDraft`.
