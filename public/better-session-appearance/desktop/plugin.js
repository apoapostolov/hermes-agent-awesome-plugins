/**
 * Better Session Appearance for Hermes (public / listed edition).
 *
 * Per-row controls rendered through the SDK session-row slots (#116305
 * item 3): a color dot (trailing) that opens the app's own swatch grid and
 * calls host.sessions.setColor, and an idle glyph (leading) replacing the
 * default dot. All plugin state lives in ctx.storage.
 *
 * Bold titles, auto rules, and Appearance-submenu extras stay in the personal
 * edition; they restyle app-owned DOM and there is no SDK hook for that. See
 * LIMITATIONS.md for the edition split.
 */

import {
  Button,
  ColorSwatches,
  PROFILE_SWATCHES,
  SESSION_ROW_AREAS,
  host,
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useRef, useState } from 'react'

const ID = 'better-session-appearance'

const GLYPHS = [
  'circle-filled', 'star-full', 'heart', 'lightbulb', 'beaker', 'rocket',
  'zap', 'flame', 'book', 'bookmark', 'bug', 'gear',
  'tools', 'terminal', 'database', 'cloud', 'globe', 'law',
  'pulse', 'shield', 'wand', 'sparkle', 'note', 'piano',
]

let storageApi = null

function loadMap(key) {
  try {
    const raw = storageApi ? storageApi.get(key, {}) : {}
    return raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {}
  } catch {
    return {}
  }
}

function saveMap(key, next) {
  try {
    if (storageApi) storageApi.set(key, next)
  } catch {
    /* storage unavailable: change stays session-local */
  }
}

function getColor(sid) {
  return loadMap('colors')[sid] || null
}

function setColor(sid, hex) {
  const colors = loadMap('colors')
  if (hex) colors[sid] = hex
  else delete colors[sid]
  saveMap('colors', colors)
  try {
    host.sessions.setColor(sid, hex)
  } catch {
    /* app store write is best-effort */
  }
}

function getGlyph(sid) {
  return loadMap('glyphs')[sid] || null
}

function setGlyph(sid, glyph) {
  const glyphs = loadMap('glyphs')
  if (glyph) glyphs[sid] = glyph
  else delete glyphs[sid]
  saveMap('glyphs', glyphs)
}

function isDark() {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
}

// Memoized lightness flip so a hand-picked color stays readable in both modes.
const adaptCache = new Map()
function adaptColor(color) {
  if (!color) return color
  const key = `${isDark() ? 'd' : 'l'}|${color}`
  if (adaptCache.has(key)) return adaptCache.get(key)
  const box = document.createElement('span')
  box.style.color = color
  document.documentElement.appendChild(box)
  const out = getComputedStyle(box).color
  box.remove()
  const m = out.match(/rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)/)
  let adapted = color
  if (m) {
    const r = +m[1] / 255
    const g = +m[2] / 255
    const b = +m[3] / 255
    const max = Math.max(r, g, b)
    const min = Math.min(r, g, b)
    const l = (max + min) / 2
    const d = max - min
    const s = l > 0.5 && d !== 0 ? d / (2 - max - min) : d === 0 ? 0 : d / (max + min)
    let h = 0
    if (d !== 0) {
      if (max === r) h = ((g - b) / d + (g < b ? 6 : 0)) * 60
      else if (max === g) h = ((b - r) / d + 2) * 60
      else h = ((r - g) / d + 4) * 60
    }
    const nextL = isDark() ? Math.max(62, Math.min(78, l * 100 + 12)) : Math.min(42, Math.max(28, l * 100 - 14))
    adapted = s < 0.04
      ? (isDark() ? 'hsl(0 0% 82%)' : 'hsl(0 0% 28%)')
      : `hsl(${Math.round(h)} ${Math.round(s * 100)}% ${Math.round(nextL)}%)`
  }
  adaptCache.set(key, adapted)
  return adapted
}

function ColorPopover({ sid, anchor, onClose }) {
  const [pos, setPos] = useState(null)
  const panelRef = useRef(null)

  useEffect(() => {
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    const width = 232
    const flip = r.right + 8 + width > window.innerWidth - 8
    setPos({
      top: Math.min(r.bottom + 6, window.innerHeight - 200),
      left: flip ? Math.max(8, r.right - width) : r.left,
      width,
    })
  }, [anchor])

  useEffect(() => {
    const onDown = event => {
      if (panelRef.current && !panelRef.current.contains(event.target)) onClose()
    }
    const onKey = event => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown, true)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown, true)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [onClose])

  if (!pos) return null

  const current = getColor(sid)

  return jsx('div', {
    ref: panelRef,
    style: {
      position: 'fixed',
      zIndex: 9999,
      top: `${pos.top}px`,
      left: `${pos.left}px`,
      width: `${pos.width}px`,
      padding: '0.5rem',
      border: '1px solid var(--ui-stroke-secondary, var(--ui-border))',
      borderRadius: '0.5rem',
      background: 'var(--ui-bg-elevated, var(--background))',
      boxShadow: 'var(--shadow-md, 0 8px 24px rgb(0 0 0 / 0.24))',
    },
    onClick: e => e.stopPropagation(),
    children: jsxs('div', {
      style: { display: 'flex', flexDirection: 'column', gap: '0.4rem' },
      children: [
        jsx(ColorSwatches, {
          swatches: PROFILE_SWATCHES,
          value: current,
          onChange: hex => {
            setColor(sid, hex)
          },
        }),
        jsxs('div', {
          style: { display: 'flex', alignItems: 'center', gap: '0.35rem' },
          children: [
            jsx('input', {
              type: 'color',
              value: /^#[0-9a-f]{6}$/i.test(current || '') ? current : '#5b8def',
              onChange: e => setColor(sid, e.target.value),
              style: {
                width: '1.6rem',
                height: '1.4rem',
                padding: 0,
                border: '1px solid var(--ui-stroke-secondary, var(--ui-border))',
                borderRadius: '0.3rem',
                background: 'transparent',
              },
              'aria-label': 'Custom color',
            }),
            jsx('span', { style: { flex: 1, fontSize: '0.7rem', color: 'var(--ui-text-tertiary)' }, children: 'Custom' }),
            jsx(Button, {
              variant: 'ghost',
              size: 'sm',
              type: 'button',
              onClick: () => setColor(sid, null),
              children: 'Clear',
            }),
          ],
        }),
      ],
    }),
  })
}

function ColorDot({ sessionId }) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef(null)
  const color = getColor(sessionId)

  return jsxs('span', {
    children: [
      jsx('button', {
        ref: btnRef,
        type: 'button',
        title: color ? 'Session color' : 'Set session color',
        'aria-label': 'Session color',
        onClick: e => {
          e.preventDefault()
          e.stopPropagation()
          setOpen(v => !v)
        },
        style: {
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '0.875rem',
          height: '0.875rem',
          padding: 0,
          border: color
            ? '1px solid color-mix(in srgb, var(--ui-accent) 45%, transparent)'
            : '1px dashed var(--ui-stroke-secondary, var(--ui-border))',
          borderRadius: '99px',
          background: color || 'transparent',
          color: color ? adaptColor(color) : 'var(--ui-text-quaternary)',
          cursor: 'pointer',
          opacity: color ? 1 : 0.55,
        },
        children: color ? null : jsx('i', { className: 'codicon codicon-symbol-color', style: { fontSize: '0.55rem' } }),
      }),
      open
        ? jsx(ColorPopover, {
            sid: sessionId,
            anchor: btnRef.current,
            onClose: () => setOpen(false),
          })
        : null,
    ],
  })
}

function GlyphPicker({ sid, anchor, onClose }) {
  const [pos, setPos] = useState(null)
  const panelRef = useRef(null)

  useEffect(() => {
    if (!anchor) return
    const r = anchor.getBoundingClientRect()
    const width = 208
    setPos({
      top: Math.min(r.bottom + 6, window.innerHeight - 260),
      left: r.left - width < 8 ? 8 : r.left - width,
      width,
    })
  }, [anchor])

  useEffect(() => {
    const onDown = event => {
      if (panelRef.current && !panelRef.current.contains(event.target)) onClose()
    }
    const onKey = event => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', onDown, true)
    document.addEventListener('keydown', onKey, true)
    return () => {
      document.removeEventListener('mousedown', onDown, true)
      document.removeEventListener('keydown', onKey, true)
    }
  }, [onClose])

  if (!pos) return null

  const current = getGlyph(sid)

  return jsx('div', {
    ref: panelRef,
    style: {
      position: 'fixed',
      zIndex: 9999,
      top: `${pos.top}px`,
      left: `${pos.left}px`,
      width: `${pos.width}px`,
      padding: '0.5rem',
      border: '1px solid var(--ui-stroke-secondary, var(--ui-border))',
      borderRadius: '0.5rem',
      background: 'var(--ui-bg-elevated, var(--background))',
      boxShadow: 'var(--shadow-md, 0 8px 24px rgb(0 0 0 / 0.24))',
    },
    onClick: e => e.stopPropagation(),
    children: jsxs('div', {
      style: { display: 'flex', flexDirection: 'column', gap: '0.4rem' },
      children: [
        jsx('div', {
          style: { fontSize: '0.7rem', fontWeight: 600, color: 'var(--ui-text-secondary)' },
          children: 'Idle glyph',
        }),
        jsx('div', {
          style: { display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '0.25rem' },
          children: jsx('button', {
            type: 'button',
            title: 'Default dot',
            'aria-label': 'Default dot',
            onClick: () => {
              setGlyph(sid, null)
              onClose()
            },
            style: {
              display: 'grid',
              placeItems: 'center',
              aspectRatio: '1',
              border: 0,
              borderRadius: '0.3rem',
              padding: 0,
              background: current ? 'transparent' : 'var(--ui-control-active-background)',
              color: 'var(--ui-text-tertiary)',
              cursor: 'pointer',
            },
            children: jsx('i', { className: 'codicon codicon-circle-slash', style: { fontSize: '0.7rem' } }),
          }),
        }),
        jsx('div', {
          style: { display: 'grid', gridTemplateColumns: 'repeat(8, 1fr)', gap: '0.25rem' },
          children: GLYPHS.map(name =>
            jsx('button', {
              key: name,
              type: 'button',
              title: name,
              'aria-label': name,
              onClick: () => {
                setGlyph(sid, name)
                onClose()
              },
              style: {
                display: 'grid',
                placeItems: 'center',
                aspectRatio: '1',
                border: 0,
                borderRadius: '0.3rem',
                padding: 0,
                background: current === name ? 'var(--ui-control-active-background)' : 'transparent',
                color: 'var(--ui-text-tertiary)',
                cursor: 'pointer',
              },
              children: jsx('i', { className: `codicon codicon-${name}`, style: { fontSize: '0.7rem' } }),
            })
          ),
        }),
      ],
    }),
  })
}

function GlyphButton({ sessionId }) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef(null)
  const glyph = getGlyph(sessionId)
  const color = getColor(sessionId)

  return jsxs('span', {
    children: [
      jsx('button', {
        ref: btnRef,
        type: 'button',
        title: 'Session idle glyph',
        'aria-label': 'Session idle glyph',
        onClick: e => {
          e.preventDefault()
          e.stopPropagation()
          setOpen(v => !v)
        },
        style: {
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '0.9rem',
          height: '0.9rem',
          padding: 0,
          border: 0,
          borderRadius: '0.2rem',
          background: 'transparent',
          color: glyph ? adaptColor(color || 'var(--ui-text-tertiary)') : 'var(--ui-text-quaternary)',
          cursor: 'pointer',
          opacity: glyph ? 1 : 0.5,
        },
        children: jsx('i', {
          className: `codicon codicon-${glyph || 'circle-filled'}`,
          style: { fontSize: '0.65rem' },
        }),
      }),
      open
        ? jsx(GlyphPicker, {
            sid: sessionId,
            anchor: btnRef.current,
            onClose: () => setOpen(false),
          })
        : null,
    ],
  })
}

export default {
  id: ID,
  name: 'Better Session Appearance',
  description:
    'Per-session color and idle glyph in the session list, through the SDK row slots and host.sessions.setColor.',
  defaultEnabled: false,
  register(ctx) {
    storageApi = ctx.storage

    ctx.register({
      id: 'glyph',
      area: SESSION_ROW_AREAS.leading,
      data: {
        render: ({ sessionId }) => jsx(GlyphButton, { sessionId }),
      },
    })

    ctx.register({
      id: 'color-dot',
      area: SESSION_ROW_AREAS.trailing,
      data: {
        render: ({ sessionId }) => jsx(ColorDot, { sessionId }),
      },
    })

    ctx.onDispose(() => {
      storageApi = null
    })
  },
}
