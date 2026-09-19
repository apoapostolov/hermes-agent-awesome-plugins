/**
 * Sidebar Manager — Hermes desktop plugin.
 *
 * A dim list-ordered glyph after the New session Ctrl/N hint enters edit mode.
 * In edit mode, nav rows (Skills, Messaging, plugin pages, …) and session
 * sections (Pinned, Recents, platforms, Cron jobs) can be clicked on/off
 * and reordered from a grip with live HTML5 gap-opening, same idea as
 * provider-status and RSS Reader. Off items stay dim until you leave edit
 * mode, then they hide. Order and hidden ids persist in localStorage.
 */

const ID = 'sidebar-manager'
const KEY = 'hermes.sidebar-manager.v1'
const STYLE_ID = 'sidebar-manager-style'
const MIME = 'application/x-sbm-id'
const NEW_TOUR = 'sidebar-nav-new-session'
const PINNED_LABELS = new Set(['Pinned', 'المثبتة', 'ピン留め', '已置顶', '已釘選'])

const CSS = `
html:not([data-sbm-edit="1"]) [data-sbm-off="1"] { display: none !important; }
html[data-sbm-edit="1"] [data-sbm-off="1"] {
  opacity: 0.38;
  filter: grayscale(0.15);
}
[data-sbm-edit-btn] {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 1.125rem;
  height: 1.125rem;
  margin-left: 2px;
  flex-shrink: 0;
  opacity: 0.45;
  color: var(--ui-text-tertiary, currentColor);
  cursor: pointer;
  border-radius: 0.2rem;
  user-select: none;
  -webkit-app-region: no-drag;
}
[data-sbm-edit-btn]:hover { opacity: 0.9; color: var(--ui-text-secondary, currentColor); }
html[data-sbm-edit="1"] [data-sbm-edit-btn] {
  opacity: 1;
  color: var(--ui-accent, var(--theme-primary, currentColor));
}
[data-sbm-edit-btn] .codicon { font-size: 11px; line-height: 1; display: block; }
[data-sbm-grip] {
  display: none;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 18px;
  flex-shrink: 0;
  cursor: grab;
  color: var(--ui-text-quaternary, var(--ui-text-tertiary, currentColor));
  user-select: none;
  -webkit-user-drag: element;
}
html[data-sbm-edit="1"] [data-sbm-grip] { display: inline-flex; }
[data-sbm-grip]:active { cursor: grabbing; }
[data-sbm-grip] .codicon { font-size: 11px; line-height: 1; display: block; }
[data-sbm-dragging] {
  opacity: 0.42;
  outline: 1px dashed color-mix(in srgb, var(--ui-accent, currentColor) 70%, transparent);
  outline-offset: -1px;
}
`

let edit = false
let state = emptyState()
let drag = null
let didDrag = false
let clickGuard = false
let scheduled = false
let observer = null

function emptyState() {
  return { navOrder: [], navHidden: [], secOrder: [], secHidden: [] }
}

function loadState() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return emptyState()
    const data = JSON.parse(raw)
    return {
      navOrder: listOf(data.navOrder),
      navHidden: listOf(data.navHidden),
      secOrder: listOf(data.secOrder),
      secHidden: listOf(data.secHidden),
    }
  } catch {
    return emptyState()
  }
}

function listOf(value) {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
}

function saveState() {
  localStorage.setItem(KEY, JSON.stringify(state))
}

function previewOrder(ids, draggingId, dropIndex) {
  const list = Array.isArray(ids) ? ids : []
  if (!draggingId || typeof dropIndex !== 'number' || !Number.isFinite(dropIndex)) return list
  const moved = list.includes(draggingId)
  if (!moved) return list
  const rest = list.filter(id => id !== draggingId)
  const target = Math.min(Math.max(Math.trunc(dropIndex), 0), rest.length)
  return [...rest.slice(0, target), draggingId, ...rest.slice(target)]
}

function dropIndexAt(ids, draggingId, overId, isAfter) {
  const rest = (Array.isArray(ids) ? ids : []).filter(id => id !== draggingId)
  const base = rest.indexOf(overId)
  return base < 0 ? null : base + (isAfter ? 1 : 0)
}

function mergeOrder(saved, live) {
  const liveSet = new Set(live)
  const out = []
  for (const id of saved) {
    if (liveSet.has(id) && !out.includes(id)) out.push(id)
  }
  for (const id of live) {
    if (!out.includes(id)) out.push(id)
  }
  return out
}

function sameList(a, b) {
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return false
  return true
}

function setFlag(el, name, on) {
  const cur = el.getAttribute(name)
  if (on) {
    if (cur !== '1') el.setAttribute(name, '1')
  } else if (cur !== null) {
    el.removeAttribute(name)
  }
}

function setEdit(on) {
  edit = Boolean(on)
  const root = document.documentElement
  if (edit) {
    if (root.getAttribute('data-sbm-edit') !== '1') root.setAttribute('data-sbm-edit', '1')
  } else if (root.hasAttribute('data-sbm-edit')) {
    root.removeAttribute('data-sbm-edit')
  }
  paint()
}

function newSessionButton() {
  const tour = document.querySelector(`[data-tour="${NEW_TOUR}"]`)
  return tour ? tour.closest('[data-slot="sidebar-menu-button"]') || tour.closest('button') : null
}

function ensureEditBtn(button) {
  const icon = '<i class="codicon codicon-list-ordered" aria-hidden="true"></i>'
  let btn = button.querySelector(':scope > [data-sbm-edit-btn]')
  if (btn) {
    if (!btn.querySelector('.codicon-list-ordered')) btn.innerHTML = icon
    return btn
  }
  btn = document.createElement('span')
  btn.setAttribute('data-sbm-edit-btn', '1')
  btn.setAttribute('role', 'button')
  btn.setAttribute('tabindex', '0')
  btn.title = 'Edit sidebar'
  btn.innerHTML = icon
  const kbd = button.querySelector('[data-slot="kbd-group"]')
  if (kbd && kbd.parentNode === button) button.insertBefore(btn, kbd.nextSibling)
  else button.appendChild(btn)
  const toggle = event => {
    event.preventDefault()
    event.stopPropagation()
    setEdit(!edit)
  }
  btn.addEventListener('pointerdown', event => {
    event.preventDefault()
    event.stopPropagation()
  })
  btn.addEventListener('click', toggle)
  btn.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') toggle(event)
  })
  return btn
}

function navIdFrom(li) {
  const tour = li.querySelector('[data-tour^="sidebar-nav-"]')
  if (!tour) return ''
  const value = tour.getAttribute('data-tour') || ''
  if (value === NEW_TOUR) return ''
  return value.startsWith('sidebar-nav-') ? value.slice('sidebar-nav-'.length) : ''
}

function collectNav() {
  const button = newSessionButton()
  if (!button) return { ul: null, rows: [] }
  const ul = button.closest('[data-slot="sidebar-menu"]')
  if (!ul) return { ul: null, rows: [] }
  const rows = []
  for (const li of ul.querySelectorAll(':scope > [data-slot="sidebar-menu-item"]')) {
    const id = navIdFrom(li)
    if (!id) continue
    rows.push({ el: li, id, kind: 'nav' })
  }
  return { ul, rows }
}

function sectionLabel(group) {
  const label = group.querySelector('span.uppercase')
  return label ? label.textContent.trim() : ''
}

function collectSections() {
  const scope = document.querySelector('[data-sessions-mode]')
  if (!scope) return { parent: null, rows: [], search: false }
  const groups = [...scope.querySelectorAll(':scope > [data-slot="sidebar-group"]')]
  const search = !groups.some(group => PINNED_LABELS.has(sectionLabel(group)))
  if (search) return { parent: scope, rows: [], search: true }
  const rows = []
  for (const group of groups) {
    const id = sectionLabel(group)
    if (!id) continue
    rows.push({ el: group, id, kind: 'sec' })
  }
  return { parent: scope, rows, search: false }
}

function ensureGrip(host) {
  let grip = host.querySelector(':scope > [data-sbm-grip]')
  if (!grip) {
    grip = document.createElement('span')
    grip.setAttribute('data-sbm-grip', '1')
    grip.draggable = true
    grip.title = 'Drag to reorder'
    grip.innerHTML = '<i class="codicon codicon-gripper" aria-hidden="true"></i>'
    host.insertBefore(grip, host.firstChild)
    grip.addEventListener('dragstart', event => {
      const el = event.currentTarget.closest('[data-sbm-id]')
      if (el) onGripStart(event, el)
    })
    grip.addEventListener('dragend', onGripEnd)
  }
  return grip
}

function navGripHost(li) {
  return li.querySelector('[data-slot="sidebar-menu-button"]') || li.querySelector('button')
}

function secGripHost(group) {
  const header = group.firstElementChild
  if (!header) return null
  return header.querySelector(':scope > button') || header.querySelector(':scope > div') || header
}

function placeGrip(row, host) {
  for (const grip of [...row.el.querySelectorAll('[data-sbm-grip]')]) {
    if (!host || grip.parentNode !== host) grip.remove()
  }
  if (edit && host) ensureGrip(host)
}

function markRow(row) {
  if (row.el.getAttribute('data-sbm-id') !== row.id) row.el.setAttribute('data-sbm-id', row.id)
  if (row.el.getAttribute('data-sbm-kind') !== row.kind) row.el.setAttribute('data-sbm-kind', row.kind)
}

function applyHidden(row, hidden) {
  setFlag(row.el, 'data-sbm-off', hidden)
}

function applyOrder(parent, orderedEls, keepFirst) {
  if (!parent) return
  const wanted = []
  if (keepFirst && keepFirst.parentNode === parent) wanted.push(keepFirst)
  for (const el of orderedEls) {
    if (el.parentNode !== parent || el === keepFirst) continue
    if (!wanted.includes(el)) wanted.push(el)
  }
  const current = [...parent.children].filter(el => wanted.includes(el))
  let same = current.length === wanted.length
  if (same) {
    for (let i = 0; i < wanted.length; i++) {
      if (current[i] !== wanted[i]) {
        same = false
        break
      }
    }
  }
  if (same) return
  for (const el of wanted) parent.appendChild(el)
}

function liveIds(rows) {
  return rows.map(row => row.id)
}

function hiddenSet(kind) {
  return new Set(kind === 'nav' ? state.navHidden : state.secHidden)
}

function orderFor(kind, live) {
  const saved = kind === 'nav' ? state.navOrder : state.secOrder
  return mergeOrder(saved, live)
}

function writeOrder(kind, next) {
  if (kind === 'nav') {
    if (sameList(state.navOrder, next)) return
    state.navOrder = next
  } else {
    if (sameList(state.secOrder, next)) return
    state.secOrder = next
  }
  saveState()
}

function toggleHidden(kind, id) {
  const key = kind === 'nav' ? 'navHidden' : 'secHidden'
  const cur = new Set(state[key])
  if (cur.has(id)) cur.delete(id)
  else cur.add(id)
  state[key] = [...cur]
  saveState()
  paint()
}

function rowMap(rows) {
  const map = new Map()
  for (const row of rows) map.set(row.id, row)
  return map
}

function orderedEls(rows, ids) {
  const map = rowMap(rows)
  const out = []
  for (const id of ids) {
    const row = map.get(id)
    if (row) out.push(row.el)
  }
  return out
}

function currentDragIds() {
  if (!drag) return null
  return previewOrder(drag.ids, drag.id, drag.dropIndex)
}

function paintNav() {
  const { ul, rows } = collectNav()
  if (!ul) return
  const live = liveIds(rows)
  const ids = drag && drag.kind === 'nav' ? currentDragIds() : orderFor('nav', live)
  if (!(drag && drag.kind === 'nav')) {
    if (!sameList(state.navOrder, ids)) {
      state.navOrder = ids
      saveState()
    }
  }
  const hidden = hiddenSet('nav')
  for (const row of rows) {
    markRow(row)
    applyHidden(row, hidden.has(row.id))
    const host = navGripHost(row.el)
    placeGrip(row, host)
    setFlag(row.el, 'data-sbm-dragging', Boolean(drag && drag.kind === 'nav' && drag.id === row.id))
  }
  const newLi = newSessionButton()?.closest('[data-slot="sidebar-menu-item"]') || null
  applyOrder(ul, orderedEls(rows, ids), newLi)
}

function paintSections() {
  const { parent, rows, search } = collectSections()
  if (!parent || search) {
    if (parent) {
      for (const group of parent.querySelectorAll(':scope > [data-slot="sidebar-group"]')) {
        group.querySelectorAll('[data-sbm-grip]').forEach(el => el.remove())
      }
    }
    return
  }
  const live = liveIds(rows)
  const ids = drag && drag.kind === 'sec' ? currentDragIds() : orderFor('sec', live)
  if (!(drag && drag.kind === 'sec')) {
    if (!sameList(state.secOrder, ids)) {
      state.secOrder = ids
      saveState()
    }
  }
  const hidden = hiddenSet('sec')
  for (const row of rows) {
    markRow(row)
    applyHidden(row, hidden.has(row.id))
    const host = secGripHost(row.el)
    placeGrip(row, host)
    setFlag(row.el, 'data-sbm-dragging', Boolean(drag && drag.kind === 'sec' && drag.id === row.id))
  }
  applyOrder(parent, orderedEls(rows, ids), null)
}

function paint() {
  const button = newSessionButton()
  if (button) {
    const btn = ensureEditBtn(button)
    btn.title = edit ? 'Done editing sidebar' : 'Edit sidebar'
  }
  paintNav()
  paintSections()
}

function requestPaint() {
  if (scheduled) return
  scheduled = true
  requestAnimationFrame(() => {
    scheduled = false
    paint()
  })
}

function onGripStart(event, rowEl) {
  const id = rowEl.getAttribute('data-sbm-id')
  const kind = rowEl.getAttribute('data-sbm-kind')
  if (!id || !kind || !edit) {
    event.preventDefault()
    return
  }
  const rows = kind === 'nav' ? collectNav().rows : collectSections().rows
  const ids = orderFor(kind, liveIds(rows))
  const from = ids.indexOf(id)
  drag = { id, kind, ids, dropIndex: from < 0 ? 0 : from }
  didDrag = false
  event.dataTransfer.setData('text/plain', id)
  event.dataTransfer.setData(MIME, `${kind}:${id}`)
  event.dataTransfer.effectAllowed = 'move'
  try {
    event.dataTransfer.setDragImage(rowEl, 18, 12)
  } catch {
    /* some engines reject setDragImage on a detached-looking node */
  }
  setFlag(rowEl, 'data-sbm-dragging', true)
}

function updateDropFromPoint(event, overEl) {
  if (!drag || !overEl) return
  const overId = overEl.getAttribute('data-sbm-id')
  const overKind = overEl.getAttribute('data-sbm-kind')
  if (!overId || overKind !== drag.kind) return
  const rect = overEl.getBoundingClientRect()
  const after = event.clientY > rect.top + rect.height / 2
  const next = dropIndexAt(drag.ids, drag.id, overId, after)
  if (next === null || next === drag.dropIndex) return
  drag.dropIndex = next
  didDrag = true
  paint()
}

function onDragOver(event) {
  if (!drag) return
  const over = event.target.closest('[data-sbm-id]')
  if (!over || over.getAttribute('data-sbm-kind') !== drag.kind) return
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  updateDropFromPoint(event, over)
}

function commitDrag() {
  if (!drag) return
  const next = previewOrder(drag.ids, drag.id, drag.dropIndex)
  const kind = drag.kind
  drag = null
  writeOrder(kind, next)
  paint()
}

function onDrop(event) {
  if (!drag) return
  event.preventDefault()
  commitDrag()
}

function onGripEnd() {
  if (drag) commitDrag()
  if (didDrag) {
    clickGuard = true
    setTimeout(() => {
      clickGuard = false
    }, 0)
  }
  didDrag = false
}

function isTrailingSectionAction(event, group) {
  const header = group.firstElementChild
  if (!header || !header.contains(event.target)) return false
  const grip = event.target.closest('[data-sbm-grip]')
  if (grip) return true
  const labelBtn = header.querySelector('button')
  if (labelBtn && labelBtn.contains(event.target)) return false
  return true
}

function onClickCapture(event) {
  if (clickGuard) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  if (!edit) return
  if (event.target.closest('[data-sbm-edit-btn]')) return
  if (event.target.closest('[data-sbm-grip]')) {
    event.preventDefault()
    event.stopPropagation()
    return
  }
  const row = event.target.closest('[data-sbm-id]')
  if (!row) return
  const kind = row.getAttribute('data-sbm-kind')
  const id = row.getAttribute('data-sbm-id')
  if (!kind || !id) return
  if (kind === 'sec') {
    const header = row.firstElementChild
    if (!header || !header.contains(event.target)) return
    if (isTrailingSectionAction(event, row)) return
  }
  event.preventDefault()
  event.stopPropagation()
  toggleHidden(kind, id)
}

function onKeydown(event) {
  if (event.key === 'Escape' && edit) {
    event.stopPropagation()
    setEdit(false)
  }
}

function start() {
  state = loadState()
  document.getElementById(STYLE_ID)?.remove()
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = CSS
  document.head.appendChild(style)

  paint()
  observer = new MutationObserver(() => {
    if (drag) return
    requestPaint()
  })
  observer.observe(document.body, { childList: true, subtree: true })

  document.addEventListener('dragover', onDragOver, true)
  document.addEventListener('drop', onDrop, true)
  document.addEventListener('click', onClickCapture, true)
  window.addEventListener('keydown', onKeydown, true)

  return () => {
    observer?.disconnect()
    observer = null
    document.removeEventListener('dragover', onDragOver, true)
    document.removeEventListener('drop', onDrop, true)
    document.removeEventListener('click', onClickCapture, true)
    window.removeEventListener('keydown', onKeydown, true)
    document.getElementById(STYLE_ID)?.remove()
    document.documentElement.removeAttribute('data-sbm-edit')
    document.querySelectorAll('[data-sbm-edit-btn], [data-sbm-grip]').forEach(el => el.remove())
    document.querySelectorAll('[data-sbm-id]').forEach(el => {
      el.removeAttribute('data-sbm-id')
      el.removeAttribute('data-sbm-kind')
      el.removeAttribute('data-sbm-off')
      el.removeAttribute('data-sbm-dragging')
    })
    drag = null
    edit = false
  }
}

export default {
  id: ID,
  name: 'Sidebar Manager',
  description: 'Reorder and hide sidebar nav rows and session sections from a dim glyph next to New session.',
  defaultEnabled: false,
  register(ctx) {
    ctx.onDispose(start())
  },
}
