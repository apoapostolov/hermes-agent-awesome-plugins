/**
 * Better Capabilities
 *
 * Capabilities → Plugins: a delete control to the right of the folder icon.
 * Capabilities → Skills (learned skills): Package (zip) between Edit and Archive,
 * plus a folder reveal and a delete control on that same row.
 *
 * Delete sends the on-disk folder to the Recycle Bin through the plugin API.
 * Package downloads a zip of the skill folder (SKILL.md, references, scripts).
 */
import { host } from '@hermes/plugin-sdk'

const ID = 'better-capabilities'
const STYLE_ID = 'better-capabilities-style'
const BTN = 'data-bc-btn'
const MARK = 'data-bc-row'

let rest = null
let painting = false

function onCapabilities() {
  const hash = String(window.location.hash || '')
  return hash.includes('/skills')
}

function notify(kind, title, message) {
  try {
    host.notify({ kind, title, message })
  } catch {
    // toast is optional
  }
}

async function api(path, body) {
  if (typeof rest !== 'function') throw new Error('Plugin API is not ready.')
  const opts = body ? { method: 'POST', body } : undefined
  return rest(path, opts)
}

function downloadZip(filename, b64) {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i)
  const blob = new Blob([bytes], { type: 'application/zip' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

function iconButton(codicon, label) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.setAttribute('aria-label', label)
  btn.title = label
  btn.setAttribute(BTN, '1')
  btn.className = 'bc-icon-btn'
  const i = document.createElement('i')
  i.className = 'codicon ' + codicon
  i.setAttribute('aria-hidden', 'true')
  btn.appendChild(i)
  return btn
}

function textButton(label) {
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.textContent = label
  btn.setAttribute(BTN, '1')
  btn.className = 'bc-text-btn'
  return btn
}

function closeOverlay() {
  document.getElementById('bc-overlay')?.remove()
}

function confirmRemove(kind, name, onYes) {
  closeOverlay()
  const overlay = document.createElement('div')
  overlay.id = 'bc-overlay'
  overlay.innerHTML =
    '<div class="bc-dialog" role="dialog" aria-modal="true">' +
    '<div class="bc-dialog-title">Remove ' +
    escapeHtml(name) +
    '?</div>' +
    '<div class="bc-dialog-body">The ' +
    (kind === 'plugin' ? 'plugin' : 'skill') +
    ' folder goes to the Recycle Bin.</div>' +
    '<div class="bc-dialog-actions">' +
    '<button type="button" class="bc-text-btn" data-bc-cancel="1">Cancel</button>' +
    '<button type="button" class="bc-text-btn bc-danger" data-bc-ok="1">Remove</button>' +
    '</div></div>'
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeOverlay()
  })
  overlay.querySelector('[data-bc-cancel]').addEventListener('click', closeOverlay)
  overlay.querySelector('[data-bc-ok]').addEventListener('click', () => {
    closeOverlay()
    onYes()
  })
  document.body.appendChild(overlay)
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

async function doDelete(kind, name) {
  try {
    const res = await api('/delete', { kind, name })
    const moved = res && res.result === 'moved'
    notify(
      'success',
      'Removed ' + name,
      moved
        ? 'The folder could not go to the Recycle Bin, so it was moved aside.'
        : 'The folder is in the Recycle Bin. Refresh Capabilities if the row is still listed.'
    )
  } catch (err) {
    notify('error', 'Could not remove ' + name, String(err && err.message ? err.message : err))
  }
}

async function doZip(name) {
  try {
    const res = await api('/zip', { kind: 'skill', name })
    if (!res || !res.b64 || !res.filename) throw new Error('Zip response was empty.')
    downloadZip(res.filename, res.b64)
    notify('success', 'Packaged ' + name, res.filename + ' is downloading.')
  } catch (err) {
    notify('error', 'Could not package ' + name, String(err && err.message ? err.message : err))
  }
}

async function doReveal(kind, name) {
  try {
    const res = await api('/resolve', { kind, name })
    const path = res && res.path
    if (!path) throw new Error('No folder path.')
    const reveal = window.hermesDesktop && window.hermesDesktop.revealPath
    if (typeof reveal === 'function') {
      await reveal(path)
      return
    }
    notify('info', name, path)
  } catch (err) {
    notify('error', 'Could not open folder', String(err && err.message ? err.message : err))
  }
}

function pluginKeyFromRow(row) {
  const testid = row.getAttribute('data-testid') || ''
  const m = /^plugin-row-(.+)$/.exec(testid)
  if (m) return m[1]
  const id = row.getAttribute('id') || ''
  if (id.startsWith('plugin-')) return id.slice('plugin-'.length)
  return ''
}

function paintPluginRows() {
  const folders = document.querySelectorAll('[data-testid^="plugin-row-"] .codicon-folder-opened')
  for (const icon of folders) {
    const row = icon.closest('[data-testid^="plugin-row-"]')
    if (!row) continue
    const name = pluginKeyFromRow(row)
    if (!name) continue
    const folderBtn = icon.closest('button')
    if (!folderBtn) continue
    const slot = folderBtn.parentElement
    if (!slot) continue
    const hostSlot = slot.parentElement
    if (!hostSlot) continue
    if (hostSlot.querySelector('[' + BTN + '="delete"]')) continue
    const del = iconButton('codicon-trash', 'Remove ' + name)
    del.setAttribute(BTN, 'delete')
    del.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      confirmRemove('plugin', name, () => void doDelete('plugin', name))
    })
    const wrap = document.createElement('span')
    wrap.className = slot.className
    wrap.setAttribute(BTN, 'wrap')
    wrap.appendChild(del)
    slot.insertAdjacentElement('afterend', wrap)
  }
}

function skillNameFromActionRow(row) {
  const header = row.previousElementSibling
  if (!header) return ''
  const title = header.querySelector('h3')
  return title ? String(title.textContent || '').trim() : ''
}

function paintSkillRow() {
  const buttons = document.querySelectorAll('button')
  let edit = null
  let archive = null
  let row = null
  for (const btn of buttons) {
    if (btn.getAttribute(BTN)) continue
    const label = String(btn.textContent || '').trim()
    if (label !== 'Edit') continue
    const parent = btn.parentElement
    if (!parent) continue
    const sibs = parent.querySelectorAll('button')
    let foundArchive = null
    for (const sib of sibs) {
      if (String(sib.textContent || '').trim() === 'Archive') foundArchive = sib
    }
    if (!foundArchive) continue
    edit = btn
    archive = foundArchive
    row = parent
    break
  }
  if (!edit || !archive || !row) return
  if (row.getAttribute(MARK) === '1') return
  const name = skillNameFromActionRow(row)
  if (!name) return

  if (!row.querySelector('[' + BTN + '="zip"]')) {
    const zip = textButton('Package (zip)')
    zip.setAttribute(BTN, 'zip')
    zip.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      void doZip(name)
    })
    row.insertBefore(zip, archive)
  }

  if (!row.querySelector('[' + BTN + '="folder"]')) {
    const folder = iconButton('codicon-folder-opened', 'Open skill folder')
    folder.setAttribute(BTN, 'folder')
    folder.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      void doReveal('skill', name)
    })
    const del = iconButton('codicon-trash', 'Remove ' + name)
    del.setAttribute(BTN, 'delete')
    del.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      confirmRemove('skill', name, () => void doDelete('skill', name))
    })
    row.appendChild(folder)
    row.appendChild(del)
  }

  row.setAttribute(MARK, '1')
}

function sweep() {
  if (!onCapabilities() || painting) return
  painting = true
  try {
    paintPluginRows()
    paintSkillRow()
  } finally {
    painting = false
  }
}

function injectStyle() {
  document.getElementById(STYLE_ID)?.remove()
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
    .bc-icon-btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.75rem;
      height: 1.75rem;
      border: none;
      background: transparent;
      color: var(--ui-text-tertiary, inherit);
      cursor: pointer;
      border-radius: 0.375rem;
    }
    .bc-icon-btn:hover { color: var(--foreground, inherit); background: var(--chrome-action-hover, transparent); }
    .bc-icon-btn .codicon { font-size: 0.85rem; }
    .bc-text-btn {
      border: none;
      background: transparent;
      color: var(--ui-text-secondary, inherit);
      cursor: pointer;
      font: inherit;
      font-size: 0.75rem;
      padding: 0.15rem 0.4rem;
      border-radius: 0.375rem;
    }
    .bc-text-btn:hover { color: var(--foreground, inherit); }
    .bc-danger { color: var(--ui-danger, #f87171); }
    .bc-danger:hover { color: var(--ui-danger, #f87171); }
    #bc-overlay {
      position: fixed;
      inset: 0;
      z-index: 9999;
      display: flex;
      align-items: center;
      justify-content: flex-start;
      padding: 2rem;
      background: color-mix(in srgb, black 22%, transparent);
    }
    .bc-dialog {
      min-width: 16rem;
      max-width: 22rem;
      padding: 0.9rem 1rem;
      border: 1px solid var(--ui-stroke-tertiary, var(--border));
      border-radius: 0.6rem;
      background: var(--ui-bg-elevated, var(--card, var(--background)));
      color: var(--foreground);
    }
    .bc-dialog-title { font-size: 0.9rem; font-weight: 600; }
    .bc-dialog-body { margin-top: 0.35rem; font-size: 0.75rem; color: var(--ui-text-tertiary, inherit); }
    .bc-dialog-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.75rem; }
  `
  document.head.appendChild(style)
}

export default {
  id: ID,
  name: 'Better Capabilities',
  description:
    'Delete plugins and skills from Capabilities, and zip a learned skill from the Edit / Archive row.',
  defaultEnabled: false,
  register(ctx) {
    rest = typeof ctx.rest === 'function' ? ctx.rest : null
    injectStyle()
    sweep()
    let scheduled = false
    const observer = new MutationObserver(() => {
      if (scheduled) return
      scheduled = true
      requestAnimationFrame(() => {
        scheduled = false
        sweep()
      })
    })
    observer.observe(document.body, { childList: true, subtree: true })
    const onHash = () => sweep()
    window.addEventListener('hashchange', onHash)
    ctx.onDispose(() => {
      observer.disconnect()
      window.removeEventListener('hashchange', onHash)
      document.getElementById(STYLE_ID)?.remove()
      closeOverlay()
      document.querySelectorAll('[' + BTN + ']').forEach((el) => el.remove())
      document.querySelectorAll('[' + MARK + ']').forEach((el) => el.removeAttribute(MARK))
    })
  },
}
