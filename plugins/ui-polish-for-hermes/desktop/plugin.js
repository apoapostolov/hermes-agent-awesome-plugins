/**
 * UI Polish for Hermes.
 *
 * Session-list channel group headers (Discord, Telegram, ...): the platform
 * icon renders first, before the collapse glyph and the group name. This
 * plugin MOVES the icon node to the far right of the same header line,
 * after the session count, so the row reads:
 *
 *   [glyph] Name ............ 12  [icon]
 *
 * DOM-move approach: a MutationObserver re-applies the move whenever React
 * re-renders a header, so it survives updates. Scoped strictly to the
 * sessions list.
 */

const ID = 'ui-polish-for-hermes'

const ROOT = '[data-sessions-mode]'

function isHeaderButton(btn) {
  if (btn.tagName !== 'BUTTON') return false
  const kids = btn.children
  if (kids.length < 4) return false
  // Child 0 is the collapse chevron - a codicon font glyph (span/i), not an
  // svg. Match it by its codicon chevron-right class.
  const first = kids[0]
  const cls = String(first.className || '')
  if (!/chevron(-right)?\b/.test(cls) && !(first.querySelector && first.querySelector('[class*="chevron"]'))) return false
  return Boolean(btn.querySelector('span.min-w-0.flex-1'))
}

function polish() {
  document.querySelectorAll(`${ROOT} button`).forEach(btn => {
    if (!isHeaderButton(btn)) return
    const icon = btn.children[1]
    if (!icon || icon === btn.lastElementChild) return
    btn.appendChild(icon)
  })
}

export default {
  id: ID,
  name: 'UI Polish for Hermes',
  description: 'Session-list polish: channel group headers show their platform icon right-aligned after the session count instead of before the name.',
  defaultEnabled: true,
  register(ctx) {
    polish()
    const obs = new MutationObserver(() => polish())
    const root = document.querySelector(ROOT) || document.body
    obs.observe(root, { childList: true, subtree: true })
    ctx.onDispose(() => obs.disconnect())
  }
}
