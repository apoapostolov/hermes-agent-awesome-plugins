/**
 * Better Capabilities — one page in Settings ▸ Plugins.
 *
 * Three of the four things the plugin used to paint onto the Capabilities page
 * have no native equivalent, so they live here instead of in app markup:
 *
 *   Skills   — delete a skill folder (Recycle Bin), package it as a zip, reveal
 *              it in the file manager, and read its other markdown files.
 *   Presets  — save and restore on/off sets for skills, toolsets and agent
 *              plugins, in the same store `/preset` reads from chat.
 *   Overview — what this profile currently has on, and the one hop to the
 *              native page for everything it already owns.
 *
 * Everything goes through the plugin SDK: `host.skills` / `host.toolsets` (the
 * same endpoints the page uses), `host.request` for the `plugins.manage` RPC,
 * `ctx.rest` for this plugin's own routes, and `ctx.os` for the OS door. No app
 * DOM is queried, restyled, hidden or clicked, so the desktop-surface admission
 * check passes and no Desktop release can break the page.
 */
import {
  Button,
  Codicon,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Switch,
  Tip,
  cn,
  host
} from '@hermes/plugin-sdk'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'better-capabilities'
const KINDS = [
  { id: 'skills', label: 'Skills' },
  { id: 'tools', label: 'Tools' },
  { id: 'plugins', label: 'Plugins' }
]
const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,59}$/
const ICON_BTN = cn(
  'inline-flex size-6 shrink-0 items-center justify-center rounded-md border border-(--ui-stroke-tertiary)',
  'text-(--ui-text-secondary) transition-colors',
  'hover:text-foreground hover:bg-(--chrome-action-hover) disabled:opacity-40'
)
const ROW = 'flex items-center gap-2 rounded-md px-2 py-1.5'
const MUTED = 'text-xs text-(--ui-text-tertiary)'
const PILL =
  'inline-flex items-center rounded border border-(--ui-stroke-tertiary) px-1 text-[0.65rem] text-(--ui-text-tertiary)'

/** Only the plugin's OWN backend is assigned here, at register time. */
let rest = null
let osDoor = null

const el = (type, props, ...kids) => {
  const merged = { ...(props || {}) }
  if (kids.length === 1) merged.children = kids[0]
  else if (kids.length > 1) merged.children = kids
  return kids.length > 1 ? jsxs(type, merged) : jsx(type, merged)
}

const message = err => String((err && err.message) || err || 'Unknown error')

function toast(kind, title, body) {
  try {
    host.notify({ kind, message: body, title })
  } catch {
    // Toasts are optional on older shells; the page also shows inline errors.
  }
}

async function api(path, body) {
  if (typeof rest !== 'function') {
    throw new Error('This plugin’s backend is not ready. Reopen Settings if it persists.')
  }
  return body === undefined ? rest(path) : rest(path, { method: 'POST', body })
}

/** Subscribe to a readonly app atom (`host.state.*`). */
function useAtom(atom) {
  const read = useCallback(() => {
    try {
      return atom && typeof atom.get === 'function' ? atom.get() : undefined
    } catch {
      return undefined
    }
  }, [atom])
  const [value, setValue] = useState(read)

  useEffect(() => {
    if (!atom || typeof atom.subscribe !== 'function') {
      return undefined
    }
    setValue(atom.get())
    const off = atom.subscribe(next => setValue(next))
    return typeof off === 'function' ? off : undefined
  }, [atom])

  return value
}

function downloadZip(filename, b64) {
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 4000)
}

function IconButton({ disabled, icon, label, onClick, tone }) {
  return el(
    Tip,
    { label },
    el('button', {
      'aria-label': label,
      className: cn(ICON_BTN, tone === 'danger' && 'hover:text-(--ui-danger)'),
      disabled: Boolean(disabled),
      onClick,
      type: 'button'
    }, el(Codicon, { name: icon, size: '0.8rem' }))
  )
}

function Section({ children, title, hint }) {
  return el(
    'section',
    { className: 'flex flex-col gap-2 rounded-lg border border-(--ui-stroke-tertiary) p-3' },
    el(
      'header',
      { className: 'flex flex-wrap items-baseline gap-2' },
      el('h3', { className: 'text-sm font-medium text-foreground' }, title),
      hint ? el('span', { className: MUTED }, hint) : null
    ),
    children
  )
}

function Empty({ children }) {
  return el('p', { className: cn(MUTED, 'px-2 py-3') }, children)
}

function ConfirmDialog({ body, confirmLabel, onCancel, onConfirm, title }) {
  return el(
    Dialog,
    { onOpenChange: open => { if (!open) onCancel() }, open: true },
    el(
      DialogContent,
      { className: 'max-w-md' },
      el(DialogHeader, null, el(DialogTitle, null, title)),
      el(DialogDescription, null, body),
      el(
        DialogFooter,
        null,
        el(Button, { onClick: onCancel, size: 'sm', variant: 'ghost' }, 'Cancel'),
        el(Button, { onClick: onConfirm, size: 'sm', variant: 'destructive' }, confirmLabel || 'Delete')
      )
    )
  )
}

// ── capability snapshots through the SDK doors ────────────────────────────

async function listSkills() {
  const rows = await host.skills.list()
  return Array.isArray(rows) ? rows : []
}

async function listToolsets() {
  const rows = await host.toolsets.list()
  return Array.isArray(rows) ? rows : []
}

async function listAgentPlugins(profile) {
  const res = await host.request('plugins.manage', profile ? { action: 'list', profile } : { action: 'list' })
  const map = {}
  for (const row of (res && res.plugins) || []) {
    if (row && row.key) {
      map[row.key] = row.status === 'enabled'
    }
  }
  return map
}

async function profileNames() {
  try {
    const res = await host.profiles.list()
    const rows = Array.isArray(res) ? res : (res && Array.isArray(res.profiles) ? res.profiles : [])
    const names = []
    for (const row of rows) {
      const name = typeof row === 'string' ? row : row && (row.name || row.profile)
      if (name && !names.includes(String(name))) {
        names.push(String(name))
      }
    }
    return names
  } catch {
    return []
  }
}

async function snapshotKind(kind, profile) {
  if (kind === 'skills') {
    const rows = await listSkills()
    const enabled = {}
    for (const row of rows) {
      if (row && row.name) {
        enabled[row.name] = Boolean(row.enabled)
      }
    }
    return { enabled }
  }
  if (kind === 'tools') {
    const rows = await listToolsets()
    const enabled = {}
    for (const row of rows) {
      if (row && row.name) {
        enabled[row.name] = Boolean(row.enabled)
      }
    }
    return { enabled }
  }
  const current = await listAgentPlugins()
  const maps = { [profile || 'default']: current }
  for (const name of await profileNames()) {
    if (name === (profile || 'default') || Object.keys(maps).length > 12) {
      continue
    }
    try {
      maps[name] = await listAgentPlugins(name)
    } catch {
      // A profile the backend cannot answer for keeps its previous row.
    }
  }
  return { agent: current, agentByProfile: maps }
}

/** Flip one kind to the preset's state. Returns how many switches changed. */
async function applyKind(kind, payload) {
  if (kind === 'skills' || kind === 'tools') {
    const wanted = (payload && payload.enabled) || {}
    const rows = kind === 'skills' ? await listSkills() : await listToolsets()
    let changed = 0
    for (const row of rows) {
      const name = row && row.name
      if (!name || !(name in wanted)) {
        continue
      }
      const want = Boolean(wanted[name])
      if (Boolean(row.enabled) === want) {
        continue
      }
      try {
        if (kind === 'skills') {
          await host.skills.setEnabled(name, want)
        } else {
          await host.toolsets.setEnabled(name, want)
        }
        changed += 1
      } catch {
        // One refused key must not stop the rest of the preset.
      }
    }
    return changed
  }

  const maps =
    payload && payload.agentByProfile && typeof payload.agentByProfile === 'object'
      ? payload.agentByProfile
      : { default: (payload && payload.agent) || {} }
  let changed = 0
  for (const [profileName, mapping] of Object.entries(maps)) {
    if (!mapping || typeof mapping !== 'object') {
      continue
    }
    let current = {}
    try {
      current = await listAgentPlugins(profileName === 'default' ? undefined : profileName)
    } catch {
      continue
    }
    for (const [key, on] of Object.entries(mapping)) {
      const want = Boolean(on)
      if (current[key] === undefined || current[key] === want) {
        continue
      }
      try {
        await host.request('plugins.manage', {
          action: 'toggle',
          enable: want,
          key,
          ...(profileName === 'default' ? {} : { profile: profileName })
        })
        changed += 1
      } catch {
        // skip keys the backend rejects
      }
    }
  }
  return changed
}

// ── Skills ────────────────────────────────────────────────────────────────

function SkillRow({ busy, onDelete, onPackage, onReveal, onToggle, profile, row }) {
  const [open, setOpen] = useState(false)
  const [files, setFiles] = useState(null)
  const [activeRel, setActiveRel] = useState('SKILL.md')
  const [text, setText] = useState('')
  const [error, setError] = useState('')

  const loadFiles = useCallback(async () => {
    setError('')
    try {
      const res = await api('/files', { name: row.name })
      setFiles(Array.isArray(res && res.files) ? res.files : [])
    } catch (err) {
      setFiles([])
      setError(message(err))
    }
  }, [row.name])

  const loadFile = useCallback(
    async rel => {
      setError('')
      setActiveRel(rel)
      try {
        const res = await api('/file', { name: row.name, rel })
        setText(String((res && res.text) || ''))
      } catch (err) {
        setText('')
        setError(message(err))
      }
    },
    [row.name]
  )

  const toggleOpen = () => {
    const next = !open
    setOpen(next)
    if (next) {
      if (!files) {
        void loadFiles()
      }
      if (!text) {
        void loadFile('SKILL.md')
      }
    }
  }

  const provenance = row.provenance && row.provenance !== 'agent' ? row.provenance : ''

  return el(
    'div',
    { className: 'flex flex-col' },
    el(
      'div',
      { className: ROW },
      el(Switch, {
        'aria-label': 'Enable ' + row.name,
        checked: Boolean(row.enabled),
        disabled: busy === row.name,
        onCheckedChange: next => onToggle(row, next),
        size: 'xs'
      }),
      el('div', { className: 'flex min-w-0 flex-1 flex-col' },
        el('span', { className: 'truncate text-sm text-foreground' }, row.name),
        row.description ? el('span', { className: cn(MUTED, 'truncate') }, row.description) : null
      ),
      provenance ? el('span', { className: PILL }, provenance) : null,
      el(IconButton, { icon: open ? 'chevron-down' : 'chevron-right', label: 'Files', onClick: toggleOpen }),
      el(IconButton, {
        disabled: Boolean(busy),
        icon: 'file-zip',
        label: 'Package (zip)',
        onClick: () => onPackage(row)
      }),
      el(IconButton, { icon: 'folder-opened', label: 'Open folder', onClick: () => onReveal(row) }),
      el(IconButton, { icon: 'trash', label: 'Delete skill', onClick: () => onDelete(row), tone: 'danger' })
    ),
    open
      ? el(
          'div',
          { className: 'mb-2 ml-2 flex flex-col gap-2 rounded-md border border-(--ui-stroke-tertiary) p-2' },
          files === null
            ? el('span', { className: MUTED }, 'Reading files…')
            : files.length === 0
              ? el('span', { className: MUTED }, 'No markdown files beyond SKILL.md.')
              : el(
                  'div',
                  { className: 'flex flex-wrap gap-1' },
                  files.map(file =>
                    el(
                      'button',
                      {
                        className: cn(
                          'rounded border px-1.5 py-0.5 text-[0.7rem]',
                          file.rel === activeRel
                            ? 'border-(--ui-stroke-tertiary) bg-(--chrome-action-hover) text-foreground'
                            : 'border-transparent text-(--ui-text-tertiary) hover:text-foreground'
                        ),
                        key: file.rel,
                        onClick: () => void loadFile(file.rel),
                        type: 'button'
                      },
                      file.label
                    )
                  )
                ),
          error ? el('span', { className: cn(MUTED, 'text-(--ui-danger)') }, error) : null,
          el('pre', {
            className: 'max-h-72 overflow-auto whitespace-pre-wrap rounded bg-(--ui-bg-quinary) p-2 font-mono text-[0.7rem] text-(--ui-text-secondary)',
            children: text || (error ? '' : 'Loading…')
          })
        )
      : null
  )
}

function SkillsPage() {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [query, setQuery] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

  const load = useCallback(async () => {
    setError('')
    try {
      setRows(await listSkills())
    } catch (err) {
      setRows([])
      setError(message(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    const list = rows || []
    const needle = query.trim().toLowerCase()
    const visible = needle
      ? list.filter(row =>
          [row.name, row.category, row.description, row.provenance]
            .filter(Boolean)
            .some(value => String(value).toLowerCase().includes(needle))
        )
      : list
    return visible.slice().sort((a, b) => String(a.name).localeCompare(String(b.name)))
  }, [query, rows])

  const onToggle = async (row, next) => {
    setBusy(row.name)
    setRows(current => (current || []).map(item => (item.name === row.name ? { ...item, enabled: next } : item)))
    try {
      await host.skills.setEnabled(row.name, next)
    } catch (err) {
      setRows(current =>
        (current || []).map(item => (item.name === row.name ? { ...item, enabled: !next } : item))
      )
      toast('error', 'Could not switch ' + row.name, message(err))
    } finally {
      setBusy('')
    }
  }

  const onPackage = async row => {
    setBusy(row.name)
    try {
      const res = await api('/zip', { name: row.name })
      if (!res || !res.b64 || !res.filename) {
        throw new Error('The zip came back empty.')
      }
      downloadZip(res.filename, res.b64)
      toast('success', 'Packaged ' + row.name, res.filename + ' is downloading.')
    } catch (err) {
      toast('error', 'Could not package ' + row.name, message(err))
    } finally {
      setBusy('')
    }
  }

  const onReveal = async row => {
    try {
      const res = await api('/resolve', { name: row.name })
      const path = res && res.path
      if (!path) {
        throw new Error('No folder path came back.')
      }
      const shown = osDoor ? await osDoor.revealPath(path) : false
      if (!shown) {
        toast('info', row.name, path)
      }
    } catch (err) {
      toast('error', 'Could not open the folder', message(err))
    }
  }

  const onDelete = async row => {
    setBusy(row.name)
    try {
      const res = await api('/delete', { name: row.name })
      const moved = res && res.result === 'moved'
      toast(
        'success',
        'Deleted ' + row.name,
        moved
          ? 'The Recycle Bin was unavailable, so the folder was moved to better-capabilities-trash.'
          : 'The folder is in the Recycle Bin.'
      )
      await load()
    } catch (err) {
      toast('error', 'Could not delete ' + row.name, message(err))
    } finally {
      setBusy('')
      setPendingDelete(null)
    }
  }

  return el(
    'div',
    { className: 'flex flex-col gap-3 p-4' },
    el(
      'div',
      { className: 'flex flex-wrap items-center gap-2' },
      el(Input, {
        'aria-label': 'Filter skills',
        className: 'h-7 max-w-xs text-xs',
        onChange: event => setQuery(event.target.value),
        placeholder: 'Filter skills',
        value: query
      }),
      el(Button, { onClick: () => void load(), size: 'sm', variant: 'ghost' }, 'Refresh'),
      el('span', { className: MUTED }, (rows ? filtered.length : 0) + ' shown')
    ),
    el(
      'p',
      { className: MUTED },
      'Delete, package and folder actions only reach skills under this Hermes home’s skills folder. Bundled and hub skills resolve outside it and are left alone.'
    ),
    error ? el('p', { className: cn(MUTED, 'text-(--ui-danger)') }, error) : null,
    el(
      Section,
      { hint: 'read from the same list the Capabilities page shows' },
      rows === null
        ? el('span', { className: MUTED }, 'Loading skills…')
        : filtered.length === 0
          ? el(Empty, null, 'No skills match.')
          : filtered.map(row =>
              el(SkillRow, {
                busy,
                key: row.name,
                onDelete: setPendingDelete,
                onPackage: row2 => void onPackage(row2),
                onReveal: row2 => void onReveal(row2),
                onToggle: (row2, next) => void onToggle(row2, next),
                row
              })
            )
    ),
    pendingDelete
      ? el(ConfirmDialog, {
          body:
            '“' +
            pendingDelete.name +
            '” goes to the Recycle Bin, or to better-capabilities-trash when the bin is unavailable. Nothing else is touched.',
          onCancel: () => setPendingDelete(null),
          onConfirm: () => void onDelete(pendingDelete),
          title: 'Delete ' + pendingDelete.name + '?'
        })
      : null
  )
}

// ── Presets ───────────────────────────────────────────────────────────────

function PresetRow({ busy, entry, kind, onApply, onDelete, onMove, onOverwrite, onRename }) {
  return el(
    'div',
    { className: ROW },
    el('div', { className: 'flex min-w-0 flex-1 flex-col' },
      el('span', { className: 'truncate text-sm text-foreground' }, entry.name),
      el('span', { className: cn(MUTED, 'truncate') }, entry.summary)
    ),
    el(IconButton, { disabled: Boolean(busy), icon: 'chevron-up', label: 'Move up', onClick: () => onMove(entry.name, -1) }),
    el(IconButton, { disabled: Boolean(busy), icon: 'chevron-down', label: 'Move down', onClick: () => onMove(entry.name, 1) }),
    el(IconButton, { disabled: Boolean(busy), icon: 'play', label: 'Apply', onClick: () => onApply(kind, entry.name) }),
    el(IconButton, { disabled: Boolean(busy), icon: 'replace', label: 'Overwrite', onClick: () => onOverwrite(kind, entry.name) }),
    el(IconButton, { disabled: Boolean(busy), icon: 'edit', label: 'Rename', onClick: () => onRename(kind, entry.name) }),
    el(IconButton, { disabled: Boolean(busy), icon: 'trash', label: 'Delete preset', onClick: () => onDelete(kind, entry.name), tone: 'danger' })
  )
}

function PresetsPage() {
  const profile = useAtom(host.state.profile)
  const [kind, setKind] = useState('skills')
  const [store, setStore] = useState(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [pendingDelete, setPendingDelete] = useState(null)

  const load = useCallback(async () => {
    setError('')
    try {
      const res = await api('/presets', undefined)
      setStore((res && res.store) || { skills: {}, tools: {}, plugins: {} })
    } catch (err) {
      setStore({ skills: {}, tools: {}, plugins: {} })
      setError(message(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const persist = useCallback(async next => {
    setStore(next)
    try {
      await rest('/presets', { method: 'PUT', body: next })
    } catch (err) {
      toast('error', 'Could not save the preset store', message(err))
    }
  }, [])

  const bucket = (store && store[kind]) || {}
  const order = useMemo(() => {
    const names = (Array.isArray(bucket._order) ? bucket._order : []).filter(item => item && bucket[item])
    for (const item of Object.keys(bucket)) {
      if (item !== '_order' && !names.includes(item)) {
        names.push(item)
      }
    }
    return names
  }, [bucket])

  const entries = useMemo(
    () =>
      order.map(item => {
        const payload = bucket[item] || {}
        let summary = ''
        if (kind === 'plugins') {
          const maps = payload.agentByProfile || {}
          const keys = Object.keys(maps)
          const on = Object.values(maps).reduce(
            (total, map) => total + Object.values(map || {}).filter(Boolean).length,
            0
          )
          summary = keys.length + ' profile' + (keys.length === 1 ? '' : 's') + ' · ' + on + ' plugin switches on'
        } else {
          const enabled = payload.enabled || {}
          const keys = Object.keys(enabled)
          const on = keys.filter(key => enabled[key]).length
          summary = on + ' of ' + keys.length + ' on'
        }
        return { name: item, payload, summary }
      }),
    [bucket, kind, order]
  )

  const saveOne = async (label, overwrite) => {
    const trimmed = String(label || '').trim()
    if (!NAME_RE.test(trimmed)) {
      toast('error', 'Name is not valid', 'Letters, numbers, spaces, dots, underscores, apostrophes or hyphens. Start with a letter or number.')
      return
    }
    if (bucket[trimmed] && !overwrite) {
      toast('error', trimmed + ' already exists', 'Use Overwrite on that row, or pick another name.')
      return
    }
    setBusy(trimmed)
    setError('')
    try {
      const payload = await snapshotKind(kind, profile)
      payload.savedAt = Date.now()
      const nextBucket = { ...bucket, [trimmed]: payload }
      const nextOrder = order.filter(item => item !== trimmed)
      nextOrder.push(trimmed)
      nextBucket._order = nextOrder
      await persist({ ...store, [kind]: nextBucket })
      setName(trimmed)
      toast('success', (overwrite ? 'Overwrote ' : 'Saved ') + trimmed, 'The ' + kind + ' on/off state is stored.')
    } catch (err) {
      setError(message(err))
      toast('error', 'Could not save the preset', message(err))
    } finally {
      setBusy('')
    }
  }

  const applyOne = async (targetKind, presetName) => {
    const payload = ((store && store[targetKind]) || {})[presetName]
    if (!payload) {
      toast('error', 'Missing preset', presetName)
      return
    }
    setBusy(presetName)
    try {
      const changed = await applyKind(targetKind, payload)
      toast('success', 'Applied ' + presetName, changed + ' switch' + (changed === 1 ? '' : 'es') + ' changed.')
      if (targetKind === 'plugins') {
        try {
          await rest('/presets/pending', { method: 'DELETE' })
        } catch {
          // pending marker is best-effort
        }
      }
    } catch (err) {
      toast('error', 'Could not apply ' + presetName, message(err))
    } finally {
      setBusy('')
    }
  }

  const renameOne = async (targetKind, from, nameInput) => {
    const to = String(name || '').trim()
    if (!to || to === from) {
      toast('error', 'Type the new name first', 'Put the new name in the field above, then click Rename.')
      return
    }
    if (!NAME_RE.test(to)) {
      toast('error', 'Name is not valid', 'Letters, numbers, spaces, dots, underscores, apostrophes or hyphens.')
      return
    }
    const targetBucket = (store && store[targetKind]) || {}
    if (targetBucket[to] && to !== from) {
      toast('error', to + ' already exists', 'Pick another name.')
      return
    }
    const nextBucket = { ...targetBucket }
    nextBucket[to] = targetBucket[from]
    delete nextBucket[from]
    nextBucket._order = order.map(item => (item === from ? to : item))
    await persist({ ...store, [targetKind]: nextBucket })
    setName(to)
  }

  const moveOne = async (targetKind, presetName, delta) => {
    const targetBucket = (store && store[targetKind]) || {}
    const list = (Array.isArray(targetBucket._order) ? targetBucket._order : Object.keys(targetBucket)).filter(
      item => item !== '_order'
    )
    const index = list.indexOf(presetName)
    const next = index + delta
    if (index < 0 || next < 0 || next >= list.length) {
      return
    }
    list.splice(index, 1)
    list.splice(next, 0, presetName)
    await persist({ ...store, [targetKind]: { ...targetBucket, _order: list } })
  }

  const removeOne = async (targetKind, presetName) => {
    const targetBucket = { ...((store && store[targetKind]) || {}) }
    delete targetBucket[presetName]
    targetBucket._order = (Array.isArray(targetBucket._order) ? targetBucket._order : []).filter(
      item => item !== presetName
    )
    await persist({ ...store, [targetKind]: targetBucket })
    setPendingDelete(null)
    toast('success', 'Deleted ' + presetName, 'The ' + targetKind + ' preset is gone.')
  }

  return el(
    'div',
    { className: 'flex flex-col gap-3 p-4' },
    el(
      'div',
      { className: 'flex flex-wrap items-center gap-1' },
      KINDS.map(item =>
        el(
          'button',
          {
            className: cn(
              'rounded-md px-2 py-1 text-xs',
              item.id === kind
                ? 'bg-(--chrome-action-hover) text-foreground'
                : 'text-(--ui-text-tertiary) hover:text-foreground'
            ),
            key: item.id,
            onClick: () => setKind(item.id),
            type: 'button'
          },
          item.label
        )
      ),
      el('span', { className: cn(MUTED, 'ml-2') }, 'profile: ' + (profile || 'default'))
    ),
    el(
      'div',
      { className: 'flex flex-wrap items-center gap-2' },
      el(Input, {
        'aria-label': 'Preset name',
        className: 'h-7 max-w-xs text-xs',
        maxLength: 60,
        onChange: event => setName(event.target.value),
        placeholder: 'Name for a new preset, or the new name when renaming',
        value: name
      }),
      el(Button, { disabled: Boolean(busy), onClick: () => void saveOne(name, false), size: 'sm' }, 'Save current'),
      el('span', { className: MUTED }, entries.length + ' preset' + (entries.length === 1 ? '' : 's'))
    ),
    kind === 'plugins'
      ? el(
          'p',
          { className: MUTED },
          'Agent-plugin switches are restored per profile. Desktop-plugin switches are app-wide and read-only for plugins, so a preset never claims them.'
        )
      : null,
    error ? el('p', { className: cn(MUTED, 'text-(--ui-danger)') }, error) : null,
    el(
      Section,
      { hint: 'the same store /preset reads from chat' },
      store === null
        ? el('span', { className: MUTED }, 'Loading presets…')
        : entries.length === 0
          ? el(Empty, null, 'No ' + kind + ' presets yet. Turn things on or off, then save the set here.')
          : entries.map(entry =>
              el(PresetRow, {
                busy,
                entry: { ...entry, name: entry.name },
                key: entry.name,
                kind,
                nameInput: name,
                onApply: (targetKind, presetName) => void applyOne(targetKind, presetName),
                onDelete: (targetKind, presetName) => setPendingDelete({ kind: targetKind, name: presetName }),
                onMove: (presetName, delta) => void moveOne(kind, presetName, delta),
                onOverwrite: (targetKind, presetName) => void saveOne(presetName, true),
                onRename: (targetKind, presetName) => void renameOne(targetKind, presetName, name)
              })
            )
    ),
    el(
      'p',
      { className: MUTED },
      'From chat: /preset save skills|tools|plugins <name>, then /preset skills|tools|plugins <name>.'
    ),
    pendingDelete
      ? el(ConfirmDialog, {
          body: 'Delete the preset “' + pendingDelete.name + '”? Capability switches already applied stay as they are.',
          onCancel: () => setPendingDelete(null),
          onConfirm: () => void removeOne(pendingDelete.kind, pendingDelete.name),
          title: 'Delete ' + pendingDelete.name + '?'
        })
      : null
  )
}

// ── Overview ──────────────────────────────────────────────────────────────

function OverviewPage() {
  const profile = useAtom(host.state.profile)
  const [counts, setCounts] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setError('')
    try {
      const [skills, toolsets, plugins] = await Promise.all([
        listSkills(),
        listToolsets(),
        listAgentPlugins()
      ])
      const on = rows => rows.filter(row => row && row.enabled).length
      setCounts({
        plugins: [Object.values(plugins).filter(Boolean).length, Object.keys(plugins).length],
        skills: [skills.filter(row => row && row.enabled).length, skills.length],
        toolsets: [on(toolsets), toolsets.length]
      })
    } catch (err) {
      setCounts(null)
      setError(message(err))
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const line = (label, pair) =>
    el(
      'div',
      { className: 'flex items-baseline gap-2' },
      el('span', { className: 'w-24 text-xs text-(--ui-text-tertiary)' }, label),
      el('span', { className: 'text-sm text-foreground' }, pair ? pair[0] + ' on · ' + pair[1] + ' installed' : '…')
    )

  return el(
    'div',
    { className: 'flex flex-col gap-3 p-4' },
    el(
      'p',
      { className: 'text-sm text-(--ui-text-secondary)' },
      'Skill delete, packaging and file browsing, plus saved on/off presets — the parts the Capabilities page does not cover. Everything else stays on the native page.'
    ),
    el(
      Section,
      { hint: 'profile: ' + (profile || 'default') },
      error ? el('p', { className: cn(MUTED, 'text-(--ui-danger)') }, error) : null,
      line('Skills', counts && counts.skills),
      line('Toolsets', counts && counts.toolsets),
      line('Plugins', counts && counts.plugins),
      el(
        'div',
        { className: 'flex flex-wrap gap-2 pt-1' },
        el(Button, { onClick: () => void load(), size: 'sm', variant: 'ghost' }, 'Refresh'),
        el(
          Button,
          {
            onClick: () => {
              try {
                host.navigate('/capabilities?tab=plugins')
              } catch {
                toast('error', 'Could not open Capabilities', 'Use the sidebar entry instead.')
              }
            },
            size: 'sm',
            variant: 'ghost'
          },
          'Open Capabilities'
        )
      )
    ),
    el(
      Section,
      { hint: 'what each sub-page does' },
      el('p', { className: MUTED }, 'Skills — filter the list, flip a skill on or off, read its other markdown files, package it as a zip, reveal it, or delete the folder.'),
      el('p', { className: MUTED }, 'Presets — save the current skills / toolsets / agent-plugin switches under a name, then reapply, overwrite, rename, reorder or delete it.')
    )
  )
}

// ── plugin ────────────────────────────────────────────────────────────────

export default {
  id: ID,
  name: 'Better Capabilities',
  description: 'Skill delete, packaging and file browsing, plus saved on/off presets for skills, toolsets and plugins.',
  defaultEnabled: false,
  register(ctx) {
    rest = typeof ctx.rest === 'function' ? ctx.rest : null
    osDoor = ctx.os || null
    ctx.registerSettingsPage({
      id: 'better-capabilities',
      title: 'Better Capabilities',
      icon: 'sparkle',
      order: 40,
      render: () => el(OverviewPage, null),
      children: [
        { id: 'skills', title: 'Skills', render: () => el(SkillsPage, null) },
        { id: 'presets', title: 'Presets', render: () => el(PresetsPage, null) }
      ]
    })
  }
}
