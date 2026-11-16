const ID = 'queue-container-fix'
const STYLE_ID = 'hermes-queue-container-fix-style'

// A queued prompt row is the only status row carrying the comment glyph. Its
// controls used to sit in the last grid column, past the end of the message,
// where a long line pushes them to the far edge and they only appear on hover.
// Moving the action column in front of the content puts them at the start of the
// first line, and a resting opacity keeps them visible without hovering.
const QUEUE_ROW = `[data-slot='composer-status-stack'] .status-row:has(.status-row-icon .codicon-comment)`

// The controls take only the width their own buttons need. A server-owned row
// can carry no controls at all, and a reserved column would leave that row with
// an empty gap before its text.
const CSS = `
${QUEUE_ROW} {
  grid-template-columns: var(--status-action-width) var(--status-icon-width) auto minmax(0, 1fr);
}

${QUEUE_ROW} .status-row-actions {
  grid-column: 3;
  justify-content: flex-start;
  opacity: 0.55;
}

${QUEUE_ROW} .status-row-content {
  grid-column: 4;
}

${QUEUE_ROW}:hover .status-row-actions,
${QUEUE_ROW}:focus-within .status-row-actions {
  opacity: 1;
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
  name: 'Queue Container Fix',
  description: "Puts each queued prompt's steer, edit and remove controls at the start of its first line.",
  defaultEnabled: true,
  register(ctx) {
    ctx.onDispose(start())
  }
}
