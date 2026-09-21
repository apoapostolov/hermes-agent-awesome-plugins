import {
  Codicon,
  COMPOSER_AREAS,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Button,
  Textarea,
  host,
  useValue,
} from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useRef, useState } from 'react'

const ID = 'prompt-enhancer'
const STYLE_ID = 'prompt-enhancer-style'
const ENHANCERS = 'enhancers'
const GHOST = 'inline-flex size-(--composer-control-size) shrink-0 items-center justify-center rounded-md border-0 bg-transparent text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
const LIBRARY = {
  display: 'flex',
  flexDirection: 'column',
  width: 'min(46rem, 92vw)',
  height: 'min(30rem, calc(85vh - 6.5rem))',
  minHeight: '22rem',
}
const PANES = {
  display: 'grid',
  gridTemplateColumns: '12.5rem minmax(0, 1fr)',
  flex: '1 1 auto',
  minHeight: 0,
}
const RAIL = {
  display: 'flex',
  flexDirection: 'column',
  gap: '2px',
  minWidth: 0,
  minHeight: 0,
  overflow: 'auto',
  borderRight: '1px solid var(--ui-stroke-secondary)',
  padding: '8px',
}
const MAIN = {
  minWidth: 0,
  minHeight: 0,
  overflow: 'auto',
  padding: '10px 12px 12px',
}
const CARD = {
  border: '1px solid var(--ui-stroke-secondary)',
  borderRadius: '2px',
  padding: '8px 10px',
  marginBottom: '8px',
}
const MENU_ROW = 'gap-2 rounded-none px-2.5 py-1 text-xs'
const ICON = 'inline-flex size-6 shrink-0 items-center justify-center rounded-md border-0 bg-transparent text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'

const DEFAULTS = [
  ['Clarify', 'Make the ask unambiguous. Keep the intent. Do not add requirements.'],
  ['Tighten', 'Cut fluff. Keep the ask and the constraints already in the draft.'],
  ['Grammar', 'Fix grammar and style. Leave the meaning alone.'],
  ['Expand', 'Turn the draft into an ordered plan. Keep it concrete.'],
  ['Summarize', 'Summarize the draft. Keep the decisions.'],
]

let storage = null
let lib = null
const listeners = new Set()
const SOURCE_URL = 'https://github.com/apoapostolov/hermes-agent-awesome-plugins'
let openLibrary = null
let openExternal = null
let closeLibrary = null
let priorDraft = null
const priorListeners = new Set()
let enhancing = false
const enhanceListeners = new Set()

function uid() {
  return Math.random().toString(36).slice(2, 10)
}

function seed() {
  return {
    folders: [{ id: ENHANCERS, name: 'Enhancers', locked: true }],
    prompts: DEFAULTS.map(([name, body]) => ({ id: uid(), folderId: ENHANCERS, name, body })),
    enhanceWith: { kind: 'session' },
  }
}

function emit() {
  listeners.forEach(fn => fn(lib))
}

function load() {
  const saved = storage ? storage.get('library', null) : null
  lib = saved && saved.folders && saved.prompts ? saved : seed()
  if (!lib.folders.some(folder => folder.id === ENHANCERS)) {
    lib = { ...lib, folders: [{ id: ENHANCERS, name: 'Enhancers', locked: true }, ...lib.folders] }
  }
  return lib
}

function save(next) {
  lib = next
  if (storage) storage.set('library', next)
  emit()
}

function useLib() {
  const [value, setValue] = useState(() => lib || seed())
  useEffect(() => {
    const fn = next => setValue(next)
    listeners.add(fn)
    return () => listeners.delete(fn)
  }, [])
  return value
}

function focusedEditor() {
  const nodes = document.querySelectorAll('[data-slot="composer-rich-input"]')
  for (const node of nodes) {
    if (node.closest('[data-pane-hidden="true"]')) continue
    if (node.getClientRects().length === 0) continue
    return node
  }
  return nodes[0] || null
}

function readEditor(editor) {
  if (!editor) return ''
  return (editor.innerText || '').replace(/\u00a0/g, ' ').trim()
}

function setEditorText(editor, text) {
  if (!editor) return
  editor.focus()
  const sel = window.getSelection()
  const range = document.createRange()
  range.selectNodeContents(editor)
  sel.removeAllRanges()
  sel.addRange(range)
  const ok = document.execCommand('insertText', false, text)
  if (!ok) editor.textContent = text
  editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
}

function insertAtCaret(editor, text) {
  if (!editor) return
  editor.focus()
  const ok = document.execCommand('insertText', false, text)
  if (!ok) editor.append(document.createTextNode(text))
  editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: text }))
}

function clearEditor(editor) {
  if (!editor) return
  editor.textContent = ''
  editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'deleteContent' }))
}

function payloadFor(prompt, draft, enhancer) {
  const body = (prompt.body || '').trim()
  if (!enhancer || !draft) return body
  return `${body}\n\nContext:\n${draft}`
}

async function ensureSession() {
  const current = host.state.focusedSessionId.get()
  if (current) return current
  const created = await host.request('session.create', {})
  const runtime = created.session_id || (created.result && created.result.session_id)
  const stored = created.stored_session_id || (created.result && created.result.stored_session_id)
  if (stored && typeof host.openSession === 'function') await host.openSession(stored)
  if (!runtime) throw new Error('No session to send into')
  return runtime
}

async function applyOnce(sessionId) {
  const pick = lib && lib.enhanceWith
  if (!pick || pick.kind !== 'model') return
  const command = `/model ${pick.model} --provider ${pick.provider} --once`
  try {
    const result = await host.request('slash.exec', { session_id: sessionId, command })
    if (result && result.error) throw new Error(result.error.message || 'model override failed')
  } catch (err) {
    host.notify({ kind: 'error', message: 'Model override failed. Sent on the session model.' })
  }
}

async function submitText(text, { clear } = {}) {
  const editor = focusedEditor()
  const sessionId = await ensureSession()
  await applyOnce(sessionId)
  const busy = host.state.busy.get()
  await host.request('prompt.submit', {
    session_id: sessionId,
    text,
    ...(busy ? { queued: true } : {}),
  })
  if (clear) clearEditor(editor)
}

async function usePrompt(prompt, mode, { dismiss } = {}) {
  const enhancer = prompt.folderId === ENHANCERS
  const editor = focusedEditor()
  const draft = readEditor(editor)
  const text = payloadFor(prompt, draft, enhancer)
  if (!text) {
    host.notify({ kind: 'error', message: 'That prompt is empty.' })
    return
  }
  if (mode === 'add') {
    if (!editor) {
      host.notify({ kind: 'error', message: 'No composer is focused.' })
      return
    }
    if (enhancer) {
      setPrior(draft)
      setEditorText(editor, text)
    } else insertAtCaret(editor, text)
    if (dismiss && closeLibrary) closeLibrary()
    return
  }
  if (mode === 'send' && enhancer) {
    await enhanceDraft(prompt, { dismiss })
    return
  }
  try {
    await submitText(text, { clear: false })
    if (dismiss && closeLibrary) closeLibrary()
  } catch (err) {
    host.notify({ kind: 'error', message: err && err.message ? err.message : 'Send failed.' })
  }
}

function EnhanceMenu() {
  const data = useLib()
  const busy = useEnhancing()
  const names = data.prompts.filter(prompt => prompt.folderId === ENHANCERS)
  if (busy) {
    return jsx('button', {
      type: 'button',
      className: GHOST,
      disabled: true,
      'aria-label': 'Enhancing',
      title: 'Enhancing',
      children: jsx(Codicon, { name: 'loading', size: '0.95rem', spinning: true }),
    })
  }
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, {
        'aria-label': 'Enhance',
        className: GHOST,
        title: 'Enhance',
        children: jsx(Codicon, { name: 'sparkle', size: '0.95rem' }),
      }),
      jsx(DropdownMenuContent, {
        align: 'end',
        className: 'w-52 rounded-none p-0 text-xs shadow-md',
        side: 'top',
        sideOffset: 8,
        children: [
          ...names.map(prompt => jsx(DropdownMenuItem, {
            className: MENU_ROW,
            onSelect: () => usePrompt(prompt, 'send'),
            children: prompt.name,
          }, prompt.id)),
          jsx(DropdownMenuSeparator, { className: 'mx-0' }),
          jsx(DropdownMenuItem, {
            className: 'rounded-none px-2.5 py-1 text-[0.625rem] text-(--ui-text-tertiary)',
            onSelect: () => { if (openLibrary) openLibrary(ENHANCERS) },
            children: 'More...',
          }),
        ],
      }),
    ],
  })
}

function setEnhancing(on) {
  enhancing = on
  enhanceListeners.forEach(fn => fn(on))
}

function useEnhancing() {
  const [value, setValue] = useState(enhancing)
  useEffect(() => {
    enhanceListeners.add(setValue)
    return () => enhanceListeners.delete(setValue)
  }, [])
  return value
}

async function enhanceDraft(prompt, { dismiss } = {}) {
  if (enhancing) return
  const editor = focusedEditor()
  const draft = readEditor(editor)
  if (!editor) {
    host.notify({ kind: 'error', message: 'No composer is focused.' })
    return
  }
  if (!draft) {
    host.notify({ kind: 'error', message: 'The composer is empty.' })
    return
  }
  const instructions = `${(prompt.body || '').trim()}\n\nReturn only the rewritten prompt. No preamble and no code fence.`
  setEnhancing(true)
  if (dismiss && closeLibrary) closeLibrary()
  try {
    const result = await host.request('llm.oneshot', {
      instructions,
      input: draft,
      task: 'title_generation',
      max_tokens: 4096,
      temperature: 0.2,
    }, 70000)
    const text = String((result && result.text) || '').trim()
    if (!text) throw new Error('Enhancement returned nothing.')
    setPrior(draft)
    setEditorText(focusedEditor() || editor, text)
  } catch (err) {
    host.notify({ kind: 'error', message: err && err.message ? err.message : 'Enhancement failed.' })
  } finally {
    setEnhancing(false)
  }
}

function setPrior(text) {
  priorDraft = text
  priorListeners.forEach(fn => fn(text))
}

function usePrior() {
  const [value, setValue] = useState(priorDraft)
  useEffect(() => {
    priorListeners.add(setValue)
    return () => priorListeners.delete(setValue)
  }, [])
  return value
}

function undoEnhancement() {
  if (priorDraft == null) return
  const editor = focusedEditor()
  if (!editor) {
    host.notify({ kind: 'error', message: 'No composer is focused.' })
    return
  }
  setEditorText(editor, priorDraft)
  setPrior(null)
}

function modelName(pick) {
  if (!pick || pick.kind !== 'model') return 'Session'
  return pick.model
}

function EnhancePickLabel({ pick }) {
  return jsxs('span', {
    className: 'inline-flex max-w-44 items-center gap-1.5',
    children: [
      jsx('span', { className: 'shrink-0 text-(--ui-text-tertiary)', children: 'Enhance Model' }),
      jsx('i', { 'aria-hidden': 'true', className: 'size-1 shrink-0 rounded-full bg-(--ui-accent)' }),
      jsx('span', { className: 'truncate text-(--ui-accent)', children: modelName(pick) }),
    ],
  })
}

function promptsIn(data, folderId) {
  return data.prompts.filter(prompt => prompt.folderId === folderId)
}

function IconBtn({ name, label, onClick, active }) {
  return jsx('button', {
    type: 'button',
    title: label,
    'aria-label': label,
    'aria-pressed': active ? 'true' : undefined,
    className: active ? `${ICON} text-(--ui-accent)` : ICON,
    onClick,
    children: jsx(Codicon, { name, size: '0.85rem' }),
  })
}

function Clamp({ text }) {
  const ref = useRef(null)
  const [cut, setCut] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    setCut(el.scrollHeight > el.clientHeight + 1)
  }, [text])
  return jsxs('div', {
    className: 'relative',
    children: [
      jsx('p', {
        ref,
        'data-pe-clamp': '',
        className: 'm-0 text-xs leading-snug text-(--ui-text-tertiary)',
        children: text || 'Empty prompt',
      }),
      cut ? jsx('span', {
        className: 'pointer-events-none absolute bottom-0 right-0 bg-[color-mix(in_srgb,var(--ui-bg-elevated)_92%,transparent)] pl-1 text-(--ui-accent)',
        children: jsx(Codicon, { name: 'ellipsis', size: '0.85rem' }),
      }) : null,
    ],
  })
}

function LibraryDialog({ open, folderId, onFolder, onClose, onEdit }) {
  const data = useLib()
  const [editMode, setEditMode] = useState(false)
  const [adding, setAdding] = useState(false)
  const [confirmId, setConfirmId] = useState(null)
  const [renaming, setRenaming] = useState(null)
  const [renamingFolder, setRenamingFolder] = useState(null)
  const [models, setModels] = useState(null)
  const [drop, setDrop] = useState(null)
  const dragId = useRef(null)
  const folder = data.folders.find(item => item.id === folderId) || data.folders[0]
  const cards = promptsIn(data, folder.id)

  useEffect(() => {
    if (!open || models) return undefined
    let dead = false
    host.request('model.options', { explicit_only: true }).then(result => {
      if (!dead) setModels((result && result.providers) || [])
    }).catch(err => {
      if (dead) return
      setModels([])
      host.notify({ kind: 'error', message: err && err.message ? err.message : 'Model list failed.' })
    })
    return () => { dead = true }
  }, [open, models])

  function updatePrompts(prompts) {
    save({ ...data, prompts })
  }

  function moveTo(id, nextFolder) {
    updatePrompts(data.prompts.map(prompt => prompt.id === id ? { ...prompt, folderId: nextFolder } : prompt))
  }

  function reorderTo(id, gap) {
    const mine = data.prompts.filter(prompt => prompt.folderId === folder.id)
    const from = mine.findIndex(prompt => prompt.id === id)
    if (from < 0 || gap == null) return
    const to = gap > from ? gap - 1 : gap
    if (to === from) return
    const next = mine.slice()
    const [moving] = next.splice(from, 1)
    next.splice(Math.max(0, Math.min(to, next.length)), 0, moving)
    save({ ...data, prompts: [...data.prompts.filter(prompt => prompt.folderId !== folder.id), ...next] })
  }

  return jsx(Dialog, {
    open,
    onOpenChange: next => { if (!next) onClose() },
    children: jsx(DialogContent, {
      fitContent: true,
      className: 'min-w-[560px] max-w-[46rem]',
      bodyClassName: 'flex min-h-0 flex-col gap-0 overflow-hidden p-0',
      children: jsxs('div', {
        className: 'min-h-0',
        'data-pe-library': '',
        style: LIBRARY,
        children: [
          jsxs(DialogHeader, {
            className: 'flex shrink-0 flex-row items-center justify-between gap-3 border-b border-(--ui-stroke-secondary) px-3 py-2.5',
            style: { paddingRight: '3.25rem' },
            children: [
              jsxs('span', {
                className: 'inline-flex min-w-0 items-center gap-1.5',
                children: [
                  jsx(DialogTitle, { children: 'Prompt Library' }),
                  jsx('a', {
                    href: SOURCE_URL,
                    title: 'Source on GitHub',
                    'aria-label': 'Source on GitHub',
                    className: 'inline-flex items-center text-(--ui-text-quaternary) hover:text-(--ui-text-tertiary)',
                    onClick: event => {
                      event.preventDefault()
                      if (openExternal) openExternal(SOURCE_URL)
                    },
                    children: jsx(Codicon, { name: 'github', size: '0.7rem' }),
                  }),
                ],
              }),
              jsxs(DropdownMenu, {
                children: [
                  jsx(DropdownMenuTrigger, {
                    className: 'max-w-48 shrink border-0 bg-transparent p-0 text-xs',
                    style: { maxWidth: '14rem' },
                    children: jsx(EnhancePickLabel, { pick: data.enhanceWith }),
                  }),
                  jsx(DropdownMenuContent, {
                    align: 'end',
                    className: 'max-h-64 w-56 overflow-auto rounded-none p-0 text-xs',
                    side: 'bottom',
                    sideOffset: 6,
                    children: [
                      jsx(DropdownMenuItem, {
                        className: MENU_ROW,
                        onSelect: () => save({ ...data, enhanceWith: { kind: 'session' } }),
                        children: 'Session model',
                      }),
                      ...(models || []).flatMap(provider => {
                        const rows = [
                          jsx('div', {
                            className: 'px-2.5 pt-1.5 text-[0.625rem] text-(--ui-text-tertiary)',
                            children: provider.name || provider.slug,
                          }, `${provider.slug}-label`),
                        ]
                        for (const model of provider.models || []) {
                          const slug = typeof model === 'string' ? model : (model.id || model.name)
                          if (!slug) continue
                          rows.push(jsx(DropdownMenuItem, {
                            className: MENU_ROW,
                            onSelect: () => save({ ...data, enhanceWith: { kind: 'model', provider: provider.slug, model: slug } }),
                            children: slug,
                          }, `${provider.slug}:${slug}`))
                        }
                        return rows
                      }),
                    ],
                  }),
                ],
              }),
            ],
          }),
          jsxs('div', {
            style: PANES,
            children: [
              jsxs('div', {
                style: RAIL,
                children: [
                  jsxs('div', {
                    className: 'flex items-center justify-between px-2 pb-1',
                    children: [
                      jsx('span', { className: 'text-sm font-semibold', children: 'Folders' }),
                      jsx(IconBtn, {
                        name: 'pencil',
                        label: editMode ? 'Done' : 'Edit folders',
                        active: editMode,
                        onClick: () => {
                          setEditMode(on => !on)
                          setAdding(false)
                          setRenamingFolder(null)
                          setConfirmId(null)
                        },
                      }),
                    ],
                  }),
                  data.folders.map(item => jsxs('div', {
                    key: item.id,
                    style: {
                      display: 'flex',
                      flexWrap: 'wrap',
                      alignItems: 'center',
                      borderRadius: '2px',
                      background: item.id === folder.id ? 'var(--ui-control-active-background)' : 'transparent',
                    },
                    onDragOver: event => { event.preventDefault(); event.currentTarget.dataset.peOver = '1' },
                    onDragLeave: event => { delete event.currentTarget.dataset.peOver },
                    onDrop: event => {
                      event.preventDefault()
                      delete event.currentTarget.dataset.peOver
                      const id = dragId.current
                      if (id) moveTo(id, item.id)
                    },
                    children: [
                      renamingFolder === item.id ? jsx('input', {
                        autoFocus: true,
                        className: 'h-7 min-w-0 flex-1 border-0 bg-transparent px-2 text-xs',
                        defaultValue: item.name,
                        onBlur: event => {
                          const name = event.target.value.trim() || item.name
                          save({ ...data, folders: data.folders.map(row => row.id === item.id ? { ...row, name } : row) })
                          setRenamingFolder(null)
                        },
                        onKeyDown: event => {
                          if (event.key === 'Enter') event.currentTarget.blur()
                          if (event.key === 'Escape') setRenamingFolder(null)
                        },
                      }) : jsx('button', {
                        type: 'button',
                        className: 'flex h-7 min-w-0 flex-1 items-center border-0 bg-transparent px-2 text-left text-xs',
                        onClick: () => onFolder(item.id),
                        children: jsx('span', { className: 'truncate', children: item.name }),
                      }),
                      editMode && !item.locked ? jsxs('span', {
                        className: 'ml-auto flex shrink-0',
                        children: [
                          jsx(IconBtn, { name: 'pencil', label: 'Rename folder', onClick: () => setRenamingFolder(item.id) }),
                          jsx(IconBtn, {
                            name: 'trash',
                            label: 'Remove folder',
                            onClick: () => {
                              const count = promptsIn(data, item.id).length
                              if (count === 0) {
                                save({ ...data, folders: data.folders.filter(row => row.id !== item.id) })
                                if (folder.id === item.id) onFolder(ENHANCERS)
                                return
                              }
                              setConfirmId(item.id)
                            },
                          }),
                        ],
                      }) : null,
                      confirmId === item.id ? jsxs('div', {
                        className: 'flex basis-full gap-2 px-2 pb-1 text-[11px]',
                        children: [
                          jsx('button', {
                            type: 'button',
                            className: 'border-0 bg-transparent p-0 text-(--ui-accent)',
                            onClick: () => {
                              save({
                                ...data,
                                folders: data.folders.filter(row => row.id !== item.id),
                                prompts: data.prompts.map(prompt => prompt.folderId === item.id ? { ...prompt, folderId: ENHANCERS } : prompt),
                              })
                              setConfirmId(null)
                              if (folder.id === item.id) onFolder(ENHANCERS)
                            },
                            children: 'Move to Enhancers',
                          }),
                          jsx('button', {
                            type: 'button',
                            className: 'border-0 bg-transparent p-0 text-destructive',
                            onClick: () => {
                              save({
                                ...data,
                                folders: data.folders.filter(row => row.id !== item.id),
                                prompts: data.prompts.filter(prompt => prompt.folderId !== item.id),
                              })
                              setConfirmId(null)
                              if (folder.id === item.id) onFolder(ENHANCERS)
                            },
                            children: 'Delete prompts',
                          }),
                        ],
                      }) : null,
                    ],
                  })),
                  editMode ? jsxs('div', {
                    className: 'mt-auto flex items-center gap-1',
                    children: [
                      jsx('button', {
                        type: 'button',
                        className: 'inline-flex size-6 shrink-0 items-center justify-center border-0 bg-transparent text-(--ui-text-tertiary)',
                        'aria-label': 'Add folder',
                        onClick: () => setAdding(true),
                        children: jsx(Codicon, { name: 'add', size: '0.85rem' }),
                      }),
                      adding ? jsx('input', {
                        autoFocus: true,
                        className: 'h-7 min-w-0 flex-1 border-0 border-b border-(--ui-stroke-secondary) bg-transparent text-xs',
                        placeholder: 'Folder name',
                        onKeyDown: event => {
                          if (event.key === 'Escape') setAdding(false)
                          if (event.key !== 'Enter') return
                          const name = event.currentTarget.value.trim()
                          if (!name) return
                          const id = uid()
                          save({ ...data, folders: [...data.folders, { id, name }] })
                          setAdding(false)
                          onFolder(id)
                        },
                      }) : null,
                    ],
                  }) : null,
                ],
              }),
              jsxs('div', {
                style: MAIN,
                children: [
                  jsxs('div', {
                    className: 'mb-2 flex items-center justify-between',
                    children: [
                      jsxs('strong', { className: 'text-sm font-semibold', children: [folder.name, jsx('span', { className: 'ml-2 font-normal text-(--ui-text-tertiary)', children: String(cards.length) })] }),
                      jsxs('div', {
                        className: 'flex items-center gap-3',
                        children: [
                          jsx('button', {
                            type: 'button',
                            className: 'border-0 bg-transparent text-xs text-(--ui-accent)',
                            onClick: () => {
                              const draft = readEditor(focusedEditor())
                              if (!draft) {
                                host.notify({ kind: 'error', message: 'The composer is empty.' })
                                return
                              }
                              const line = draft.split('\n').map(row => row.trim()).find(Boolean) || 'Imported'
                              const prompt = { id: uid(), folderId: folder.id, name: line, body: draft }
                              const at = data.prompts.findIndex(row => row.folderId === folder.id)
                              const next = data.prompts.slice()
                              next.splice(at < 0 ? next.length : at, 0, prompt)
                              save({ ...data, prompts: next })
                            },
                            children: 'Import Prompt',
                          }),
                          jsx('button', {
                            type: 'button',
                            className: 'border-0 bg-transparent text-xs text-(--ui-accent)',
                            onClick: () => {
                              const prompt = { id: uid(), folderId: folder.id, name: 'Untitled', body: '' }
                              save({ ...data, prompts: [...data.prompts, prompt] })
                              onEdit(prompt)
                            },
                            children: 'New prompt',
                          }),
                        ],
                      }),
                    ],
                  }),
                  ...cards.flatMap((prompt, index) => [
                    drop === index ? jsx('div', { 'data-pe-gap': '', key: `gap-${index}` }) : null,
                    jsxs('article', {
                    key: prompt.id,
                    draggable: true,
                    className: 'min-w-0',
                    style: { ...CARD, marginBottom: drop === index + 1 || (index === cards.length - 1 && drop !== cards.length) ? 0 : 8 },
                    onDragStart: () => { dragId.current = prompt.id },
                    onDragEnd: () => setDrop(null),
                    onDragOver: event => {
                      event.preventDefault()
                      const rect = event.currentTarget.getBoundingClientRect()
                      setDrop(event.clientY < rect.top + rect.height / 2 ? index : index + 1)
                    },
                    onDrop: event => {
                      event.preventDefault()
                      event.stopPropagation()
                      const id = dragId.current
                      if (id) reorderTo(id, drop == null ? index : drop)
                      setDrop(null)
                    },
                    children: [
                      jsxs('div', {
                        className: 'min-w-0',
                        children: [
                          jsxs('div', {
                            className: 'flex min-w-0 items-center gap-2',
                            children: [
                              jsx('span', {
                                className: 'text-(--ui-text-tertiary)',
                                children: jsx(Codicon, { name: 'gripper', size: '0.75rem' }),
                              }),
                              renaming === prompt.id ? jsx('input', {
                                autoFocus: true,
                                className: 'h-6 min-w-0 flex-1 border-0 bg-transparent text-xs font-semibold',
                                defaultValue: prompt.name,
                                onBlur: event => {
                                  const name = event.target.value.trim() || prompt.name
                                  updatePrompts(data.prompts.map(row => row.id === prompt.id ? { ...row, name } : row))
                                  setRenaming(null)
                                },
                                onKeyDown: event => { if (event.key === 'Enter') event.currentTarget.blur() },
                              }) : jsx('b', { className: 'min-w-0 flex-1 truncate text-xs', children: prompt.name }),
                              jsxs('div', {
                                className: 'ml-auto flex shrink-0',
                                children: [
                                  jsx(IconBtn, { name: 'insert', label: 'Add to composer', onClick: () => usePrompt(prompt, 'add', { dismiss: true }) }),
                                  jsx(IconBtn, { name: 'send', label: 'Send', onClick: () => usePrompt(prompt, 'send', { dismiss: true }) }),
                                  jsx(IconBtn, { name: 'edit', label: 'Edit', onClick: () => onEdit(prompt) }),
                                  jsx(IconBtn, { name: 'symbol-string', label: 'Rename', onClick: () => setRenaming(prompt.id) }),
                                  jsx(IconBtn, { name: 'trash', label: 'Delete', onClick: () => updatePrompts(data.prompts.filter(row => row.id !== prompt.id)) }),
                                ],
                              }),
                            ],
                          }),
                          jsx(Clamp, { text: (prompt.body || '').replace(/\s+/g, ' ').trim() }),
                        ],
                      }),
                    ],
                  }),
                ].filter(Boolean)),
                drop === cards.length ? jsx('div', { 'data-pe-gap': '', key: 'gap-end' }) : null,
                ],
              }),
            ],
          }),
        ],
      }),
    }),
  })
}

function EditDialog({ prompt, onClose }) {
  const data = useLib()
  const [body, setBody] = useState(prompt ? prompt.body : '')
  useEffect(() => { setBody(prompt ? prompt.body : '') }, [prompt])
  function commit() {
    if (!prompt) return
    save({ ...data, prompts: data.prompts.map(row => row.id === prompt.id ? { ...row, body } : row) })
    onClose()
  }
  return jsx(Dialog, {
    open: Boolean(prompt),
    onOpenChange: next => { if (!next) onClose() },
    children: jsx(DialogContent, {
      fitContent: true,
      className: 'max-w-[92vw]',
      bodyClassName: 'block min-w-0 p-4',
      children: jsxs('div', {
        'data-pe-edit': '',
        style: { width: '100%', maxWidth: '100%', minWidth: 0, boxSizing: 'border-box' },
        children: [
          jsx(DialogHeader, { children: jsx(DialogTitle, { children: prompt ? prompt.name : 'Edit' }) }),
          jsx(Textarea, {
            value: body,
            onChange: event => setBody(event.target.value),
            onKeyDown: event => {
              if (event.key !== 'Escape') return
              event.preventDefault()
              event.stopPropagation()
              onClose()
            },
            style: {
              display: 'block',
              width: '100%',
              maxWidth: '100%',
              minWidth: 0,
              boxSizing: 'border-box',
              minHeight: '16rem',
            },
          }),
          jsx('div', {
            className: 'mt-3 flex justify-center',
            children: jsx(Button, { type: 'button', onClick: commit, children: 'Save' }),
          }),
        ],
      }),
    }),
  })
}

function ComposerTools() {
  const view = useValue(host.state.viewport)
  const prior = usePrior()
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [folderId, setFolderId] = useState(ENHANCERS)
  const [editing, setEditing] = useState(null)
  useEffect(() => {
    openLibrary = id => {
      setFolderId(id || ENHANCERS)
      setLibraryOpen(true)
    }
    closeLibrary = () => setLibraryOpen(false)
    return () => {
      openLibrary = null
      closeLibrary = null
    }
  }, [])
  if (view && view.narrow) return null
  return jsxs(Fragment, {
    children: [
      prior == null ? null : jsx('button', {
        type: 'button',
        className: GHOST,
        'aria-label': 'Undo',
        title: 'Undo',
        onClick: undoEnhancement,
        children: jsx(Codicon, { name: 'discard', size: '0.95rem' }),
      }),
      jsx(EnhanceMenu, {}),
      jsx('button', {
        type: 'button',
        className: GHOST,
        'aria-label': 'Library',
        title: 'Library',
        onClick: () => setLibraryOpen(true),
        children: jsx(Codicon, { name: 'library', size: '0.95rem' }),
      }),
      jsx(LibraryDialog, {
        open: libraryOpen,
        folderId,
        onFolder: setFolderId,
        onClose: () => setLibraryOpen(false),
        onEdit: prompt => setEditing(prompt),
      }),
      jsx(EditDialog, { prompt: editing, onClose: () => setEditing(null) }),
    ],
  })
}

const CSS = `
[data-slot="dialog-content"]:has([data-pe-library]){width:min(46rem,92vw)!important;max-width:min(46rem,92vw)!important}
[data-slot="dialog-content"]:has([data-pe-edit]){width:min(36.8rem,74vw)!important;max-width:min(36.8rem,74vw)!important}
[data-pe-edit],[data-pe-edit] textarea{display:block;width:100%;max-width:100%;min-width:0;box-sizing:border-box}
[data-pe-clamp]{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
[data-pe-gap]{height:2px;margin:3px 0;background:var(--ui-accent)}
[data-pe-over]{outline:1px solid var(--ui-accent);outline-offset:-1px}
`

export default {
  id: ID,
  name: 'Prompt Enhancer',
  description: 'Send a saved prompt with the current draft as context. Folders, reorder, and a one-call model override that never writes the session.',
  defaultEnabled: true,
  register(ctx) {
    storage = ctx.storage
    openExternal = ctx.os && ctx.os.openExternal
    load()
    const style = document.createElement('style')
    style.id = STYLE_ID
    style.textContent = CSS
    document.head.appendChild(style)
    ctx.onDispose(() => {
      document.getElementById(STYLE_ID)?.remove()
    })
    ctx.register({
      id: 'actions',
      area: COMPOSER_AREAS.actions,
      order: 10,
      render: () => jsx(ComposerTools, {}),
    })
  },
}
