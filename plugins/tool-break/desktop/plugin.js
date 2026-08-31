/**
 * tool-break desktop half. Layout A: name + time pill left,
 * Break / Message / Again / gear right. Message injects "/break "
 * into the composer. Gear sets elapsed color grades, auto-break
 * checkboxes, and tools that never show the strip.
 */
import {
  cn,
  Codicon,
  COMPOSER_AREAS,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  host,
  KEYBINDS_AREA,
  PALETTE_AREA,
  Tip as Tooltip
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useRef, useState } from 'react'

const ID = 'tool-break'
const GRADE_KEY = 'tool-break.grades'
const HIDE_KEY = 'tool-break.hide'
const DEFAULT_GRADES = {
  amber: 30,
  amberBold: 60,
  redBold: 120,
  autoAmber: false,
  autoAmberBold: false,
  autoRedBold: false
}
const DEFAULT_HIDE = [
  'web_search',
  'web_extract',
  'open_page',
  'skill_view',
  'skill_manage',
  'read_file',
  'write_file',
  'patch',
  'search_files',
  'session_search',
  'memory',
  'todo',
  'viking_search',
  'viking_read',
  'image_generate',
  'clarify'
]

const BTN =
  'h-6 shrink-0 rounded-md px-2 text-[0.68rem] font-semibold text-(--ui-text-primary) hover:bg-(--chrome-action-hover)'
const BTN_OFF =
  'h-6 shrink-0 rounded-md px-2 text-[0.68rem] font-semibold text-(--ui-text-tertiary) opacity-40 cursor-not-allowed'
const GEAR =
  'inline-flex size-6 shrink-0 items-center justify-center rounded-md text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-(--ui-text-primary)'
const FIELD =
  'h-6 w-14 rounded border bg-transparent px-1.5 text-[0.7rem] text-(--ui-text-secondary)'
const LIMIT_FIELD =
  'mx-auto block h-6 w-10 rounded border bg-transparent px-1 text-center text-[0.7rem] tabular-nums text-(--ui-text-secondary) [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none'
const PILL =
  'shrink-0 rounded-full px-1.5 py-0.5 font-mono text-[0.6875rem] tabular-nums leading-4'
const CHIP =
  'inline-flex h-6 items-center rounded-md border border-(--ui-stroke-secondary) px-1.5 text-[0.65rem] text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)'

function sessionId() {
  return (
    (host.state.focusedSessionId && host.state.focusedSessionId.get()) ||
    (host.state.activeSessionId && host.state.activeSessionId.get()) ||
    ''
  )
}

function clampSec(value, fallback) {
  const n = Number(value)
  if (!Number.isFinite(n) || n < 1) {
    return fallback
  }
  return Math.min(3600, Math.round(n))
}

function asBool(value, fallback) {
  if (typeof value === 'boolean') {
    return value
  }
  return fallback
}

function loadGrades() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(GRADE_KEY) || '')
    return {
      amber: clampSec(raw.amber, DEFAULT_GRADES.amber),
      amberBold: clampSec(raw.amberBold, DEFAULT_GRADES.amberBold),
      redBold: clampSec(raw.redBold, DEFAULT_GRADES.redBold),
      autoAmber: asBool(raw.autoAmber, false),
      autoAmberBold: asBool(raw.autoAmberBold, false),
      autoRedBold: asBool(raw.autoRedBold, false)
    }
  } catch {
    return { ...DEFAULT_GRADES }
  }
}

function saveGrades(grades) {
  window.localStorage.setItem(GRADE_KEY, JSON.stringify(grades))
}

function loadHide() {
  try {
    const raw = JSON.parse(window.localStorage.getItem(HIDE_KEY) || '')
    if (!Array.isArray(raw)) {
      return [...DEFAULT_HIDE]
    }
    return raw.map(name => String(name || '').trim().toLowerCase()).filter(Boolean)
  } catch {
    return [...DEFAULT_HIDE]
  }
}

function saveHide(names) {
  window.localStorage.setItem(HIDE_KEY, JSON.stringify(names))
}

function gradeStyle(elapsedSec, grades) {
  if (elapsedSec >= grades.redBold) {
    return { color: '#ef4444', fontWeight: 700 }
  }
  if (elapsedSec >= grades.amberBold) {
    return { color: '#f59e0b', fontWeight: 700 }
  }
  if (elapsedSec >= grades.amber) {
    return { color: '#f59e0b', fontWeight: 500 }
  }
  return { color: 'var(--ui-text-tertiary)', fontWeight: 500 }
}

async function runSlash(command, quiet) {
  const sid = sessionId()
  if (!sid) {
    if (!quiet) {
      host.notify({ kind: 'info', message: 'No focused session' })
    }
    return null
  }
  const res = await host.request('slash.exec', { session_id: sid, command })
  return String((res && (res.output || res.message || res.result)) || '')
}

async function breakNow(command) {
  try {
    const output = (await runSlash(command)) || 'ok'
    if (output.toLowerCase().includes('nothing')) {
      return
    }
    host.notify({ kind: 'info', message: output.slice(0, 240) })
  } catch (err) {
    host.notify({
      kind: 'error',
      message: err && err.message ? String(err.message) : 'slash.exec failed'
    })
  }
}

function visibleComposerTarget() {
  const nodes = document.querySelectorAll('[data-composer-target]')
  for (const node of nodes) {
    if (node.closest('[data-pane-hidden]')) {
      continue
    }
    if (node.dataset.composerTarget) {
      return node.dataset.composerTarget
    }
  }
  return 'main'
}

function ensureBreakTrailingSpace() {
  const roots = document.querySelectorAll('[data-composer-target]')
  let editor = null
  for (const root of roots) {
    if (root.closest('[data-pane-hidden]')) {
      continue
    }
    editor = root.querySelector('[contenteditable="true"]')
    if (editor) {
      break
    }
  }
  if (!editor) {
    return
  }
  const text = (editor.innerText || editor.textContent || '').replace(/\u00a0/g, ' ')
  if (text === '/break' || text.startsWith('/break\n')) {
    editor.focus()
    const sel = window.getSelection()
    if (sel) {
      const range = document.createRange()
      range.selectNodeContents(editor)
      range.collapse(false)
      sel.removeAllRanges()
      sel.addRange(range)
    }
    document.execCommand('insertText', false, ' ')
  } else {
    editor.focus()
  }
}

function injectBreakMessage() {
  const target = visibleComposerTarget()
  window.setTimeout(() => {
    window.dispatchEvent(
      new CustomEvent('hermes:composer-insert', {
        detail: { mode: 'prefix', target, text: '/break' }
      })
    )
    window.dispatchEvent(
      new CustomEvent('hermes:composer-focus', {
        detail: { target }
      })
    )
  }, 0)
  window.setTimeout(ensureBreakTrailingSpace, 40)
}

function parseStatus(raw) {
  if (!raw) {
    return { inflight: false, tools: [] }
  }
  const start = raw.indexOf('{')
  const end = raw.lastIndexOf('}')
  if (start < 0 || end <= start) {
    return { inflight: false, tools: [] }
  }
  try {
    const data = JSON.parse(raw.slice(start, end + 1))
    return data && typeof data === 'object' ? data : { inflight: false, tools: [] }
  } catch {
    return { inflight: false, tools: [] }
  }
}

function fmtElapsed(ms) {
  const s = Math.max(0, Math.floor((Number(ms) || 0) / 1000))
  const m = Math.floor(s / 60)
  const r = s % 60
  if (m >= 60) {
    const h = Math.floor(m / 60)
    return `${h}:${String(m % 60).padStart(2, '0')}:${String(r).padStart(2, '0')}`
  }
  return `${m}:${String(r).padStart(2, '0')}`
}

function elapsedMs(tool, now) {
  if (!tool) {
    return 0
  }
  if (tool.started_wall) {
    return Math.max(0, now - tool.started_wall * 1000)
  }
  return Number(tool.elapsed_ms) || 0
}

function toolList(status) {
  if (Array.isArray(status.tools) && status.tools.length) {
    return status.tools
  }
  if (status.inflight) {
    return [status]
  }
  return []
}

function isHidden(name, hide) {
  return hide.includes(String(name || '').toLowerCase())
}

function visibleTools(status, hide) {
  return toolList(status).filter(tool => {
    const name = String(tool.name || '').toLowerCase()
    if (isHidden(name, hide)) {
      return false
    }
    const spawn = name === 'terminal' || name === 'process'
    return tool.killable === true || spawn
  })
}

function GradeRow({ label, hint, value, onChange, auto, onAuto }) {
  return jsxs('tr', {
    className: 'border-t border-(--ui-stroke-secondary)',
    children: [
      jsx('td', {
        className: 'py-1.5 pr-3',
        children: jsxs('span', {
          className: 'block min-w-0',
          children: [
            jsx('span', {
              className: 'block text-[0.75rem] text-(--ui-text-primary)',
              children: label
            }),
            jsx('span', {
              className: 'block text-[0.65rem] text-(--ui-text-tertiary)',
              children: hint
            })
          ]
        })
      }),
      jsx('td', {
        className: 'w-[5.75rem] py-1.5 text-center align-middle',
        children: jsx('input', {
          className: LIMIT_FIELD,
          type: 'number',
          min: 1,
          max: 3600,
          value: value,
          onChange: event => onChange(event.target.value)
        })
      }),
      jsx('td', {
        className: 'w-[6.75rem] py-1.5 text-center align-middle',
        children: jsx('input', {
          type: 'checkbox',
          checked: !!auto,
          title: 'Auto Break',
          'aria-label': `${label} auto break`,
          onChange: event => onAuto(event.target.checked)
        })
      })
    ]
  })
}

function HideRow({ hide, onChange }) {
  const [draft, setDraft] = useState('')
  const add = () => {
    const name = draft.trim().toLowerCase().replace(/\s+/g, '_')
    if (!name) {
      return
    }
    if (!hide.includes(name)) {
      onChange([...hide, name])
    }
    setDraft('')
  }
  return jsxs('div', {
    className: 'space-y-1.5 py-2',
    children: [
      jsx('div', {
        className: 'text-[0.75rem] text-(--ui-text-primary)',
        children: 'Never show the bar'
      }),
      jsx('div', {
        className: 'text-[0.65rem] text-(--ui-text-tertiary)',
        children: 'Select in-process tools that rarely break to exclude from break monitoring.'
      }),
      jsx('div', {
        className: 'flex flex-wrap gap-1',
        children: hide.map(name =>
          jsx(
            'button',
            {
              type: 'button',
              className: CHIP,
              title: 'Show this tool',
              onClick: () => onChange(hide.filter(item => item !== name)),
              children: name
            },
            name
          )
        )
      }),
      jsxs('div', {
        className: 'flex items-center gap-1.5',
        children: [
          jsx('input', {
            className: cn(FIELD, 'w-40 text-left'),
            placeholder: 'tool_name',
            value: draft,
            onChange: event => setDraft(event.target.value),
            onKeyDown: event => {
              if (event.key === 'Enter') {
                event.preventDefault()
                add()
              }
            }
          }),
          jsx('button', {
            className: BTN,
            type: 'button',
            onClick: add,
            children: 'Add'
          })
        ]
      })
    ]
  })
}

function GradeDialog({ open, onOpenChange, grades, onSave, hide, onHide }) {
  const [draft, setDraft] = useState(grades)
  const [hideDraft, setHideDraft] = useState(hide)
  useEffect(() => {
    if (open) {
      setDraft(grades)
      setHideDraft(hide)
    }
  }, [open, grades, hide])
  const setField = (key, raw) => {
    setDraft(prev => ({ ...prev, [key]: raw }))
  }
  const commit = () => {
    const next = {
      amber: clampSec(draft.amber, DEFAULT_GRADES.amber),
      amberBold: clampSec(draft.amberBold, DEFAULT_GRADES.amberBold),
      redBold: clampSec(draft.redBold, DEFAULT_GRADES.redBold),
      autoAmber: !!draft.autoAmber,
      autoAmberBold: !!draft.autoAmberBold,
      autoRedBold: !!draft.autoRedBold
    }
    onSave(next)
    onHide(hideDraft)
    onOpenChange(false)
  }
  return jsx(Dialog, {
    open,
    onOpenChange,
    children: jsxs(DialogContent, {
      className: cn(
        'max-w-md rounded-xl border-(--ui-stroke-secondary)',
        'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_96%,transparent)] backdrop-blur-md'
      ),
      'data-context-menu-skip': true,
      children: [
        jsx(DialogHeader, {
          children: jsx(DialogTitle, { children: 'Break' })
        }),
        jsxs('table', {
          className: 'w-full table-fixed border-collapse',
          children: [
            jsx('colgroup', {
              children: [
                jsx('col', {}),
                jsx('col', { className: 'w-[5.75rem]' }),
                jsx('col', { className: 'w-[6.75rem]' })
              ]
            }),
            jsx('thead', {
              children: jsxs('tr', {
                children: [
                  jsx('th', { className: 'p-0' }),
                  jsx('th', {
                    className:
                      'w-[5.75rem] pb-1 text-center text-[0.65rem] font-normal whitespace-nowrap text-(--ui-text-tertiary)',
                    children: 'Limit (s)'
                  }),
                  jsx('th', {
                    className:
                      'w-[6.75rem] pb-1 text-center text-[0.65rem] font-normal whitespace-nowrap text-(--ui-text-tertiary)',
                    children: 'Auto Break'
                  })
                ]
              })
            }),
            jsxs('tbody', {
              children: [
                jsx(GradeRow, {
                  label: 'Amber',
                  hint: 'Warn',
                  value: draft.amber,
                  auto: draft.autoAmber,
                  onChange: value => setField('amber', value),
                  onAuto: value => setField('autoAmber', value)
                }),
                jsx(GradeRow, {
                  label: 'Amber bold',
                  hint: 'Getting long',
                  value: draft.amberBold,
                  auto: draft.autoAmberBold,
                  onChange: value => setField('amberBold', value),
                  onAuto: value => setField('autoAmberBold', value)
                }),
                jsx(GradeRow, {
                  label: 'Red bold',
                  hint: 'Stuck',
                  value: draft.redBold,
                  auto: draft.autoRedBold,
                  onChange: value => setField('redBold', value),
                  onAuto: value => setField('autoRedBold', value)
                })
              ]
            })
          ]
        }),
        jsx(HideRow, { hide: hideDraft, onChange: setHideDraft }),
        jsxs('div', {
          className: 'flex justify-end gap-2 pt-1',
          children: [
            jsx('button', {
              className: BTN,
              type: 'button',
              onClick: () => onOpenChange(false),
              children: 'Cancel'
            }),
            jsx('button', {
              className: BTN,
              type: 'button',
              onClick: commit,
              children: 'Save'
            })
          ]
        })
      ]
    })
  })
}

function ToolRow({
  tool,
  newest,
  grades,
  now,
  onBreak,
  onMessage,
  onAgain,
  onGear
}) {
  const label = tool.label || tool.name || 'tool'
  const waited = elapsedMs(tool, now)
  const clock = fmtElapsed(waited)
  const tone = gradeStyle(waited / 1000, grades)
  const againOff = tool.again_disabled === true
  const breakCmd = tool.id ? `/break --id ${tool.id}` : '/break'
  const againCmd = tool.id ? `/again --id ${tool.id}` : '/again'
  return jsxs('div', {
    className: 'flex items-center gap-2 py-0.5',
    children: [
      jsxs('div', {
        className: 'flex min-w-0 flex-1 items-center gap-1.5',
        children: [
          jsx('span', {
            className: 'min-w-0 truncate font-mono text-[0.6875rem] text-(--ui-text-secondary)',
            title: label,
            children: label
          }),
          jsx('span', {
            className: PILL,
            style: {
              color: tone.color,
              fontWeight: tone.fontWeight,
              background: 'color-mix(in srgb, var(--ui-bg-quaternary) 80%, transparent)'
            },
            children: clock
          })
        ]
      }),
      jsxs('div', {
        className: 'flex shrink-0 items-center gap-0.5',
        children: [
          jsx(Tooltip, {
            label: 'Kill this spawn.\nKeep the turn.',
            children: jsx('button', {
              className: BTN,
              type: 'button',
              onClick: () => onBreak(breakCmd),
              children: 'Break'
            })
          }),
          newest
            ? jsx(Tooltip, {
                label: 'Put /break in the composer\nso you can type a hint.',
                children: jsx('button', {
                  className: BTN,
                  type: 'button',
                  onClick: onMessage,
                  children: 'Message'
                })
              })
            : null,
          newest
            ? jsx(Tooltip, {
                label: againOff
                  ? 'Again used twice on this call.\nBreak instead.'
                  : 'Kill and reissue\nthis call once.',
                children: jsx('button', {
                  className: againOff ? BTN_OFF : BTN,
                  type: 'button',
                  disabled: againOff,
                  onClick: () => {
                    if (!againOff) {
                      onAgain(againCmd)
                    }
                  },
                  children: 'Again'
                })
              })
            : null,
          newest
            ? jsx(Tooltip, {
                label: 'Grades, auto break, hide list',
                children: jsx('button', {
                  className: GEAR,
                  type: 'button',
                  'aria-label': 'Break settings',
                  onClick: onGear,
                  children: jsx(Codicon, { name: 'settings-gear', size: '0.7rem' })
                })
              })
            : null
        ]
      })
    ]
  })
}

function BreakBar() {
  const [status, setStatus] = useState({ inflight: false, tools: [] })
  const [now, setNow] = useState(() => Date.now())
  const [grades, setGrades] = useState(loadGrades)
  const [hide, setHide] = useState(loadHide)
  const [open, setOpen] = useState(false)
  const fired = useRef(new Set())

  useEffect(() => {
    let stop = false
    let poll = 0
    const tick = async () => {
      try {
        const raw = await runSlash('/break-status', true)
        if (!stop) {
          setStatus(parseStatus(raw))
        }
      } catch {
        if (!stop) {
          setStatus({ inflight: false, tools: [] })
        }
      }
    }
    void tick()
    poll = window.setInterval(() => {
      void tick()
    }, 1000)
    const clock = window.setInterval(() => {
      setNow(Date.now())
    }, 250)
    return () => {
      stop = true
      window.clearInterval(poll)
      window.clearInterval(clock)
    }
  }, [])

  const tools = visibleTools(status, hide)

  useEffect(() => {
    const live = new Set(tools.map(tool => tool.id).filter(Boolean))
    for (const id of Array.from(fired.current)) {
      if (!live.has(id)) {
        fired.current.delete(id)
      }
    }
    for (const tool of tools) {
      if (!tool.id || fired.current.has(tool.id)) {
        continue
      }
      const sec = elapsedMs(tool, now) / 1000
      const hit =
        (grades.autoAmber && sec >= grades.amber) ||
        (grades.autoAmberBold && sec >= grades.amberBold) ||
        (grades.autoRedBold && sec >= grades.redBold)
      if (!hit) {
        continue
      }
      fired.current.add(tool.id)
      void breakNow(`/break --id ${tool.id}`)
    }
  }, [tools, now, grades])

  const dialog = jsx(GradeDialog, {
    open,
    onOpenChange: setOpen,
    grades,
    hide,
    onSave: next => {
      saveGrades(next)
      setGrades(next)
    },
    onHide: next => {
      saveHide(next)
      setHide(next)
    }
  })

  if (!tools.length) {
    return dialog
  }

  return jsxs('div', {
    className: 'flex flex-col gap-0.5',
    children: [
      ...tools.map((tool, index) =>
        jsx(
          ToolRow,
          {
            tool,
            newest: index === 0,
            grades,
            now,
            onBreak: command => {
              void breakNow(command)
            },
            onMessage: injectBreakMessage,
            onAgain: command => {
              void breakNow(command)
            },
            onGear: () => setOpen(true)
          },
          tool.id || `${tool.name}-${index}`
        )
      ),
      dialog
    ]
  })
}

export default {
  id: ID,
  name: 'Break',
  register(ctx) {
    ctx.register({
      id: 'break-bar',
      area: COMPOSER_AREAS.top,
      render: () => jsx(BreakBar, {})
    })
    ctx.register({
      id: 'break-key',
      area: KEYBINDS_AREA,
      data: {
        id: 'tool-break.break',
        label: 'Skip stalled tool call',
        category: 'session',
        defaults: ['mod+shift+b'],
        run: () => {
          void breakNow('/break')
        }
      }
    })
    ctx.register({
      id: 'break-palette',
      area: PALETTE_AREA,
      data: {
        id: 'tool-break.break',
        label: 'Break stalled tool',
        keywords: ['break', 'stuck', 'hung', 'skip', 'tool'],
        run: () => {
          void breakNow('/break')
        }
      }
    })
    ctx.register({
      id: 'again-palette',
      area: PALETTE_AREA,
      data: {
        id: 'tool-break.again',
        label: 'Break and reissue stalled tool',
        keywords: ['again', 'retry', 'reissue', 'stuck'],
        run: () => {
          void breakNow('/again')
        }
      }
    })
  }
}
