/**
 * Reasoning Switch — statusbar control for the focused session's reasoning
 * effort.
 *
 * - Word + gear in the statusbar (right area). Click the word to rotate through
 *   the levels enabled in the dialog. Gear opens the config dialog.
 * - Dialog: the seven standardized levels (minimal..ultra) plus none; per-level
 *   color (theme-variable dropdown); checkbox = include in rotation; a prompt
 *   limit that auto-demotes to the next lower included level after N user
 *   prompts.
 *
 * Gateway contract (same calls the app's own model menu makes):
 *   host.request('config.get',  { key: 'reasoning', session_id }) -> { value }
 *   host.request('config.set',  { key: 'reasoning', session_id, value })
 * Session-scoped: never touches the global profile default.
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
  Input,
  Tip as Tooltip,
  STATUSBAR_AREAS,
  host,
} from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import * as React from 'react'
import { useEffect, useRef, useState } from 'react'

// ── level vocabulary (mirrors hermes_constants.VALID_REASONING_EFFORTS + none) ──

const NONE = 'none'
const LEVELS = [NONE, 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra']
const LABEL = {
  none: 'none',
  minimal: 'Minimal',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  xhigh: 'Extra High',
  max: 'Max',
  ultra: 'Ultra',
}
// Lowest -> highest ordering used for auto-demotion. 'none' is its own floor.
const ASCENDING = [NONE, 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra']

// ── plugin-scoped persistence (survives restarts; namespaced by the host) ──
// Shape: { levels: {<level>: {included: bool, color: string|null, maxPrompts: int|null}},
//          current: <level>, remaining: {<sessionId>: int} }
const DEFAULT_LEVELS = () => {
  const out = {}
  for (const lv of LEVELS) {
    out[lv] = {
      included: lv === 'medium' || lv === 'high',
      color: null,
      maxPrompts: null, // null = unlimited
    }
  }
  return out
}

function loadConfig(storage) {
  const fallback = { levels: DEFAULT_LEVELS(), current: 'medium' }
  const saved = storage.get('config', null)
  if (!saved || typeof saved !== 'object') return fallback
  const cfg = {
    levels: DEFAULT_LEVELS(),
    current: LEVELS.includes(saved.current) ? saved.current : 'medium',
  }
  for (const lv of LEVELS) {
    const s = saved.levels?.[lv]
    if (s) {
      cfg.levels[lv] = {
        included: Boolean(s.included),
        color: typeof s.color === 'string' ? s.color : null,
        maxPrompts: Number.isFinite(s.maxPrompts) && s.maxPrompts > 0 ? Math.floor(s.maxPrompts) : null,
      }
    }
  }
  // Never strand the user: the current level must be included in the rotation.
  if (!cfg.levels[cfg.current].included) {
    const first = ASCENDING.find(lv => cfg.levels[lv].included)
    if (first) cfg.current = first
  }
  return cfg
}

// ── theme-variable color palette for the dropdown ──

const COLOR_CHOICES = [
  { value: '', label: 'Default', css: 'var(--ui-text-secondary)' },
  { value: 'var(--ui-accent)', label: 'Accent', css: 'var(--ui-accent)' },
  { value: '#22c55e', label: 'Green', css: '#22c55e' },
  { value: '#f59e0b', label: 'Amber', css: '#f59e0b' },
  { value: '#ef4444', label: 'Red', css: '#ef4444' },
  { value: '#3b82f6', label: 'Blue', css: '#3b82f6' },
  { value: '#a855f7', label: 'Purple', css: '#a855f7' },
  { value: '#ec4899', label: 'Pink', css: '#ec4899' },
  { value: '#14b8a6', label: 'Teal', css: '#14b8a6' },
]

// ── gateway helpers ──

async function getEffort(sessionId) {
  if (!sessionId) return null
  try {
    const res = await host.request('config.get', { key: 'reasoning', session_id: sessionId })
    const v = String(res?.value ?? '').trim().toLowerCase()
    if (v === 'false' || v === 'disabled') return NONE
    return LEVELS.includes(v) ? v : null
  } catch {
    return null
  }
}

async function setEffort(sessionId, level) {
  if (!sessionId) return false
  try {
    await host.request('config.set', { key: 'reasoning', session_id: sessionId, value: level })
    return true
  } catch {
    return false
  }
}

// ── statusbar chip ──

function LevelChip({ cfg, storage, onOpenDialog }) {
  const [sessionId, setSessionId] = useState(() => host.state.focusedSessionId.get())
  const [live, setLive] = useState(null) // effort reported by the gateway
  const [remaining, setRemaining] = useState(null) // prompts left at this level
  const [flash, setFlash] = useState(false)

  // Follow tile focus.
  useEffect(() => host.state.focusedSessionId.subscribe(id => setSessionId(id)), [])

  // Seed + re-read whenever the focused session changes.
  useEffect(() => {
    let alive = true
    getEffort(sessionId).then(v => alive && setLive(v))
    return () => {
      alive = false
    }
  }, [sessionId])

  // Rotation prompt counter: a user prompt = awaitingResponse rising edge on
  // the focused session (send -> first assistant payload).
  useEffect(() => {
    let prev = host.state.awaitingResponse.get()
    return host.state.awaitingResponse.subscribe(now => {
      if (now && !prev) {
        const sid = host.state.focusedSessionId.get()
        if (sid) tickPrompt(sid)
      }
      prev = now
    })
  }, [])

  // Poll the remaining counter (tickPrompt writes through storage).
  useEffect(() => {
    const t = setInterval(() => {
      const sid = host.state.focusedSessionId.get()
      const rem = sid ? storage.get('remaining', {})[sid] : undefined
      setRemaining(Number.isFinite(rem) ? rem : null)
    }, 500)
    return () => clearInterval(t)
  }, [])

  // Auto-demotion: when the counter hits 0 and the gateway-reported level is
  // still the limited one, drop to the next lower included level.
  useEffect(() => {
    if (remaining !== 0 || !sessionId || !live) return
    const entry = cfg.levels[live]
    if (!entry || entry.maxPrompts == null) return
    if (live === NONE) return // 'none' is the floor; nowhere to demote
    // Levels strictly below `live`, high -> low order ('none' included when
    // checked: demoting to thinking-off is a valid step).
    const lower = [...ASCENDING].reverse().slice(ASCENDING.indexOf(live) + 1)
    const next = lower.find(lv => cfg.levels[lv].included)
    if (!next) return
    setEffort(sessionId, next).then(ok => {
      if (!ok) return
      const all = storage.get('remaining', {})
      delete all[sessionId]
      storage.set('remaining', all)
      setLive(next)
      setRemaining(null)
    })
  }, [remaining, live, sessionId, cfg])

  const displayed = live || cfg.current
  const color = cfg.levels[displayed]?.color || null
  const limited = cfg.levels[displayed]?.maxPrompts != null

  const rotate = async () => {
    const included = ASCENDING.filter(lv => cfg.levels[lv].included)
    if (!included.length || !sessionId) return
    const idx = included.indexOf(displayed)
    const next = included[(idx + 1) % included.length] ?? included[0]
    const ok = await setEffort(sessionId, next)
    if (!ok) return
    const all = storage.get('remaining', {})
    const maxP = cfg.levels[next].maxPrompts
    if (maxP != null) all[sessionId] = maxP
    else delete all[sessionId]
    storage.set('remaining', all)
    storage.set('config', { ...cfg, current: next })
    setLive(next)
    setRemaining(maxP ?? null)
    setFlash(true)
    setTimeout(() => setFlash(false), 400)
  }

  const label = LABEL[displayed] || displayed
  const tip = [
    `Reasoning: ${label}`,
    limited && remaining != null ? `${remaining} prompt${remaining === 1 ? '' : 's'} left at this level` : null,
    'Click to rotate · gear to configure',
  ]
    .filter(Boolean)
    .join('  ·  ')

  return jsxs('span', {
    className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] tabular-nums cursor-pointer select-none',
    onClick: rotate,
    children: [
      jsx(Tooltip, {
        label: tip,
        children: jsxs('span', {
          className: 'inline-flex items-center gap-1' + (flash ? ' opacity-60' : ''),
          children: [
            jsx(Codicon, { name: 'lightbulb', size: '0.6rem', style: { color: color || 'var(--ui-text-tertiary)' } }),
            jsx('span', { style: { color: color || 'var(--ui-text-tertiary)' }, children: label + ':' }),
            jsx('span', { style: { color: 'var(--ui-text-quaternary)' }, children: limited && remaining != null ? String(remaining) : '' }),
          ],
        }),
      }),
      jsx('span', {
        title: 'Configure reasoning rotation',
        onClick: e => {
          e.stopPropagation()
          onOpenDialog()
        },
        className: 'inline-flex items-center justify-center cursor-pointer text-(--ui-text-quaternary) hover:text-(--ui-text-tertiary)',
        children: jsx(Codicon, { name: 'settings-gear', size: '0.7rem' }),
      }),
    ],
  })
}

// Prompt tick shared with the subscriber above (module-level to avoid rebinds).
let _tickPrompt = () => {}
function tickPrompt(sid) {
  _tickPrompt(sid)
}

// ── config dialog ──

function ConfigDialog({ cfg, setCfg, open, onOpenChange }) {
  if (!open) return null
  const update = (lv, patch) => {
    setCfg(prev => ({
      ...prev,
      levels: { ...prev.levels, [lv]: { ...prev.levels[lv], ...patch } },
    }))
  }

  const includedCount = ASCENDING.filter(lv => cfg.levels[lv].included).length

  return jsx(Dialog, {
    open,
    onOpenChange,
    children: jsx(DialogContent, {
      fitContent: true,
      className: 'min-w-[24rem]',
      children: [
        jsxs(DialogHeader, {
          children: [
            jsx(DialogTitle, { children: 'Reasoning Switch' }),
            jsx('p', {
              className: 'text-xs text-(--ui-text-tertiary)',
              children: 'Click the word to rotate. A prompt limit auto-demotes after N prompts.',
            }),
          ],
        }),
        jsx('div', {
          className: 'flex w-max flex-col gap-1.5 py-2',
          children: ASCENDING.map(lv => {
            const entry = cfg.levels[lv]
            const isCurrent = cfg.current === lv
            return jsxs('div', {
              'data-rs-row': '',
              className: 'flex items-center gap-2 rounded-md px-2 py-1.5',
              style: {
                border: '1px solid var(--ui-stroke-secondary, var(--ui-border))',
                ...(entry.color ? { '--rs-color': entry.color } : {}),
              },
              children: [
                jsx(Checkbox, {
                  checked: entry.included,
                  onCheckedChange: v => update(lv, { included: Boolean(v) }),
                  disabled: isCurrent && entry.included && includedCount === 1,
                  title: 'Include in the click-rotation',
                }),
                jsx('span', {
                  className: 'w-24 shrink-0 text-xs font-medium',
                  style: { color: entry.color || 'var(--ui-text-secondary)' },
                  children: LABEL[lv],
                }),
                jsx(ColorSelect, {
                  value: entry.color || '',
                  onChange: v => update(lv, { color: v || null }),
                }),
                jsx('span', { className: 'flex-1' }),
                jsx('span', {
                  className: 'text-[0.65rem] text-(--ui-text-quaternary) shrink-0',
                  children: 'prompts',
                }),
                jsx(Input, {
                  type: 'number',
                  min: 1,
                  value: entry.maxPrompts ?? '',
                  placeholder: '∞',
                  onChange: e => {
                    const raw = e.target.value
                    const n = parseInt(raw, 10)
                    update(lv, { maxPrompts: Number.isFinite(n) && n > 0 ? n : null })
                  },
                  className: 'w-16 h-6 text-xs shrink-0',
                }),
              ],
            }, lv)
          }),
        }),
        jsxs('div', {
          className: 'flex items-center justify-between pt-1',
          children: [
            jsx('span', {
              className: 'text-[0.65rem] text-(--ui-text-quaternary)',
              children: includedCount
                ? `${includedCount} level${includedCount === 1 ? '' : 's'} in rotation`
                : 'No levels in rotation — clicking the word does nothing',
            }),
            jsx(Button, { variant: 'outline', size: 'sm', onClick: () => onOpenChange(false), children: 'Done' }),
          ],
        }),
      ],
    }),
  })
}

// Small themed dropdown (native select; color-scheme pinned per app mode).
// The closed select mirrors the chosen color in its text and border.
function ColorSelect({ value, onChange }) {
  const chosen = COLOR_CHOICES.find(c => c.value === value)
  const active = value && chosen
  return jsx('select', {
    'data-rs-select': '',
    value,
    onChange: e => onChange(e.target.value),
    className: 'h-6 rounded-md border text-xs px-1.5 shrink-0',
    style: {
      background: 'transparent',
      color: active ? value : 'var(--ui-text-secondary, var(--foreground))',
      borderColor: active ? value : 'var(--ui-border)',
    },
    children: COLOR_CHOICES.map(c =>
      jsx('option', {
        value: c.value,
        style: {
          background: 'var(--ui-bg-elevated, var(--background, #222))',
          color: 'var(--ui-text-secondary, var(--foreground))',
        },
        children: c.label,
      }, c.label)
    ),
  })
}

// ── root ──

function Root() {
  const [cfg, setCfg] = useState(() => loadConfig(_storage))
  const [dialogOpen, setDialogOpen] = useState(false)
  const cfgRef = useRef(cfg)
  cfgRef.current = cfg

  // Persist on every change.
  useEffect(() => {
    _storage.set('config', cfg)
  }, [cfg])

  // Keep the gateway and local state in sync: poll the live effort lightly so
  // external changes (slash command, model menu) still repaint the chip.
  useEffect(() => {
    let alive = true
    const poll = async () => {
      const sid = host.state.focusedSessionId.get()
      const v = await getEffort(sid)
      if (alive && v && v !== cfgRef.current.current) {
        setCfg(prev => (prev.current === v ? prev : { ...prev, current: v }))
      }
    }
    const t = setInterval(poll, 4000)
    poll()
    return () => {
      alive = false
      clearInterval(t)
    }
  }, [])

  // Wire the prompt tick with live access to config.
  useEffect(() => {
    _tickPrompt = sid => {
      const cur = cfgRef.current.levels[cfgRef.current.current]
      if (!cur || cur.maxPrompts == null) return
      const all = _storage.get('remaining', {})
      const left = (Number.isFinite(all[sid]) ? all[sid] : cur.maxPrompts) - 1
      all[sid] = Math.max(0, left)
      _storage.set('remaining', all)
    }
    return () => {
      _tickPrompt = () => {}
    }
  }, [])

  return jsxs(Fragment, {
    children: [
      jsx(LevelChip, { cfg, storage: _storage, onOpenDialog: () => setDialogOpen(true) }),
      jsx(ConfigDialog, { cfg, setCfg, open: dialogOpen, onOpenChange: setDialogOpen }),
    ],
  })
}

// Module-level storage handle, injected at register.
let _storage = null
let _styleEl = null

export default {
  id: 'reasoning-switch',
  name: 'Reasoning Switch',
  description: 'Statusbar reasoning-effort rotation with per-level colors and prompt limits.',

  register(ctx) {
    _storage = ctx.storage

    // Native select popup: pin color-scheme to the app's resolved mode so the
    // dropdown list is not white-on-white in dark mode (OS may disagree).
    _styleEl = document.createElement('style')
    _styleEl.textContent = `
      html[data-hermes-mode="dark"] select[data-rs-select],
      html.dark select[data-rs-select] { color-scheme: dark; }
      html[data-hermes-mode="light"] select[data-rs-select] { color-scheme: light; }
      select[data-rs-select] option {
        background: var(--ui-bg-elevated, var(--background, inherit));
        color: var(--ui-text-secondary, var(--foreground));
      }
      /* a chosen color tints the row's checkbox checked state */
      [data-rs-row] [data-slot="checkbox"][data-state="checked"] {
        border-color: var(--rs-color, var(--ui-accent)) !important;
        background: color-mix(in srgb, var(--rs-color, var(--ui-accent)) 55%, transparent) !important;
      }
      /* number inputs: no vertical spinner arrows */
      [data-rs-row] input[type="number"] { appearance: textfield; -moz-appearance: textfield; }
      [data-rs-row] input[type="number"]::-webkit-outer-spin-button,
      [data-rs-row] input[type="number"]::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
    `
    document.head.appendChild(_styleEl)
    ctx.onDispose(() => {
      _styleEl?.remove()
      _styleEl = null
      _tickPrompt = () => {}
    })

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 120, // between provider chips (50) and the provider-status gear (210)
      render: () => jsx(Root, {}),
    })
  },
}
