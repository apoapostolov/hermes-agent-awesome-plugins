/**
 * Memory Review Command for Hermes.
 *
 * Adds one row to the native app context menu (the shell fallback that
 * replaced the Electron menu). The row stays grayed out when memory is
 * clean. When a staged batch is waiting or a store is over budget it
 * becomes a one-click send of `/memory pending` through the composer.
 */

const ID = 'memory-review-command'
const MENU = '[data-slot="dropdown-menu-content"][data-state="open"]'
const ITEM_ATTR = 'data-mrc-item'
const SEP_ATTR = 'data-mrc-sep'
const DOT = ' \u00b7\u00a0'
const COMMAND = '/memory pending'

let rest = null
let lastState = null
let fetchGen = 0

function visibleComposerTarget() {
  const nodes = document.querySelectorAll('[data-composer-target]')
  for (const node of nodes) {
    if (node.closest('[data-pane-hidden]')) continue
    if (node.dataset.composerTarget) return node.dataset.composerTarget
  }
  return 'main'
}

function visibleComposerSurface() {
  const target = visibleComposerTarget()
  const nodes = document.querySelectorAll('[data-composer-target]')
  let fallback = null
  for (const node of nodes) {
    if (node.closest('[data-pane-hidden]')) continue
    if (!fallback) fallback = node
    if (node.dataset.composerTarget === target) return node
  }
  return fallback
}

function sendMemoryPending() {
  const surface = visibleComposerSurface()
  const target = (surface && surface.dataset.composerTarget) || visibleComposerTarget()
  const surfaceId = surface && surface.dataset.composerSurfaceId
  window.dispatchEvent(
    new CustomEvent('hermes:composer-insert', {
      detail: { mode: 'prefix', target, text: COMMAND },
    })
  )
  window.dispatchEvent(
    new CustomEvent('hermes:composer-focus', {
      detail: { target },
    })
  )
  if (!surfaceId) return
  window.setTimeout(() => {
    window.dispatchEvent(
      new CustomEvent('hermes:composer-submit', {
        detail: { surfaceId, target, text: COMMAND },
      })
    )
  }, 40)
}

function labelFor(state) {
  if (!state || !state.ok) {
    return { text: 'Memory: review' + DOT + 'state unknown', enabled: false }
  }
  const pending = Number(state.pending) || 0
  const memFull = Boolean(state.memory_full)
  const userFull = Boolean(state.user_full)
  const full = memFull || userFull
  if (pending <= 0 && !full) {
    return { text: 'Memory: review', enabled: false }
  }
  let fullSuffix = ''
  if (memFull && userFull) fullSuffix = 'store full'
  else if (userFull) fullSuffix = 'user store full'
  else if (memFull) fullSuffix = 'memory store full'
  if (pending > 0 && fullSuffix) {
    return { text: 'Pending: ' + pending + DOT + fullSuffix, enabled: true }
  }
  if (pending > 0) {
    return { text: 'Memory: review pending (' + pending + ')', enabled: true }
  }
  return { text: 'Memory: store full', enabled: true }
}

function isShellMenu(menu) {
  if (!(menu instanceof Element)) return false
  if (menu.getAttribute('data-slot') !== 'dropdown-menu-content') return false
  if (menu.getAttribute('data-state') !== 'open') return false
  const text = menu.textContent || ''
  return text.includes('New chat') && (text.includes('Settings') || text.includes('Update Hermes'))
}

function applyRow(row, state) {
  const { text, enabled } = labelFor(state)
  const label = row.querySelector('[data-mrc-label]')
  if (label && label.textContent !== text) label.textContent = text
  const disabled = enabled ? 'false' : 'true'
  if (row.getAttribute('aria-disabled') !== disabled) {
    row.setAttribute('aria-disabled', disabled)
  }
  if (enabled) {
    if (row.hasAttribute('data-disabled')) row.removeAttribute('data-disabled')
    if (row.style.opacity !== '1') row.style.opacity = '1'
    if (row.style.pointerEvents !== 'auto') row.style.pointerEvents = 'auto'
  } else {
    if (row.getAttribute('data-disabled') !== '') row.setAttribute('data-disabled', '')
    if (row.style.opacity !== '0.5') row.style.opacity = '0.5'
    if (row.style.pointerEvents !== 'none') row.style.pointerEvents = 'none'
  }
}

function makeSeparator() {
  const sep = document.createElement('div')
  sep.setAttribute(SEP_ATTR, '1')
  sep.setAttribute('data-slot', 'dropdown-menu-separator')
  sep.setAttribute('role', 'separator')
  sep.className = '-mx-1 my-1 h-px bg-(--ui-stroke-tertiary)'
  return sep
}

function makeRow() {
  const row = document.createElement('div')
  row.setAttribute(ITEM_ATTR, '1')
  row.setAttribute('data-slot', 'dropdown-menu-item')
  row.setAttribute('role', 'menuitem')
  row.tabIndex = -1
  row.className =
    'relative flex items-center gap-2 rounded-md px-2 py-1 text-xs outline-hidden select-none'
  const icon = document.createElement('i')
  icon.className = 'codicon codicon-note'
  icon.style.fontSize = '0.875rem'
  const label = document.createElement('span')
  label.setAttribute('data-mrc-label', '1')
  row.appendChild(icon)
  row.appendChild(label)
  row.addEventListener('pointerdown', event => {
    event.preventDefault()
    event.stopPropagation()
  })
  row.addEventListener('click', event => {
    event.preventDefault()
    event.stopPropagation()
    const enabled = row.getAttribute('aria-disabled') !== 'true'
    if (!enabled) return
    sendMemoryPending()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
  })
  applyRow(row, lastState)
  return row
}

function enhanceMenu(menu) {
  if (!isShellMenu(menu)) return
  let row = menu.querySelector('[' + ITEM_ATTR + ']')
  if (!row) {
    if (!menu.querySelector('[' + SEP_ATTR + ']')) menu.appendChild(makeSeparator())
    row = makeRow()
    menu.appendChild(row)
  }
  applyRow(row, lastState)
  if (menu.dataset.mrcFetch === '1') return
  menu.dataset.mrcFetch = '1'
  const gen = ++fetchGen
  Promise.resolve()
    .then(() => (rest ? rest('/state') : Promise.resolve({ ok: false })))
    .then(data => {
      if (gen !== fetchGen) return
      lastState = data && typeof data === 'object' ? data : { ok: false }
      const live = menu.querySelector('[' + ITEM_ATTR + ']')
      if (live) applyRow(live, lastState)
    })
    .catch(() => {
      if (gen !== fetchGen) return
      lastState = { ok: false }
      const live = menu.querySelector('[' + ITEM_ATTR + ']')
      if (live) applyRow(live, lastState)
    })
}

function start() {
  let scheduled = false
  const scan = () => {
    scheduled = false
    document.querySelectorAll(MENU).forEach(enhanceMenu)
  }
  const observer = new MutationObserver(() => {
    if (scheduled) return
    scheduled = true
    requestAnimationFrame(scan)
  })
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['data-state'],
  })
  scan()
  return () => {
    fetchGen += 1
    observer.disconnect()
    document.querySelectorAll('[' + ITEM_ATTR + '], [' + SEP_ATTR + ']').forEach(node => node.remove())
  }
}

export default {
  id: ID,
  name: 'Memory Review Command',
  description: 'Native menu command that sends /memory pending when a review is waiting.',
  defaultEnabled: false,
  register(ctx) {
    rest = ctx.rest
    ctx.onDispose(start())
  },
}
