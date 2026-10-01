# LIMITATIONS

Personal edition of **Prompt Enhance** (`prompt-enhance`). This file is why that edition cannot be listed in the Hermes Plugin Catalog as-is.

The public edition was removed. Do not copy this tree back into `public/` until the missing hook exists.

## Catalog bar

- Desktop surface lint refuses `document.querySelectorAll` on `[data-slot="composer-rich-input"]`, `execCommand('insertText')`, and synthetic input events. Catalog notice: [apoapostolov/hermes-agent-awesome-plugins#4](https://github.com/apoapostolov/hermes-agent-awesome-plugins/issues/4).
- `host.composer.getDraft` and `setDraft` cover reading a draft, replacing it, writing an enhancement back, and undo.
- `host.composer.insertText` only appends. Modes are `block`, `inline`, and `prefix`. None of them writes at the caret.

## Blocker

### Add on a saved prompt inserts at the caret

- **Personal behavior:** a prompt outside the Enhancers folder is inserted at the current selection. Enhancer prompts replace the whole draft, which `setDraft` can do.
- **Why a public port drops behavior:** append is not the same action when the caret is in the middle of a draft.
- **Needed hook:** a composer insert that writes at the selection, or a draft API that returns and restores the caret.
- **Public edition:** omitted. A listed copy that appends instead would ship a smaller product under the same name.

## Checklist before a public edition

- [ ] Add at the caret goes through a public composer API.
- [ ] No `document.querySelector` on app `data-slot` markup, no `execCommand`, no synthetic input events.
- [ ] Enhance, undo, and replace still use `getDraft` / `setDraft`.
