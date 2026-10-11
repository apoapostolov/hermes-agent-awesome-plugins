/**
 * Memory-Review for Hermes.
 *
 * Palette + shell-menu command opens a Hermes-style dialog: checkbox each
 * staged write, select all, approve or reject the selection. Never applies
 * a write without that click.
 */

import {
  cn,
  Codicon,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Button,
  Checkbox,
  Tip as Tooltip,
  STATUSBAR_AREAS,
  host,
  usePluginI18n,
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useState } from 'react'

const ID = 'memory-review'
const MENU = '[data-slot="dropdown-menu-content"][data-state="open"]'
const ITEM_ATTR = 'data-mrc-item'
const SEP_ATTR = 'data-mrc-sep'
const DOT = ' \u00b7\u00a0'
const OPEN_EVENT = 'hermes-mrc-open'
const SOURCE = 'https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/personal/memory-review'
const STYLE_ID = 'memory-review-style'

const EN = {
  title: 'Memory review',
  source: 'Source on GitHub',
  memory: 'Memory',
  user: 'User',
  all: 'All',
  none: 'none',
  entry: 'entry',
  entries: 'entries',
  approve: 'Approve',
  reject: 'Reject',
  consolidate: 'Consolidate',
  working: 'Working',
  add: 'Add',
  remove: 'Remove',
  replace: 'Replace',
  userProfile: 'User profile',
  memoryNotes: 'Memory notes',
  noPending: 'No pending writes.',
  readFail: 'Could not read pending writes.',
  noComposer: 'No composer for a consolidation round',
  promptReady: 'Prompt ready in the composer. Send it to start consolidation.',
  requestFailed: 'request failed',
  stateUnknown: 'Memory' + DOT + 'state unknown',
  storeFull: 'store full',
  userStoreFull: 'user store full',
  memoryStoreFull: 'memory store full',
  memoryStoreFullLabel: 'Memory: store full',
  paletteLabel: 'Memory: pending',
  paletteDetail: 'opens review',
  paletteClean: 'clean',
  pending: n => 'Memory: pending (' + n + ')',
  pendingFull: (n, suffix) => 'Pending: ' + n + DOT + suffix,
  approved: n => 'Approved ' + n,
  approvedFailed: (n, failed, err) => 'Approved ' + n + ', ' + failed + ' failed' + (err ? ': ' + err : ''),
  rejected: n => 'Rejected ' + n,
  count: (sel, total) => sel + ' / ' + total,
}
const ES = {
  title: 'Revisión de memoria',
  source: 'Código en GitHub',
  memory: 'Memoria',
  user: 'Usuario',
  all: 'Todas',
  none: 'ninguna',
  entry: 'entrada',
  entries: 'entradas',
  approve: 'Aprobar',
  reject: 'Rechazar',
  consolidate: 'Consolidar',
  working: 'Trabajando',
  add: 'Añadir',
  remove: 'Quitar',
  replace: 'Reemplazar',
  userProfile: 'Perfil de usuario',
  memoryNotes: 'Notas de memoria',
  noPending: 'No hay escrituras pendientes.',
  readFail: 'No se pudieron leer las escrituras pendientes.',
  noComposer: 'No hay compositor para una ronda de consolidación',
  promptReady: 'El prompt está en el compositor. Envíalo para iniciar la consolidación.',
  requestFailed: 'la petición falló',
  stateUnknown: 'Memoria' + DOT + 'estado desconocido',
  storeFull: 'almacén lleno',
  userStoreFull: 'almacén de usuario lleno',
  memoryStoreFull: 'almacén de memoria lleno',
  memoryStoreFullLabel: 'Memoria: almacén lleno',
  paletteLabel: 'Memoria: pendientes',
  paletteDetail: 'abre la revisión',
  paletteClean: 'limpio',
  pending: n => 'Memoria: pendientes (' + n + ')',
  pendingFull: (n, suffix) => 'Pendientes: ' + n + DOT + suffix,
  approved: n => 'Aprobadas ' + n,
  approvedFailed: (n, failed, err) => 'Aprobadas ' + n + ', ' + failed + ' fallidas' + (err ? ': ' + err : ''),
  rejected: n => 'Rechazadas ' + n,
  count: (sel, total) => sel + ' / ' + total,
}
const LOCALES = { en: EN, es: ES }
let i18nT = null
function tr(key, ...args) {
  if (i18nT) return i18nT(key, ...args)
  const msg = EN[key]
  if (typeof msg === 'function') return msg(...args)
  return msg == null ? key : msg
}


let rest = null
let lastState = null
let fetchGen = 0
let openExternal = null

function openReview() {
  window.dispatchEvent(new CustomEvent(OPEN_EVENT))
}

function openSource(e) {
  e.preventDefault()
  openExternal?.(SOURCE)
}

function hasGlyph(menu, name) {
  return Boolean(menu.querySelector('.codicon-' + name))
}

function isShellMenu(menu) {
  if (!(menu instanceof Element)) return false
  if (menu.getAttribute('data-slot') !== 'dropdown-menu-content') return false
  if (menu.getAttribute('data-state') !== 'open') return false
  const start = hasGlyph(menu, 'add')
  const chrome = hasGlyph(menu, 'settings-gear') || hasGlyph(menu, 'cloud-download')
  return start && chrome
}

function labelFor(state) {
  if (!state || !state.ok) {
    return { text: tr('stateUnknown'), enabled: false }
  }
  const pending = Number(state.pending) || 0
  const memFull = Boolean(state.memory_full)
  const userFull = Boolean(state.user_full)
  const full = memFull || userFull
  if (pending <= 0 && !full) {
    return { text: tr('memory'), enabled: false }
  }
  let fullSuffix = ''
  if (memFull && userFull) fullSuffix = tr('storeFull')
  else if (userFull) fullSuffix = tr('userStoreFull')
  else if (memFull) fullSuffix = tr('memoryStoreFull')
  if (pending > 0 && fullSuffix) {
    return { text: tr('pendingFull', pending, fullSuffix), enabled: true }
  }
  if (pending > 0) {
    return { text: tr('pending', pending), enabled: true }
  }
  return { text: tr('memoryStoreFullLabel'), enabled: true }
}

function sessionId() {
  try {
    return host.state.focusedSessionId.get() || null
  } catch {
    return null
  }
}

function runSlash(command) {
  const sid = sessionId()
  if (!sid || !host.request) return Promise.resolve('')
  return host
    .request('slash.exec', { session_id: sid, command })
    .then(res => String((res && (res.output || res.message || res.result)) || ''))
}

function overLimit(err) {
  return /over the limit/i.test(String(err || ''))
}

async function seatPrompt(text) {
  // SDK composer draft API (#116305 item 1): seat the prompt as a prefix so
  // the user sees and sends it. Fail-closed when no visible surface answers.
  let ok = false
  try {
    ok = await host.composer.insertText(null, text, { mode: 'prefix' })
  } catch {
    ok = false
  }
  if (ok) host.composer.focus(null)
  return ok
}

function compactPrompt(target) {
  const file = target === 'user' ? 'USER.md' : 'MEMORY.md'
  return [
    'The user clicked Consolidate in Memory-Review.',
    'Run one memory consolidation round on ' + file + '.',
    'Follow the memory-compaction skill.',
    'Target at most 70% of that store char cap.',
    'Merge overlapping entries and drop only ephemeral facts.',
    'Never touch skills, identity, credentials, or hard rules.',
    'Use one memory tool batch. This click is the approval to apply it.',
  ].join(' ')
}

function parsePendingOutput(text) {
  const items = []
  for (const line of String(text || '').split(/\r?\n/)) {
    const m = line.match(/^\s+(\S+)(?:\s+\[(auto)\])?\s+(.*)$/)
    if (!m) continue
    if (m[1] === 'Apply:' || /pending$/i.test(m[1])) continue
    const summary = (m[3] || '').trim()
    items.push({
      id: m[1],
      origin: m[2] === 'auto' ? 'background_review' : '',
      summary,
      target: / on user\b/.test(summary) ? 'user' : 'memory',
      action: 'batch',
      ops: 1,
    })
  }
  return items
}

function opBody(action, raw) {
  let t = String(raw || '').trim()
  if (action === 'replace') {
    const arrow = t.indexOf(' -> ')
    if (arrow >= 0) t = t.slice(arrow + 4).trim()
  }
  return t
}

function parseSummaryOps(summary) {
  let s = String(summary || '')
  const pref = s.match(/^background review consolidation \(batch on (user|memory)\):\s*/i)
  const target = pref ? pref[1].toLowerCase() : ''
  if (pref) s = s.slice(pref[0].length)
  const hits = []
  const re = /-\s*(add|replace|remove):\s*/gi
  let m
  while ((m = re.exec(s))) {
    hits.push({ action: m[1].toLowerCase(), at: m.index, len: m[0].length })
  }
  const ops = []
  if (!hits.length) {
    const t = s.trim()
    if (t) ops.push({ action: 'replace', text: t })
    return { target, ops }
  }
  for (let i = 0; i < hits.length; i++) {
    const start = hits[i].at + hits[i].len
    const end = i + 1 < hits.length ? hits[i + 1].at : s.length
    const chunk = s.slice(start, end).replace(/;\s*$/, '').trim()
    ops.push({ action: hits[i].action, text: opBody(hits[i].action, chunk) })
  }
  return { target, ops }
}

function displayParts(item) {
  let target = item.target === 'user' ? 'user' : 'memory'
  let ops = Array.isArray(item.ops_detail) && item.ops_detail.length ? item.ops_detail : null
  if (!ops) {
    const parsed = parseSummaryOps(item.summary)
    if (parsed.target) target = parsed.target
    ops = parsed.ops
  }
  const action = (ops[0] && ops[0].action) || 'replace'
  const text = ops
    .filter(o => o.action !== 'remove')
    .map(o => o.text)
    .filter(Boolean)
    .join(DOT)
  return { target, action, text }
}

function actionGlyph(action) {
  if (action === 'add') return 'add'
  if (action === 'remove') return 'trash'
  return 'replace'
}

function pickAll(items) {
  const sel = {}
  for (const item of items || []) {
    if (item && item.id) sel[item.id] = true
  }
  return sel
}

function StoreMeter({ glyph, label, info }) {
  if (!info) return null
  const used = Number(info.used)
  const limit = Number(info.limit)
  const pct =
    limit > 0
      ? Math.max(0, Math.min(100, Math.round((100 * used) / limit)))
      : Math.max(0, Math.min(100, Number(info.pct) || 0))
  const n = Number(info.entries) || 0
  return jsxs('div', {
    className: 'flex items-center gap-1.5 text-[0.65rem] leading-none text-(--ui-text-quaternary)',
    children: [
      jsx(Codicon, { name: glyph, size: '0.65rem' }),
      jsx('span', { children: label }),
      jsx('span', {
        className: 'tabular-nums',
        children: n + ' ' + (n === 1 ? tr('entry') : tr('entries')),
      }),
      jsx('span', { className: 'tabular-nums', children: pct + '%' }),
      jsx('div', {
        className: 'h-1.5 w-10 shrink-0 overflow-hidden rounded-full',
        style: {
          background: 'color-mix(in srgb, var(--ui-text-quaternary) 18%, transparent)',
        },
        children: jsx('div', {
          className: 'h-full rounded-full',
          style: {
            width: pct + '%',
            background: 'color-mix(in srgb, var(--ui-text-tertiary) 55%, transparent)',
            transition: 'width 320ms ease',
          },
        }),
      }),
    ],
  })
}

function refreshState() {
  const gen = ++fetchGen
  const restP = rest ? rest('/state').catch(() => null) : Promise.resolve(null)
  return restP.then(data => {
    if (gen !== fetchGen) return lastState
    const restItems = data && Array.isArray(data.items) ? data.items : []
    const finish = items => {
      lastState = {
        ok: !(data && data.ok === false && !items.length),
        pending: items.length || Number(data && data.pending) || 0,
        memory_full: Boolean(data && data.memory_full),
        user_full: Boolean(data && data.user_full),
        stores: (data && data.stores) || null,
        items,
      }
      return lastState
    }
    if (data && data.stores) return finish(restItems)
    return runSlash('/memory pending')
      .catch(() => '')
      .then(text => {
        if (gen !== fetchGen) return lastState
        return finish(restItems.length ? restItems : parsePendingOutput(text))
      })
  })
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
    openReview()
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
  refreshState().then(() => {
    const live = menu.querySelector('[' + ITEM_ATTR + ']')
    if (live) applyRow(live, lastState)
  })
}

function startMenu() {
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

function useGlassOn() {
  const [on, setOn] = useState(
    () => typeof document !== 'undefined' && document.documentElement.hasAttribute('data-hermes-glass')
  )
  useEffect(() => {
    const el = document.documentElement
    const mo = new MutationObserver(() => setOn(el.hasAttribute('data-hermes-glass')))
    mo.observe(el, { attributes: true, attributeFilter: ['data-hermes-glass'] })
    return () => mo.disconnect()
  }, [])
  return on
}

function ReviewDialog({ open, onOpenChange }) {
  const t = usePluginI18n(ID)
  const glass = useGlassOn()
  const [state, setState] = useState(() => lastState || { ok: true, items: [] })
  const [picked, setPicked] = useState(() => pickAll((lastState && lastState.items) || []))
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState('')
  const [fails, setFails] = useState({})

  useEffect(() => {
    if (!open) return
    let alive = true
    setNote('')
    refreshState().then(data => {
      if (!alive) return
      const next = data || { ok: false, items: [] }
      setState(next)
      setPicked(pickAll(next.items))
    })
    return () => {
      alive = false
    }
  }, [open])

  useEffect(() => {
    if (!open || !glass) return
    const apply = () => {
      document.querySelectorAll('[data-slot="dialog-overlay"]').forEach(el => {
        el.style.background = 'rgb(0 0 0 / 0.06)'
        el.style.backdropFilter = 'blur(10px)'
        el.style.webkitBackdropFilter = 'blur(10px)'
      })
    }
    apply()
    const id = requestAnimationFrame(apply)
    return () => {
      cancelAnimationFrame(id)
      document.querySelectorAll('[data-slot="dialog-overlay"]').forEach(el => {
        el.style.background = ''
        el.style.backdropFilter = ''
        el.style.webkitBackdropFilter = ''
      })
    }
  }, [open, glass])

  if (!open) return null

  const items = Array.isArray(state.items) ? state.items : []
  const ids = items.map(item => item.id).filter(Boolean)
  const selected = ids.filter(id => picked[id])
  const allOn = ids.length > 0 && selected.length === ids.length
  const fitFail = items.find(item => overLimit(fails[item.id]))

  const toggleAll = value => {
    const next = {}
    if (value) for (const id of ids) next[id] = true
    setPicked(next)
  }

  const compact = async () => {
    if (busy) return
    const target = fitFail && displayParts(fitFail).target === 'user' ? 'user' : 'memory'
    if (!(await seatPrompt(compactPrompt(target)))) {
      setNote(tr('noComposer'))
      return
    }
    setBusy(false)
    setNote(tr('promptReady'))
  }

  const run = action => {
    if (!selected.length || busy) return
    setBusy(true)
    setNote('')
    const all = selected.length === ids.length
    const restDecide = rest
      ? rest('/decide', { method: 'POST', body: { action, ids: selected } })
      : Promise.reject(new Error('no rest'))
    const viaSlash = () => {
      const verb = action === 'reject' ? 'reject' : 'approve'
      if (all) return runSlash('/memory ' + verb + ' all')
      return selected.reduce(
        (p, id) => p.then(() => runSlash('/memory ' + verb + ' ' + id)),
        Promise.resolve('')
      )
    }
    restDecide
      .then(out => {
        if (!out || out.ok === false) throw new Error((out && out.error) || 'decide failed')
        return out
      })
      .catch(() => viaSlash().then(() => ({ ok: true })))
      .then(out => {
        const applied = Number(out && out.applied) || 0
        const failed = (out && out.failed) || []
        const err = failed[0] && failed[0].error ? String(failed[0].error).split('\n')[0] : ''
        const nextFails = {}
        for (const row of failed) {
          if (row && row.id) nextFails[row.id] = row.error || 'failed'
        }
        setFails(nextFails)
        if (action === 'approve') {
          setNote(
            failed.length
              ? tr('approvedFailed', applied, failed.length, err)
              : tr('approved', applied)
          )
        } else {
          setFails({})
          setNote(tr('rejected', out.rejected || selected.length))
        }
        return refreshState()
      })
      .then(data => {
        const next = data || { ok: false, items: [] }
        setState(next)
        setPicked(pickAll(next.items))
      })
      .catch(err => {
        setNote(err && err.message ? String(err.message) : tr('requestFailed'))
      })
      .finally(() => setBusy(false))
  }

  return jsx(Dialog, {
    open,
    onOpenChange,
    children: jsx(DialogContent, {
      fitContent: true,
      'data-context-menu-skip': '',
      className: cn(
        'min-w-[28rem] max-w-lg rounded-xl shadow-nous border-(--ui-accent)',
        glass
          ? 'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_42%,transparent)] backdrop-blur-2xl'
          : 'bg-(--ui-chat-bubble-background)'
      ),
      bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
      children: [
        jsxs(DialogHeader, {
          className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2',
          children: [
            jsx(DialogTitle, { children: t('title') }),
            jsx('a', {
              href: SOURCE,
              title: t('source'),
              target: '_blank',
              rel: 'noreferrer',
              onClick: openSource,
              className:
                'inline-flex items-center text-(--ui-text-quaternary) hover:text-(--ui-text-tertiary)',
              children: jsx(Codicon, { name: 'github', size: '0.7rem' }),
            }),
          ],
        }),
        state.stores
          ? jsxs('div', {
              className: 'flex items-center justify-between gap-4',
              children: [
                jsx(StoreMeter, {
                  glyph: 'note',
                  label: t('memory'),
                  info: state.stores.memory,
                }),
                jsx(StoreMeter, {
                  glyph: 'person',
                  label: t('user'),
                  info: state.stores.user,
                }),
              ],
            })
          : null,
        jsxs('div', {
          className:
            'overflow-hidden rounded-lg border border-(--stroke-nous) divide-y divide-(--ui-stroke-secondary)',
          children: [
            jsxs('label', {
              'data-mrc-row': '',
              className: 'flex items-center gap-2 px-2 py-1.5 text-xs',
              children: [
                jsx(Checkbox, {
                  checked: allOn,
                  disabled: !ids.length || busy,
                  onCheckedChange: v => toggleAll(Boolean(v)),
                }),
                jsx('span', { className: 'font-medium', children: t('all') }),
                jsx('span', {
                  className: 'ml-auto text-[0.65rem] text-(--ui-text-quaternary)',
                  children: ids.length ? t('count', selected.length, ids.length) : t('none'),
                }),
              ],
            }),
            items.length
              ? items.map(item => {
                  const parts = displayParts(item)
                  return jsxs(
                    'div',
                    {
                      'data-mrc-row': '',
                      className: 'flex items-center gap-2 px-2 py-1.5 text-xs',
                      children: [
                        jsx(Checkbox, {
                          checked: Boolean(picked[item.id]),
                          disabled: busy,
                          onCheckedChange: v =>
                            setPicked(prev => ({ ...prev, [item.id]: Boolean(v) })),
                        }),
                        jsxs('span', {
                          className: 'flex w-8 shrink-0 items-center gap-0.5 text-(--ui-text-tertiary)',
                          children: [
                            jsx(Tooltip, {
                              label: parts.target === 'user' ? t('userProfile') : t('memoryNotes'),
                              children: jsx(Codicon, {
                                name: parts.target === 'user' ? 'person' : 'note',
                                size: '0.75rem',
                              }),
                            }),
                            jsx(Tooltip, {
                              label:
                                parts.action === 'add'
                                  ? t('add')
                                  : parts.action === 'remove'
                                    ? t('remove')
                                    : t('replace'),
                              children: jsx(Codicon, {
                                name: actionGlyph(parts.action),
                                size: '0.75rem',
                              }),
                            }),
                          ],
                        }),
                        jsx('span', {
                          className: 'min-w-0 flex-1 truncate',
                          title: parts.text,
                          children: parts.text || item.id,
                        }),
                      ],
                    },
                    item.id
                  )
                })
              : jsx('div', {
                  className: 'px-2 py-3 text-xs text-(--ui-text-quaternary)',
                  children: state.ok === false ? t('readFail') : t('noPending'),
                }),
          ],
        }),
        jsxs('div', {
          className: 'flex flex-col gap-1.5 pt-1',
          children: [
            note || busy || fitFail
              ? jsxs('div', {
                  className: 'flex items-center gap-2',
                  children: [
                    jsx('span', {
                      className: 'min-w-0 flex-1 truncate text-[0.65rem] text-(--ui-text-quaternary)',
                      title: note || (fitFail && String(fails[fitFail.id]).split('\n')[0]) || '',
                      children: note || (busy ? t('working') : String(fails[fitFail.id]).split('\n')[0]),
                    }),
                    fitFail
                      ? jsx(Button, {
                          variant: 'outline',
                          className: 'h-6 shrink-0 px-2 text-[0.65rem]',
                          disabled: busy,
                          onClick: compact,
                          children: t('consolidate'),
                        })
                      : null,
                  ],
                })
              : null,
            jsxs('div', {
              className: 'flex w-full gap-1.5',
              children: [
                jsx(Button, {
                  variant: 'outline',
                  className: 'h-8 min-w-0 flex-1 basis-1/2',
                  disabled: busy || !selected.length,
                  onClick: () => run('reject'),
                  children: t('reject'),
                }),
                jsx(Button, {
                  className: 'h-8 min-w-0 flex-1 basis-1/2',
                  disabled: busy || !selected.length,
                  onClick: () => run('approve'),
                  children: t('approve'),
                }),
              ],
            }),
          ],
        }),
      ],
    }),
  })
}

function ReviewRoot() {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const onOpen = () => setOpen(true)
    window.addEventListener(OPEN_EVENT, onOpen)
    return () => window.removeEventListener(OPEN_EVENT, onOpen)
  }, [])
  return jsx(ReviewDialog, { open, onOpenChange: setOpen })
}

export default {
  id: ID,
  name: 'Memory-Review',
  description: 'Dialog to checkbox staged memory writes and approve or reject them.',
  defaultEnabled: true,
  register(ctx) {
    rest = ctx.rest
    openExternal = ctx.os && ctx.os.openExternal
    i18nT = ctx.i18n.t
    ctx.i18n.register(LOCALES)
    ctx.i18n.onLocaleChange(() => {
      document.querySelectorAll('[' + ITEM_ATTR + ']').forEach(row => applyRow(row, lastState))
    })
    void refreshState()
    ctx.onDispose(startMenu())

    const style = document.createElement('style')
    style.id = STYLE_ID
    style.textContent = `
      [data-mrc-row] [data-slot="checkbox"][data-state="checked"] {
        border-color: var(--ui-accent) !important;
        background: color-mix(in srgb, var(--ui-accent) 55%, transparent) !important;
      }
    `
    document.getElementById(STYLE_ID)?.remove()
    document.head.appendChild(style)
    ctx.onDispose(() => {
      document.getElementById(STYLE_ID)?.remove()
    })

    ctx.register({
      id: 'host',
      area: STATUSBAR_AREAS.right,
      order: 400,
      render: () =>
        jsx('span', {
          'aria-hidden': true,
          style: { display: 'contents' },
          children: jsx(ReviewRoot, {}),
        }),
    })
    ctx.register({
      id: 'palette',
      area: 'palette',
      data: {
        id: 'memory.review',
        label: tr('paletteLabel'),
        keywords: ['memory', 'pending', 'review', 'store', 'full', 'approve', 'memoria', 'pendientes', 'revisión', 'almacén', 'aprobar'],
        detail: () => {
          const { text, enabled } = labelFor(lastState)
          if (!lastState) return tr('paletteDetail')
          return enabled ? text : tr('paletteClean')
        },
        detailVariant: 'state',
        run: openReview,
      },
    })
  },
}
