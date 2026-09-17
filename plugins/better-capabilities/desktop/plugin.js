/**
 * Better Capabilities
 *
 * Capabilities → Plugins: a delete control to the right of the folder icon.
 * Capabilities → Skills (learned skills): Package (zip) between Edit and Archive,
 * plus a folder reveal and a delete control on that same row.
 * Installed | Presets | Browse: save and restore on/off sets for skills, tools, plugins.
 *
 * Delete sends the on-disk folder to the Recycle Bin through the plugin API.
 * Package downloads a zip of the skill folder (SKILL.md, references, scripts).
 */
import { host } from '@hermes/plugin-sdk'

const ID = 'better-capabilities'
const STYLE_ID = 'better-capabilities-style'
const BTN = 'data-bc-btn'
const MARK = 'data-bc-row'
const PRESET_STORE = 'hermes.better-capabilities.presets.v1'
const PRESET_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,59}$/

let rest = null
let painting = false

function onCapabilities() {
  const hash = String(window.location.hash || '')
  return hash.includes('/skills')
}

function pageKind() {
  const hash = String(window.location.hash || '')
  if (!hash.includes('/skills')) return null
  const query = hash.split('?')[1] || ''
  const tab = new URLSearchParams(query).get('tab')
  if (tab === 'plugins') return 'plugins'
  if (tab === 'toolsets') return 'tools'
  if (tab === 'mcp') return null
  return 'skills'
}

function kindLabel(kind) {
  if (kind === 'plugins') return 'Plugins'
  if (kind === 'tools') return 'Tools'
  return 'Skills'
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

async function desktopApi(opts) {
  const fn = window.hermesDesktop && window.hermesDesktop.api
  if (typeof fn !== 'function') throw new Error('Desktop API is not available.')
  return fn(opts)
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

function isHidden(el) {
  return Boolean(el && el.closest('[data-pane-hidden]'))
}

function pluginKeyFromRow(row) {
  const testid = row.getAttribute('data-testid') || ''
  const m = /^plugin-row-(.+)$/.exec(testid)
  if (m) return m[1]
  const id = row.getAttribute('id') || ''
  if (id.startsWith('plugin-')) return id.slice('plugin-'.length)
  return ''
}

function pluginKeyFromButton(btn) {
  const row = btn && btn.closest('[data-testid^="plugin-row-"]')
  return row ? pluginKeyFromRow(row) : ''
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
    const del = iconButton('codicon-trash', 'Remove plugin')
    del.setAttribute(BTN, 'delete')
    del.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      const liveName = pluginKeyFromButton(e.currentTarget) || name
      if (!liveName) return
      confirmRemove('plugin', liveName, () => void doDelete('plugin', liveName))
    })
    const wrap = document.createElement('span')
    wrap.className = slot.className
    wrap.setAttribute(BTN, 'wrap')
    wrap.appendChild(del)
    slot.insertAdjacentElement('afterend', wrap)
  }
}

function skillNameFromActionRow(row) {
  if (!row) return ''
  let sib = row.previousElementSibling
  while (sib) {
    const title = sib.tagName === 'H3' ? sib : sib.querySelector && sib.querySelector('h3')
    const text = title ? String(title.textContent || '').trim() : ''
    if (text) return text
    sib = sib.previousElementSibling
  }
  const pane = row.parentElement
  const fallback = pane && pane.querySelector('header h3, h3')
  return fallback ? String(fallback.textContent || '').trim() : ''
}

function liveSkillName(btn) {
  const row = btn && btn.parentElement
  return skillNameFromActionRow(row)
}

function skillMdDir(skillMdPath) {
  return String(skillMdPath || '').replace(/[\\/]+SKILL\.md$/i, '')
}

function isSkillMdRel(rel) {
  return !rel || /^SKILL\.md$/i.test(rel)
}

async function listSkillMarkdown(skillName) {
  const info = await desktopApi({ path: '/api/skills/content?name=' + encodeURIComponent(skillName) })
  const skillMd = info && info.path
  if (!skillMd) throw new Error('No SKILL.md path')
  const root = skillMdDir(skillMd)
  const files = [{ rel: 'SKILL.md', folder: '', label: 'SKILL.md', abs: skillMd }]
  const skip = { '.git': 1, __pycache__: 1, node_modules: 1 }
  const readDir = window.hermesDesktop && window.hermesDesktop.readDir
  if (typeof readDir !== 'function') return files
  async function walk(dir, prefix) {
    const res = await readDir(dir)
    const entries = (res && res.entries) || []
    const dirs = []
    const mds = []
    for (const ent of entries) {
      if (!ent || skip[ent.name]) continue
      if (ent.isDirectory) dirs.push(ent)
      else if (/\.md$/i.test(ent.name) && !(prefix === '' && /^SKILL\.md$/i.test(ent.name))) mds.push(ent)
    }
    mds.sort((a, b) => a.name.localeCompare(b.name))
    for (const file of mds) {
      const rel = prefix ? prefix + '/' + file.name : file.name
      files.push({
        rel,
        folder: prefix,
        label: prefix.includes('/') ? rel.slice(rel.indexOf('/') + 1) : file.name,
        abs: file.path,
      })
    }
    dirs.sort((a, b) => a.name.localeCompare(b.name))
    for (const dirEnt of dirs) {
      await walk(dirEnt.path, prefix ? prefix + '/' + dirEnt.name : dirEnt.name)
    }
  }
  await walk(root, '')
  return files
}

function nativeSkillBlocks(row) {
  const box = []
  let el = row.nextElementSibling
  while (el) {
    if (el.getAttribute && el.getAttribute('data-bc-preview')) {
      el = el.nextElementSibling
      continue
    }
    box.push(el)
    el = el.nextElementSibling
  }
  return box
}

function setNativeSkillVisible(row, visible) {
  for (const el of nativeSkillBlocks(row)) {
    if (visible) {
      if (el.getAttribute('data-bc-hid') === '1') {
        el.style.display = ''
        el.removeAttribute('data-bc-hid')
      }
    } else if (el.getAttribute('data-bc-hid') !== '1') {
      el.setAttribute('data-bc-hid', '1')
      el.style.display = 'none'
    }
  }
}

function previewEl(row) {
  let pre = row.parentElement && row.parentElement.querySelector('pre[data-bc-preview="1"]')
  if (pre) return pre
  pre = document.createElement('pre')
  pre.setAttribute('data-bc-preview', '1')
  pre.setAttribute(BTN, 'preview')
  pre.setAttribute('data-selectable-text', 'true')
  pre.className = 'overflow-auto whitespace-pre-wrap wrap-break-word rounded-lg border border-(--ui-stroke-tertiary) bg-(--ui-bg-quinary) p-3 font-mono text-[0.68rem] leading-relaxed'
  pre.style.display = 'none'
  const pane = row.parentElement
  if (pane) pane.appendChild(pre)
  return pre
}

function showSkillMd(row) {
  setNativeSkillVisible(row, true)
  const pre = row.parentElement && row.parentElement.querySelector('pre[data-bc-preview="1"]')
  if (pre) pre.style.display = 'none'
}

async function showOtherMd(row, absPath) {
  const readText = window.hermesDesktop && window.hermesDesktop.readFileText
  if (typeof readText !== 'function') throw new Error('Cannot read skill files in this desktop build.')
  const res = await readText(absPath)
  const text = res && res.text != null ? res.text : ''
  setNativeSkillVisible(row, false)
  const pre = previewEl(row)
  pre.textContent = text
  pre.style.display = ''
}

function closeFileMenus() {
  document.querySelectorAll('[data-bc-file-menu]').forEach((menu) => {
    menu.style.display = 'none'
  })
}

function placeFileMenu(trigger, menu) {
  const rect = trigger.getBoundingClientRect()
  const pad = 8
  menu.style.position = 'fixed'
  menu.style.top = rect.bottom + 4 + 'px'
  menu.style.left = rect.left + 'px'
  menu.style.right = 'auto'
  menu.style.width = 'max-content'
  menu.style.maxWidth = Math.max(160, window.innerWidth - pad * 2) + 'px'
  menu.style.maxHeight = Math.max(120, window.innerHeight - rect.bottom - pad) + 'px'
  requestAnimationFrame(() => {
    const box = menu.getBoundingClientRect()
    if (box.right > window.innerWidth - pad) {
      menu.style.left = Math.max(pad, window.innerWidth - pad - box.width) + 'px'
    }
    if (box.left < pad) menu.style.left = pad + 'px'
  })
}

function paintSkillFilePicker(row, editBtn, skillName) {
  let wrap = row.querySelector('[data-bc-files]')
  if (!wrap) {
    wrap = document.createElement('span')
    wrap.setAttribute('data-bc-files', '1')
    wrap.setAttribute(BTN, 'files')
    wrap.className = 'bc-file-wrap'
    const trigger = document.createElement('button')
    trigger.type = 'button'
    trigger.className = 'bc-file-trigger'
    trigger.setAttribute(BTN, 'files-trigger')
    trigger.textContent = 'SKILL.md'
    const menu = document.createElement('div')
    menu.className = 'bc-file-menu'
    menu.setAttribute('data-bc-file-menu', '1')
    menu.style.display = 'none'
    trigger.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      const open = menu.style.display !== 'none'
      closeFileMenus()
      if (!open) {
        menu.style.display = 'block'
        placeFileMenu(trigger, menu)
      }
    })
    wrap.append(trigger, menu)
    editBtn.insertAdjacentElement('afterend', wrap)
  }
  if (wrap.getAttribute('data-bc-skill') !== skillName) {
    wrap.setAttribute('data-bc-skill', skillName)
    wrap.setAttribute('data-bc-rel', 'SKILL.md')
    const trigger = wrap.querySelector('.bc-file-trigger')
    if (trigger) trigger.textContent = 'SKILL.md'
    showSkillMd(row)
    void fillSkillFileMenu(wrap, row, skillName)
  } else if (!isSkillMdRel(wrap.getAttribute('data-bc-rel'))) {
    setNativeSkillVisible(row, false)
  }
}

async function fillSkillFileMenu(wrap, row, skillName) {
  const menu = wrap.querySelector('[data-bc-file-menu]')
  const trigger = wrap.querySelector('.bc-file-trigger')
  if (!menu || !trigger) return
  menu.replaceChildren()
  let files
  try {
    files = await listSkillMarkdown(skillName)
  } catch (err) {
    const empty = document.createElement('div')
    empty.className = 'bc-file-head'
    empty.textContent = 'Could not list markdown files'
    menu.appendChild(empty)
    return
  }
  if (wrap.getAttribute('data-bc-skill') !== skillName) return
  let lastFolder = null
  for (const file of files) {
    const folderKey = file.folder || (isSkillMdRel(file.rel) ? '' : '/')
    if (folderKey && folderKey !== lastFolder) {
      lastFolder = folderKey
      const head = document.createElement('div')
      head.className = 'bc-file-head'
      head.textContent = folderKey === '/' ? '/' : '/' + file.folder
      menu.appendChild(head)
    }
    const item = document.createElement('button')
    item.type = 'button'
    item.className = 'bc-file-item'
    item.setAttribute(BTN, 'file-item')
    item.textContent = file.label
    item.addEventListener('click', (e) => {
      e.preventDefault()
      e.stopPropagation()
      menu.style.display = 'none'
      wrap.setAttribute('data-bc-rel', file.rel)
      trigger.textContent = isSkillMdRel(file.rel) ? 'SKILL.md' : file.label
      if (isSkillMdRel(file.rel)) showSkillMd(row)
      else void showOtherMd(row, file.abs).catch((err) => {
        notify('error', 'Could not preview', String(err && err.message ? err.message : err))
      })
    })
    menu.appendChild(item)
  }
}

function paintSkillRow() {
  const buttons = document.querySelectorAll('button')
  for (const btn of buttons) {
    if (btn.getAttribute(BTN)) continue
    if (isHidden(btn)) continue
    const label = String(btn.textContent || '').trim()
    if (label !== 'Edit') continue
    const row = btn.parentElement
    if (!row) continue
    const sibs = row.querySelectorAll('button')
    let archive = null
    for (const sib of sibs) {
      if (String(sib.textContent || '').trim() === 'Archive') archive = sib
    }
    if (!archive) continue
    const name = skillNameFromActionRow(row)
    if (!name) continue
    if (row.getAttribute('data-bc-skill') !== name) row.setAttribute('data-bc-skill', name)
    paintSkillFilePicker(row, btn, name)

    if (!row.querySelector('[' + BTN + '="zip"]')) {
      const zip = textButton('Package (zip)')
      zip.setAttribute(BTN, 'zip')
      zip.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const liveName = liveSkillName(e.currentTarget)
        if (!liveName) {
          notify('error', 'Could not package', 'No skill name on this row.')
          return
        }
        void doZip(liveName)
      })
      row.insertBefore(zip, archive)
    }

    if (!row.querySelector('[' + BTN + '="folder"]')) {
      const folder = iconButton('codicon-folder-opened', 'Open skill folder')
      folder.setAttribute(BTN, 'folder')
      folder.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const liveName = liveSkillName(e.currentTarget)
        if (!liveName) return
        void doReveal('skill', liveName)
      })
      const del = iconButton('codicon-trash', 'Remove skill')
      del.setAttribute(BTN, 'delete')
      del.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        const liveName = liveSkillName(e.currentTarget)
        if (!liveName) return
        confirmRemove('skill', liveName, () => void doDelete('skill', liveName))
      })
      row.appendChild(folder)
      row.appendChild(del)
    }

    row.setAttribute(MARK, '1')
  }
}

function loadPresetStore() {
  try {
    const raw = window.localStorage.getItem(PRESET_STORE)
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed && typeof parsed === 'object') return parsed
  } catch {
    // fall through
  }
  return { skills: {}, tools: {}, plugins: {} }
}

function savePresetStore(store) {
  window.localStorage.setItem(PRESET_STORE, JSON.stringify(store))
}

function presetsFor(kind) {
  const store = loadPresetStore()
  const map = store[kind] && typeof store[kind] === 'object' ? store[kind] : {}
  return map
}

function presetOrder(kind) {
  const map = presetsFor(kind)
  const raw = Array.isArray(map._order) ? map._order : []
  const order = []
  for (const name of raw) {
    if (name && name !== '_order' && map[name] && !order.includes(name)) order.push(name)
  }
  for (const name of Object.keys(map)) {
    if (name === '_order') continue
    if (!order.includes(name)) order.push(name)
  }
  return order
}

function setPresetOrder(kind, order) {
  const store = loadPresetStore()
  if (!store[kind] || typeof store[kind] !== 'object') store[kind] = {}
  store[kind]._order = order.filter((name) => name && name !== '_order')
  savePresetStore(store)
}

function writePreset(kind, name, payload) {
  const store = loadPresetStore()
  if (!store[kind] || typeof store[kind] !== 'object') store[kind] = {}
  store[kind][name] = payload
  const order = Array.isArray(store[kind]._order) ? store[kind]._order.slice() : []
  if (!order.includes(name)) order.push(name)
  store[kind]._order = order
  savePresetStore(store)
}

function removePreset(kind, name) {
  const store = loadPresetStore()
  if (store[kind] && typeof store[kind] === 'object') {
    delete store[kind][name]
    if (Array.isArray(store[kind]._order)) {
      store[kind]._order = store[kind]._order.filter((item) => item !== name)
    }
  }
  savePresetStore(store)
}

function renamePreset(kind, from, to) {
  const store = loadPresetStore()
  const map = store[kind] && typeof store[kind] === 'object' ? store[kind] : {}
  if (!map[from]) throw new Error('No preset named ' + from)
  if (map[to] && to !== from) throw new Error('A preset named ' + to + ' already exists.')
  map[to] = map[from]
  if (to !== from) delete map[from]
  if (Array.isArray(map._order)) {
    map._order = map._order.map((item) => (item === from ? to : item))
    if (!map._order.includes(to)) map._order.push(to)
  }
  store[kind] = map
  savePresetStore(store)
}

function switchOn(el) {
  return el && el.getAttribute('data-state') === 'checked'
}

function clickSwitchTo(el, on) {
  if (!el) return false
  if (switchOn(el) === on) return true
  el.click()
  return true
}

function switchInTitleRow(title) {
  const rows = document.querySelectorAll('.row-hover')
  for (const row of rows) {
    if (isHidden(row)) continue
    const label = row.querySelector('span.block.truncate')
    if (!label) continue
    if (String(label.textContent || '').trim() !== title) continue
    return row.querySelector('[data-slot="switch"]')
  }
  return null
}

function currentProfileName() {
  try {
    const atom = host.state && host.state.profile
    const value = atom && typeof atom.get === 'function' ? atom.get() : ''
    return String(value || 'default').trim() || 'default'
  } catch {
    return 'default'
  }
}

async function listProfileNames() {
  const names = []
  const seen = {}
  function add(name) {
    const n = String(name || '').trim()
    if (!n || seen[n]) return
    seen[n] = 1
    names.push(n)
  }
  add('default')
  add(currentProfileName())
  try {
    const res = await desktopApi({ path: '/api/profiles' })
    for (const row of (res && res.profiles) || []) {
      if (row && row.name) add(row.name)
    }
  } catch {
    // profile list is optional
  }
  return names
}

async function snapshotAgentForProfile(profile) {
  const agent = {}
  const listed = await host.request('plugins.manage', { action: 'list', profile })
  for (const row of listed && listed.plugins ? listed.plugins : []) {
    if (row && row.key) agent[row.key] = row.status === 'enabled'
  }
  return agent
}

async function snapshotKind(kind) {
  if (kind === 'skills') {
    const rows = await desktopApi({ path: '/api/skills' })
    const enabled = {}
    for (const row of rows || []) {
      if (row && row.name) enabled[row.name] = !!row.enabled
    }
    return { enabled }
  }
  if (kind === 'tools') {
    const rows = await desktopApi({ path: '/api/tools/toolsets' })
    const enabled = {}
    for (const row of rows || []) {
      if (row && row.name) enabled[row.name] = !!row.enabled
    }
    return { enabled }
  }
  const desktop = {}
  try {
    const raw = window.localStorage.getItem('hermes.desktop.pluginDecisions.v2')
    const decisions = raw ? JSON.parse(raw) : {}
    if (decisions && typeof decisions === 'object') {
      for (const [id, on] of Object.entries(decisions)) desktop[id] = !!on
    }
  } catch {
    // ignore
  }
  document.querySelectorAll('[data-testid^="plugin-row-"]').forEach((row) => {
    if (isHidden(row)) return
    const key = pluginKeyFromRow(row)
    const switches = [...row.querySelectorAll('[data-slot="switch"]')]
    if (key && switches[0]) desktop[key] = switchOn(switches[0])
  })
  const agentByProfile = {}
  const profiles = await listProfileNames()
  for (const profile of profiles) {
    try {
      agentByProfile[profile] = await snapshotAgentForProfile(profile)
    } catch {
      // skip profiles the gateway cannot list
    }
  }
  const current = currentProfileName()
  const agent = agentByProfile[current] || agentByProfile.default || {}
  return { desktop, agent, agentByProfile }
}

async function applyKind(kind, payload) {
  if (kind === 'skills' || kind === 'tools') {
    const enabled = (payload && payload.enabled) || {}
    for (const [name, on] of Object.entries(enabled)) {
      const sw = switchInTitleRow(name)
      if (clickSwitchTo(sw, on)) continue
      if (kind === 'skills') {
        await desktopApi({ path: '/api/skills/toggle', method: 'PUT', body: { name, enabled: on } })
      } else {
        await desktopApi({
          path: '/api/tools/toolsets/' + encodeURIComponent(name),
          method: 'PUT',
          body: { enabled: on },
        })
      }
    }
    return
  }
  const desktop = (payload && payload.desktop) || {}
  const agent = (payload && payload.agent) || {}
  const agentByProfile =
    payload && payload.agentByProfile && typeof payload.agentByProfile === 'object'
      ? payload.agentByProfile
      : null
  for (const [id, on] of Object.entries(desktop)) {
    const row = document.querySelector('[data-testid="plugin-row-' + id + '"]')
    const sw = row && row.querySelector('[data-slot="switch"]')
    if (clickSwitchTo(sw, on)) continue
    try {
      const raw = window.localStorage.getItem('hermes.desktop.pluginDecisions.v2')
      const decisions = raw ? JSON.parse(raw) : {}
      decisions[id] = on
      window.localStorage.setItem('hermes.desktop.pluginDecisions.v2', JSON.stringify(decisions))
    } catch {
      // ignore
    }
  }
  const current = currentProfileName()
  const maps = agentByProfile || { [current]: agent }
  for (const [profile, map] of Object.entries(maps)) {
    if (!map || typeof map !== 'object') continue
    for (const [key, on] of Object.entries(map)) {
      const row = document.querySelector('[data-testid="plugin-row-' + key + '"]')
      const switches = row ? [...row.querySelectorAll('[data-slot="switch"]')] : []
      const agentSw = switches.length > 1 ? switches[1] : null
      if (profile === current && clickSwitchTo(agentSw, on)) continue
      try {
        await host.request('plugins.manage', { action: 'toggle', key, enable: on, profile })
      } catch {
        // skip keys the backend rejects
      }
    }
  }
}

function presetNames(kind) {
  return presetOrder(kind)
}

function persistPresetListOrder(kind, listEl) {
  const order = []
  listEl.querySelectorAll('.bc-preset-row[data-bc-preset]').forEach((row) => {
    const name = row.getAttribute('data-bc-preset')
    if (name) order.push(name)
  })
  setPresetOrder(kind, order)
}

function bindPresetReorder(listEl, kind) {
  if (listEl.getAttribute('data-bc-drag') === '1') return
  listEl.setAttribute('data-bc-drag', '1')
  let dragName = ''
  listEl.addEventListener('dragstart', (e) => {
    const grip = e.target.closest('[data-bc-grip]')
    if (!grip) {
      e.preventDefault()
      return
    }
    const row = grip.closest('.bc-preset-row')
    dragName = row ? row.getAttribute('data-bc-preset') || '' : ''
    if (!dragName) {
      e.preventDefault()
      return
    }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', dragName)
    row.classList.add('bc-preset-dragging')
  })
  listEl.addEventListener('dragend', () => {
    listEl.querySelectorAll('.bc-preset-dragging').forEach((row) => row.classList.remove('bc-preset-dragging'))
    if (dragName) persistPresetListOrder(kind, listEl)
    dragName = ''
  })
  listEl.addEventListener('dragover', (e) => {
    e.preventDefault()
    if (!dragName) return
    const over = e.target.closest('.bc-preset-row')
    if (!over) return
    let dragging = null
    listEl.querySelectorAll('.bc-preset-row').forEach((row) => {
      if (row.getAttribute('data-bc-preset') === dragName) dragging = row
    })
    if (!dragging || dragging === over) return
    const rect = over.getBoundingClientRect()
    const before = e.clientY < rect.top + rect.height / 2
    listEl.insertBefore(dragging, before ? over : over.nextSibling)
  })
}

function renderPresetList(kind, listEl, nameInput) {
  listEl.replaceChildren()
  const names = presetNames(kind)
  if (names.length === 0) {
    const empty = document.createElement('div')
    empty.className = 'bc-dialog-body'
    empty.textContent = 'No presets yet.'
    listEl.appendChild(empty)
    return
  }
  for (const name of names) {
    const row = document.createElement('div')
    row.className = 'bc-preset-row'
    row.setAttribute('data-bc-preset', name)
    const grip = document.createElement('span')
    grip.className = 'bc-grip'
    grip.setAttribute('data-bc-grip', '1')
    grip.setAttribute('title', 'Reorder')
    grip.setAttribute('aria-label', 'Reorder')
    grip.draggable = true
    const gripIcon = document.createElement('i')
    gripIcon.className = 'codicon codicon-gripper'
    gripIcon.setAttribute('aria-hidden', 'true')
    grip.appendChild(gripIcon)
    const label = document.createElement('div')
    label.className = 'bc-preset-name'
    label.textContent = name
    const actions = document.createElement('div')
    actions.className = 'bc-preset-actions'
    const apply = iconButton('codicon-play', 'Apply')
    apply.addEventListener('click', () => void onApplyPreset(kind, name))
    const overwrite = iconButton('codicon-replace', 'Overwrite')
    overwrite.addEventListener('click', () => void onSavePreset(kind, name, true, nameInput))
    const rename = iconButton('codicon-edit', 'Rename')
    rename.addEventListener('click', () => void onRenamePreset(kind, name, nameInput, listEl))
    const del = iconButton('codicon-trash', 'Delete')
    del.classList.add('bc-danger')
    del.addEventListener('click', () => {
      removePreset(kind, name)
      renderPresetList(kind, listEl, nameInput)
      notify('success', 'Deleted ' + name, 'The ' + kindLabel(kind).toLowerCase() + ' preset is gone.')
    })
    actions.append(apply, overwrite, rename, del)
    row.append(grip, label, actions)
    listEl.appendChild(row)
  }
}

async function onSavePreset(kind, name, overwrite, nameInput) {
  const trimmed = String(name || '').trim()
  if (!PRESET_NAME_RE.test(trimmed)) {
    notify('error', 'Name is not valid', 'Use letters, numbers, spaces, or hyphens. Start with a letter or number.')
    return
  }
  const existing = presetsFor(kind)[trimmed]
  if (existing && !overwrite) {
    notify('error', trimmed + ' already exists', 'Use Overwrite on that row, or pick another name.')
    return
  }
  try {
    const payload = await snapshotKind(kind)
    payload.savedAt = Date.now()
    writePreset(kind, trimmed, payload)
    if (nameInput) nameInput.value = trimmed
    const listEl = document.getElementById('bc-preset-list')
    if (listEl) renderPresetList(kind, listEl, nameInput)
    notify('success', overwrite ? 'Overwrote ' + trimmed : 'Saved ' + trimmed, kindLabel(kind) + ' on/off state is stored.')
  } catch (err) {
    notify('error', 'Could not save preset', String(err && err.message ? err.message : err))
  }
}

async function onApplyPreset(kind, name) {
  const payload = presetsFor(kind)[name]
  if (!payload) {
    notify('error', 'Missing preset', name)
    return
  }
  try {
    await applyKind(kind, payload)
    notify('success', 'Applied ' + name, kindLabel(kind) + ' switches now match that preset.')
  } catch (err) {
    notify('error', 'Could not apply ' + name, String(err && err.message ? err.message : err))
  }
}

function onRenamePreset(kind, from, nameInput, listEl) {
  const to = String((nameInput && nameInput.value) || '').trim()
  if (!to || to === from) {
    notify('error', 'Type the new name', 'Put the new name in the field, then click Rename.')
    return
  }
  if (!PRESET_NAME_RE.test(to)) {
    notify('error', 'Name is not valid', 'Use letters, numbers, spaces, or hyphens.')
    return
  }
  try {
    renamePreset(kind, from, to)
    nameInput.value = to
    renderPresetList(kind, listEl, nameInput)
    notify('success', 'Renamed preset', from + ' is now ' + to + '.')
  } catch (err) {
    notify('error', 'Could not rename', String(err && err.message ? err.message : err))
  }
}

function openPresetDialog(kind) {
  closeOverlay()
  const overlay = document.createElement('div')
  overlay.id = 'bc-overlay'
  overlay.innerHTML =
    '<div class="bc-dialog bc-dialog-wide" role="dialog" aria-modal="true">' +
    '<div class="bc-dialog-title">' +
    escapeHtml(kindLabel(kind)) +
    ' presets</div>' +
    '<div class="bc-dialog-body">Save the current on/off set, or apply one you already stored.</div>' +
    '<div class="bc-preset-save">' +
    '<input class="bc-input" data-bc-name="1" maxlength="60" placeholder="Name" />' +
    '</div>' +
    '<div id="bc-preset-list" class="bc-preset-list"></div>' +
    '<div class="bc-dialog-actions"><button type="button" class="bc-text-btn" data-bc-cancel="1">Close</button></div>' +
    '</div>'
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeOverlay()
  })
  overlay.querySelector('[data-bc-cancel]').addEventListener('click', closeOverlay)
  const nameInput = overlay.querySelector('[data-bc-name]')
  const listEl = overlay.querySelector('#bc-preset-list')
  const saveRow = overlay.querySelector('.bc-preset-save')
  const saveBtn = iconButton('codicon-save', 'Save')
  saveBtn.setAttribute('data-bc-save', '1')
  saveBtn.addEventListener('click', () => {
    void onSavePreset(kind, nameInput.value, false, nameInput)
  })
  saveRow.appendChild(saveBtn)
  nameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      void onSavePreset(kind, nameInput.value, false, nameInput)
    }
  })
  bindPresetReorder(listEl, kind)
  renderPresetList(kind, listEl, nameInput)
  document.body.appendChild(overlay)
  nameInput.focus()
}

function makePresetTab() {
  const sample = document.querySelector('[data-capability-tabs] button')
  const btn = document.createElement('button')
  btn.type = 'button'
  btn.setAttribute(BTN, 'presets')
  btn.setAttribute('data-bc-presets', '1')
  btn.setAttribute('aria-pressed', 'false')
  if (sample) {
    btn.className = sample.className
    const sampleSpan = sample.querySelector('span')
    const span = document.createElement('span')
    if (sampleSpan) span.className = sampleSpan.className
    span.textContent = 'Presets'
    btn.appendChild(span)
  } else {
    btn.className = 'bc-text-tab'
    const span = document.createElement('span')
    span.className = 'bc-text-tab-label'
    span.textContent = 'Presets'
    btn.appendChild(span)
  }
  btn.addEventListener('click', (e) => {
    e.preventDefault()
    e.stopPropagation()
    const kind = pageKind()
    if (!kind) return
    openPresetDialog(kind)
  })
  return btn
}

function browseButton(bar) {
  const buttons = bar.querySelectorAll('button')
  for (const btn of buttons) {
    if (btn.getAttribute('data-bc-presets')) continue
    if (String(btn.textContent || '').trim() === 'Browse') return btn
  }
  return null
}

function paintPresetTab() {
  const kind = pageKind()
  if (!kind) return
  if (kind === 'tools') ensureToolsPresetBar()
  const bars = document.querySelectorAll('[data-capability-tabs], [data-bc-tools-tabs]')
  for (const bar of bars) {
    if (isHidden(bar)) continue
    if (bar.querySelector('[data-bc-presets]')) continue
    const tab = makePresetTab()
    const browse = browseButton(bar)
    if (browse) bar.insertBefore(tab, browse)
    else bar.appendChild(tab)
  }
}

function ensureToolsPresetBar() {
  if (document.querySelector('[data-bc-tools-tabs]')) return
  const section = document.querySelector('section.flex.h-full.min-w-0.flex-col')
  if (!section) return
  const col = section.querySelector(':scope > div.flex.h-full.flex-col')
  if (!col) return
  const bar = document.createElement('div')
  bar.className = 'flex shrink-0 items-center gap-4 px-3 py-1'
  bar.setAttribute('data-bc-tools-tabs', '1')
  bar.setAttribute(BTN, 'tools-tabs')
  const profile = col.querySelector(':scope > div.border-b')
  if (profile) profile.insertAdjacentElement('afterend', bar)
  else col.insertBefore(bar, col.firstChild)
}

function sweep() {
  if (!onCapabilities() || painting) return
  painting = true
  try {
    paintPresetTab()
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
    .bc-text-tab {
      display: inline-flex;
      align-items: center;
      height: 1.75rem;
      padding: 0 0.25rem;
      border: none;
      background: transparent;
      color: var(--ui-text-tertiary, inherit);
      cursor: pointer;
      font: inherit;
      font-size: var(--conversation-caption-font-size, 0.75rem);
      font-weight: 500;
    }
    .bc-text-tab-label { text-decoration: underline; text-underline-offset: 4px; text-decoration-color: color-mix(in srgb, currentColor 25%, transparent); }
    .bc-text-tab:hover { color: var(--foreground, inherit); }
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
    .bc-dialog-wide { min-width: 22rem; max-width: 28rem; }
    .bc-dialog-title { font-size: 0.9rem; font-weight: 600; }
    .bc-dialog-body { margin-top: 0.35rem; font-size: 0.75rem; color: var(--ui-text-tertiary, inherit); }
    .bc-dialog-actions { display: flex; gap: 0.5rem; justify-content: flex-end; margin-top: 0.75rem; }
    .bc-preset-save { display: flex; gap: 0.4rem; align-items: center; margin-top: 0.7rem; }
    .bc-input {
      flex: 1;
      min-width: 0;
      height: 1.7rem;
      border: 1px solid var(--ui-stroke-tertiary, var(--border));
      border-radius: 0.375rem;
      background: var(--ui-bg-quinary, transparent);
      color: var(--foreground);
      padding: 0 0.45rem;
      font: inherit;
      font-size: 0.75rem;
    }
    .bc-preset-list { margin-top: 0.7rem; display: flex; flex-direction: column; gap: 0.2rem; max-height: 14rem; overflow: auto; }
    .bc-preset-row { display: flex; align-items: center; gap: 0.15rem; }
    .bc-preset-row.bc-preset-dragging { opacity: 0.45; }
    .bc-grip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 1.15rem;
      height: 1.5rem;
      color: var(--ui-text-tertiary, inherit);
      cursor: grab;
    }
    .bc-grip:active { cursor: grabbing; }
    .bc-grip .codicon { font-size: 0.85rem; }
    .bc-preset-name { flex: 1; min-width: 0; font-size: 0.78rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bc-preset-actions { display: flex; flex-wrap: nowrap; justify-content: flex-end; }
    .bc-file-wrap { position: relative; display: inline-flex; }
    .bc-file-trigger {
      border: 1px solid var(--ui-stroke-tertiary, var(--border));
      background: transparent;
      color: var(--ui-text-secondary, inherit);
      cursor: pointer;
      font: inherit;
      font-size: 0.72rem;
      padding: 0.12rem 0.45rem;
      border-radius: 0.375rem;
      max-width: 10rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .bc-file-trigger:hover { color: var(--foreground, inherit); }
    .bc-file-menu {
      z-index: 40;
      min-width: 12rem;
      width: max-content;
      overflow: auto;
      padding: 0.25rem 0;
      border: 1px solid var(--ui-stroke-tertiary, var(--border));
      border-radius: 0.45rem;
      background: var(--ui-bg-elevated, var(--card, var(--background)));
    }
    .bc-file-head {
      padding: 0.28rem 0.55rem 0.1rem;
      font-size: 0.62rem;
      font-weight: 600;
      color: var(--ui-text-tertiary, inherit);
      white-space: nowrap;
    }
    .bc-file-item {
      display: block;
      width: 100%;
      text-align: left;
      border: none;
      background: transparent;
      color: var(--foreground);
      cursor: pointer;
      font: inherit;
      font-size: 0.72rem;
      padding: 0.22rem 0.7rem;
      white-space: nowrap;
    }
    .bc-file-item:hover { background: var(--chrome-action-hover, color-mix(in srgb, var(--foreground) 8%, transparent)); }
  `
  document.head.appendChild(style)
}

export default {
  id: ID,
  name: 'Better Capabilities',
  description:
    'Delete plugins and skills from Capabilities, zip a learned skill, and save on/off presets.',
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
    const onDocDown = (e) => {
      if (e.target && e.target.closest && e.target.closest('[data-bc-files]')) return
      closeFileMenus()
    }
    window.addEventListener('hashchange', onHash)
    document.addEventListener('mousedown', onDocDown, true)
    ctx.onDispose(() => {
      observer.disconnect()
      window.removeEventListener('hashchange', onHash)
      document.removeEventListener('mousedown', onDocDown, true)
      document.getElementById(STYLE_ID)?.remove()
      closeOverlay()
      document.querySelectorAll('[' + BTN + ']').forEach((el) => el.remove())
      document.querySelectorAll('[' + MARK + ']').forEach((el) => el.removeAttribute(MARK))
    })
  },
}
