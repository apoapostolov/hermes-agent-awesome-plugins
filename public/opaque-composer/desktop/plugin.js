const ID = 'opaque-composer'
const STYLE_ID = 'hermes-opaque-composer-style'

const CSS = `
[data-slot='composer-root'],
[data-slot='composer-root'][data-thread-scrolled-up] {
  --composer-fill: var(--dt-card) !important;
}
`

function start() {
  document.getElementById(STYLE_ID)?.remove()

  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = CSS
  document.head.appendChild(style)

  return () => {
    document.getElementById(STYLE_ID)?.remove()
  }
}

export default {
  id: ID,
  name: 'Opaque Composer',
  description: 'Keep the bottom composer solid so conversation text never shows through it.',
  defaultEnabled: false,
  register(ctx) {
    ctx.onDispose(start())
  }
}
