/**
 * Drag to Pin — Hermes desktop plugin.
 *
 * Makes the Pinned section of the Sessions sidebar a drop container:
 *
 *   drag a session row into Pinned    -> pin it at the drop slot
 *   drag a pinned row out to Sessions -> unpin it
 *
 * Why it rides the app's own pointer drag instead of native HTML5 DnD: the
 * session row already runs two gestures off one press — dnd-kit's
 * PointerSensor reorder (listeners spread on the row shell) and the pane
 * session-drag. Native DnD collided with both; a pointer drag on the same
 * threshold does not. Same lesson the core session-drag.ts records.
 *
 * The grabber ([data-reorder-handle]) is deliberately left alone: it stays
 * pure reorder. Dragging the row BODY is what pins/unpins.
 *
 * Row identity and store writes go through the SDK session-list API
 * (#116305 item 3): a SESSION_ROW_AREAS.leading marker carries the durable
 * session id, and pin/unpin/reset go through host.sessions. No fiber walks.
 */

import { host, SESSION_ROW_AREAS } from '@hermes/plugin-sdk'
import { jsx } from 'react/jsx-runtime'

const ID = 'drag-to-pin-session'
const ROW = '.row-hover'
const MARKER = '[data-dtp-session]'
const SKIP = '[data-row-actions], [data-reorder-handle]'
const OVER_ATTR = 'data-dtp-over'
const STYLE_ID = 'drag-to-pin-style'
const GAP_ID = 'drag-to-pin-gap'

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
#${GAP_ID} {
  position: fixed;
  z-index: 9999;
  height: 2px;
  pointer-events: none;
  border-radius: 1px;
  background: var(--ui-accent);
  display: none;
}
`

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

function pinnedRows(group) {
  if (!group) return []

  const content = group.querySelector('[data-slot="sidebar-group-content"]')

  return [...(content || group).querySelectorAll(ROW)]
}

/** Visual insert index among currently rendered pinned rows (0..length). */
function dropIndex(group, y) {
  const rows = pinnedRows(group)

  for (let i = 0; i < rows.length; i++) {
    const r = rows[i].getBoundingClientRect()

    if (y < r.top + r.height / 2) return i
  }

  return rows.length
}

function mark(group, on) {
  if (!group) return

  if (on) {
    group.setAttribute(OVER_ATTR, '1')
  } else {
    group.removeAttribute(OVER_ATTR)
  }
}

function gapEl() {
  return document.getElementById(GAP_ID)
}

function showGap(group, y) {
  const el = gapEl()
  if (!el || !group) return

  const rows = pinnedRows(group)
  const box = group.getBoundingClientRect()
  let top

  if (!rows.length) {
    const content = group.querySelector('[data-slot="sidebar-group-content"]')
    top = content ? content.getBoundingClientRect().top + 4 : box.bottom - 6
  } else {
    const i = dropIndex(group, y)

    top =
      i >= rows.length
        ? rows[rows.length - 1].getBoundingClientRect().bottom
        : rows[i].getBoundingClientRect().top
  }

  el.style.left = `${box.left + 8}px`
  el.style.width = `${Math.max(0, box.width - 16)}px`
  el.style.top = `${top - 1}px`
  el.style.display = 'block'
}

function hideGap() {
  const el = gapEl()
  if (el) el.style.display = 'none'
}

function clearMarks() {
  for (const node of document.querySelectorAll(`[${OVER_ATTR}]`)) {
    node.removeAttribute(OVER_ATTR)
  }

  hideGap()
}

// ── Row identity ─────────────────────────────────────────────────────────────

/**
 * The durable session id of a row, published by this plugin's own
 * SESSION_ROW_AREAS.leading marker. The id is the STORED (lineage root) id —
 * the one host.sessions.* addresses — so pins survive compression id rotation.
 */
function rowId(row) {
  const marker = row && row.querySelector(MARKER)

  return marker ? marker.getAttribute('data-dtp-session') || null : null
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

  const id = rowId(row)
  if (!id) return

  drag = {
    row,
    id,
    source,
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
  const overPinned = drag.source === 'recents' && contains(secs.pinned, x, y)
  const overRecents = drag.source === 'pinned' && contains(secs.recents, x, y)

  mark(secs.pinned, overPinned)
  mark(secs.recents, overRecents)

  if (overPinned) {
    showGap(secs.pinned, y)
  } else {
    hideGap()
  }
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
    if (pin) {
      host.sessions.pin(finished.id, true, dropIndex(secs.pinned, y))
    } else {
      host.sessions.pin(finished.id, false)
    }
  } catch (err) {
    console.warn(`[${ID}] pin toggle failed`, err)

    return
  }

  // dnd-kit ran off the same press. Its reorder is a no-op across lists
  // visually (the row leaves the list it was dragged from), but it flips
  // the flat list into MANUAL order — a sticky sort change the user never
  // asked for. Empty order ids switch the list back to its normal sort.
  // Re-apply the pin index after that write so a late dnd-kit permutation
  // cannot shove the new pin to the bottom.
  if (pin) {
    setTimeout(() => {
      try {
        host.sessions.reorder([])
      } catch {
        /* list may have unmounted */
      }

      try {
        host.sessions.pin(finished.id, true, dropIndex(secs.pinned, y))
      } catch {
        /* store call may have gone */
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

  const gap = document.createElement('div')
  gap.id = GAP_ID
  document.body.appendChild(gap)

  window.addEventListener('pointerdown', onPointerDown, true)
  document.addEventListener('click', onClickCapture, true)

  return () => {
    window.removeEventListener('pointerdown', onPointerDown, true)
    document.removeEventListener('click', onClickCapture, true)
    window.removeEventListener('pointermove', onPointerMove, true)
    window.removeEventListener('pointerup', onPointerUp, true)
    window.removeEventListener('pointercancel', onPointerCancel, true)
    document.getElementById(STYLE_ID)?.remove()
    document.getElementById(GAP_ID)?.remove()
    clearMarks()
    drag = null
  }
}

export default {
  id: ID,
  name: 'Drag to Pin',
  description: 'Drag a session into Pinned to pin it at the drop slot, drag it out to unpin.',
  defaultEnabled: true,
  register(ctx) {
    // Publishes the durable session id onto every row so the pointer gesture
    // can name rows without reading React internals.
    ctx.register({
      id: 'id-marker',
      area: SESSION_ROW_AREAS.leading,
      data: {
        render: ({ sessionId }) =>
          jsx('span', {
            'data-dtp-session': sessionId,
            style: { display: 'none' },
          }),
      },
    })

    ctx.onDispose(start())
  },
}
