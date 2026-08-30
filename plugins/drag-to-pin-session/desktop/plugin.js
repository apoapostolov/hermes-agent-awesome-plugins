/**
 * Drag to Pin — Hermes desktop plugin.
 *
 * Makes the Pinned section of the Sessions sidebar a drop container:
 *
 *   drag a session row into Pinned    -> pin it
 *   drag a pinned row out to Sessions -> unpin it
 *
 * Hot-loads, no rebuild, no restart. LIVE door:
 *   desktop-plugins/drag-to-pin-session/plugin.js
 *
 * Why it rides the app's own pointer drag instead of native HTML5 DnD: the
 * session row already runs two gestures off one press — dnd-kit's
 * PointerSensor reorder (listeners spread on the row shell) and the pane
 * session-drag. Native DnD collided with both; a pointer drag on the same
 * threshold does not. Same lesson the core session-drag.ts records.
 *
 * The grabber ([data-reorder-handle]) is deliberately left alone: it stays
 * pure reorder. Dragging the row BODY is what pins/unpins.
 */

const ID = 'drag-to-pin-session'
const ROW = '.row-hover'
const SKIP = '[data-row-actions], [data-reorder-handle]'
const OVER_ATTR = 'data-dtp-over'
const STYLE_ID = 'drag-to-pin-style'

// Localized "Pinned" section labels (i18n en/ar/ja/zh/zh-hant).
const PINNED_LABELS = new Set(['Pinned', 'المثبتة', 'ピン留め', '已置顶', '已釘選'])

// Matches the app's own row-drag activation distance.
const THRESHOLD = 6

const CSS = `
[${OVER_ATTR}] {
  background: color-mix(in srgb, var(--ui-accent) 14%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--ui-accent) 55%, transparent);
  border-radius: 0.5rem;
}
`

// ── React fiber access ───────────────────────────────────────────────────────
// The compiled sidebar exposes no data attributes carrying a session id, so the
// row's identity is read off the component props the row was rendered with.
// Read-only: nothing here mutates React state.

function fiberOf(el) {
  if (!el) return null

  for (const key of Object.keys(el)) {
    if (key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$')) {
      return el[key]
    }
  }

  return null
}

function findProps(el, test, cap = 90) {
  const root = fiberOf(el)
  if (!root) return null

  const seen = new Set()
  const queue = [root]
  let n = 0

  while (queue.length && n < cap) {
    const fiber = queue.pop()
    n += 1

    if (!fiber || seen.has(fiber)) continue
    seen.add(fiber)

    const props = fiber.memoizedProps || fiber.pendingProps
    if (props && test(props)) return props

    if (fiber.return) queue.push(fiber.return)
  }

  return null
}

// ── Sidebar geometry ─────────────────────────────────────────────────────────

function sectionLabel(group) {
  const label = group.querySelector('span.uppercase')

  return label ? label.textContent.trim() : ''
}

/** Resolve the two droppable sections inside the sessions sidebar. */
function sections() {
  const scope = document.querySelector('[data-sessions-mode]')
  if (!scope) return null

  const groups = [...scope.querySelectorAll('[data-slot="sidebar-group"]')]
  const pinned = groups.find(group => PINNED_LABELS.has(sectionLabel(group)))

  // Hidden while a search query is active; nothing to drop onto.
  if (!pinned) return null

  // Recents is the next group after Pinned in the same container.
  const recents =
    groups.find(
      group => group !== pinned && group.compareDocumentPosition(pinned) & Node.DOCUMENT_POSITION_PRECEDING
    ) || null

  return { pinned, recents }
}

function contains(group, x, y) {
  if (!group) return false

  const r = group.getBoundingClientRect()

  return x >= r.left && x <= r.right && y >= r.top && y <= r.bottom
}

function mark(group, on) {
  if (!group) return

  if (on) {
    group.setAttribute(OVER_ATTR, '1')
  } else {
    group.removeAttribute(OVER_ATTR)
  }
}

function clearMarks() {
  for (const node of document.querySelectorAll(`[${OVER_ATTR}]`)) {
    node.removeAttribute(OVER_ATTR)
  }
}

// ── Row identity ─────────────────────────────────────────────────────────────

/**
 * The row's own props. `onPin` is the section's toggle wired to the right
 * store call for wherever the row lives: pinSession in Sessions, unpinSession
 * in Pinned. Going through it means the real atom updates, the backend
 * `pinned` mirror PATCHes, and the sidebar re-renders — no localStorage
 * poking that the in-memory store would never see.
 */
function rowProps(row) {
  return findProps(row, p => p.session && typeof p.session.id === 'string' && typeof p.onPin === 'function')
}

/** The section's reorder callback, needed to undo dnd-kit's reorder below. */
function reorderFn(row) {
  const props = findProps(row, p => typeof p.onReorderSessions === 'function')

  return props ? props.onReorderSessions : null
}

function sectionOf(secs, row) {
  if (secs.pinned.contains(row)) return 'pinned'
  if (secs.recents && secs.recents.contains(row)) return 'recents'

  return null
}

// ── Gesture ──────────────────────────────────────────────────────────────────

let drag = null

function onPointerDown(event) {
  if (event.button !== 0 || drag) return

  const target = event.target
  if (!target || !target.closest) return

  const row = target.closest(ROW)
  if (!row) return

  // The grabber owns reorder; the kebab cluster owns its own gestures.
  if (target.closest(SKIP)) return

  const secs = sections()
  if (!secs) return

  const source = sectionOf(secs, row)
  if (!source) return

  const props = rowProps(row)
  if (!props) return

  drag = {
    row,
    props,
    source,
    reorder: reorderFn(row),
    x0: event.clientX,
    y0: event.clientY,
    engaged: false
  }

  window.addEventListener('pointermove', onPointerMove, true)
  window.addEventListener('pointerup', onPointerUp, true)
  window.addEventListener('pointercancel', onPointerCancel, true)
}

function onPointerMove(event) {
  if (!drag) return

  if (!drag.engaged) {
    if (Math.hypot(event.clientX - drag.x0, event.clientY - drag.y0) < THRESHOLD) return
    drag.engaged = true
  }

  const secs = sections()
  if (!secs) return

  const { x, y } = { x: event.clientX, y: event.clientY }

  // Light the section that would actually receive the drop.
  mark(secs.pinned, drag.source === 'recents' && contains(secs.pinned, x, y))
  mark(secs.recents, drag.source === 'pinned' && contains(secs.recents, x, y))
}

function teardown() {
  window.removeEventListener('pointermove', onPointerMove, true)
  window.removeEventListener('pointerup', onPointerUp, true)
  window.removeEventListener('pointercancel', onPointerCancel, true)
  clearMarks()

  const finished = drag
  drag = null

  return finished
}

function onPointerCancel() {
  teardown()
}

function onPointerUp(event) {
  const finished = teardown()
  if (!finished || !finished.engaged) return

  const secs = sections()
  if (!secs) return

  const { x, y } = { x: event.clientX, y: event.clientY }
  const target = contains(secs.pinned, x, y) ? 'pinned' : contains(secs.recents, x, y) ? 'recents' : null

  const pin = finished.source === 'recents' && target === 'pinned'
  const unpin = finished.source === 'pinned' && target === 'recents'

  if (!pin && !unpin) return

  try {
    finished.props.onPin()
  } catch (err) {
    console.warn(`[${ID}] pin toggle failed`, err)

    return
  }

  // dnd-kit ran off the same press. Its reorder is a no-op across lists
  // visually (the row leaves the list it was dragged from), but it flips
  // the flat list into MANUAL order — a sticky sort change the user never
  // asked for. Empty order ids switch the list back to its normal sort;
  // run after dnd-kit's own pointerup so it is the last write.
  if (pin && finished.reorder) {
    setTimeout(() => {
      try {
        finished.reorder([])
      } catch {
        /* list may have unmounted */
      }
    }, 0)
  }

  // Reveal what just landed if Pinned was collapsed.
  if (pin && !secs.pinned.querySelector('[data-slot="sidebar-group-content"]')) {
    secs.pinned.querySelector('button')?.click()
  }

  // Suppress the click that follows a real drag (it would resume the chat).
  suppressClick()
}

let clickGuard = false

function suppressClick() {
  clickGuard = true
  setTimeout(() => {
    clickGuard = false
  }, 0)
}

function onClickCapture(event) {
  if (!clickGuard) return

  event.preventDefault()
  event.stopPropagation()
}

// ── Lifecycle ────────────────────────────────────────────────────────────────

function start() {
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = CSS
  document.head.appendChild(style)

  window.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('click', onClickCapture, true)

  return () => {
    window.removeEventListener('pointerdown', onPointerDown, true)
    document.removeEventListener('click', onClickCapture, true)
    window.removeEventListener('pointermove', onPointerMove, true)
    window.removeEventListener('pointerup', onPointerUp, true)
    window.removeEventListener('pointercancel', onPointerCancel, true)
    document.getElementById(STYLE_ID)?.remove()
    clearMarks()
    drag = null
  }
}

export default {
  id: ID,
  name: 'Drag to Pin',
  description: 'Drag a session into the Pinned section to pin it, drag it out to unpin.',
  defaultEnabled: true,
  register(ctx) {
    ctx.onDispose(start())
  }
}
