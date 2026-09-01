const ID = 'busy-shortcuts'
const COMPOSER_SELECTOR = '[contenteditable="true"]'

function activeComposer() {
  const active = document.activeElement
  if (active && active.matches?.(COMPOSER_SELECTOR)) {
    return active
  }
  return null
}

function replaceEditorText(editor, text) {
  editor.focus()
  const selection = window.getSelection()
  if (!selection) {
    return
  }
  const range = document.createRange()
  range.selectNodeContents(editor)
  selection.removeAllRanges()
  selection.addRange(range)
  document.execCommand('insertText', false, text)
}

function start() {
  const onInput = event => {
    const editor = event.target?.closest?.(COMPOSER_SELECTOR)
    if (!editor || editor !== activeComposer()) {
      return
    }
    const text = (editor.innerText || editor.textContent || '').replace(/\u00a0/g, ' ')
    if (text === '/q') {
      replaceEditorText(editor, '/busy queue')
    }
  }

  document.addEventListener('input', onInput, true)
  return () => document.removeEventListener('input', onInput, true)
}

export default {
  id: ID,
  name: 'Busy Shortcuts',
  description: 'Compact slash commands for interrupt, queue, and steer busy-input modes.',
  defaultEnabled: true,
  register(ctx) {
    ctx.onDispose(start())
  }
}
