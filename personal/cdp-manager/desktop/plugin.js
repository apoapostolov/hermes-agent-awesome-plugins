/**
 * CDP Manager - statusbar chip + dialog + Python backend for local Chrome
 * DevTools Protocol ports (default 9222, 9333, 9335; editable in dialog).
 *
 * Statusbar chip reflects live health, polled every 5s from /health:
 *   normal  CDP down        ·  bold  CDP up
 *   amber   CDP has issues  ·  red   critical, needs a reboot
 *
 * The checkmarked port is the MANAGED port. A backend supervisor thread
 * (started with the plugin API on Hermes launch) checks every port's health
 * regularly, starts the managed port whenever it is down, and force-reboots
 * it (stop + launch) after repeated failed launches.
 *
 * Per-port glyph buttons: launch / stop (state-aware, one at a time) and
 * recheck. Segmented Auto-refresh selector (Manual/2s/5s/10s/30s) while the
 * dialog is open. The github glyph before the footer hint opens the repo.
 */
import {
  cn,
  Codicon,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Button,
  Input,
  Tip as Tooltip,
  STATUSBAR_AREAS,
} from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useRef, useState } from 'react'

// ── backend door ──

let _rest = null // injected at register(ctx) — ctx.rest hits /api/plugins/cdp-manager
let _openExternal = null // ctx.os.openExternal: target=_blank window.open is denied in-app

const REPO_URL = 'https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/personal/cdp-manager'
const GLYPH_BTN = 'inline-flex size-6 shrink-0 items-center justify-center rounded-md border text-(--ui-text-secondary) hover:text-foreground hover:bg-(--chrome-action-hover)'
const GLYPH_SIZE = '0.85rem'

async function api(path, body) {
  if (!_rest) throw new Error('backend not ready')
  if (body === undefined) return _rest(path)
  return _rest(path, { method: 'POST', body })
}

// Glyph button with a working tooltip. Codicon glyphs are FONT glyphs: the
// app CSS forces .codicon{font-size:.875em}, so size the inner glyph, not the
// button, or the icon shrinks to nothing.
function GlyphButton({ glyph, label, onClick, busy, danger }) {
  return jsx(Tooltip, {
    label,
    children: jsx('button', {
      type: 'button',
      onClick: e => {
        e.preventDefault()
        if (!busy) onClick()
      },
      className: cn(GLYPH_BTN, danger && 'hover:text-red-400'),
      style: { opacity: busy ? 0.5 : 1 },
      'data-cdp-glyph': glyph,
      children: jsx(Codicon, { name: glyph, size: GLYPH_SIZE }),
    }),
  })
}

// Segmented selector, same shape as the RSS Reader ticker speed control:
// inline group of small buttons, aria-pressed marks the active segment.
function Segmented({ value, onChange, options }) {
  return jsx('span', {
    className: 'cdp-segmented',
    role: 'group',
    style: {
      display: 'inline-flex',
      gap: '2px',
      border: '1px solid var(--ui-stroke-secondary)',
      borderRadius: '7px',
      padding: '2px',
    },
    children: options.map(o =>
      jsx(
        'button',
        {
          type: 'button',
          'aria-pressed': String(o.id) === String(value),
          onClick: () => onChange(o.id),
          style: {
            background: String(o.id) === String(value)
              ? 'color-mix(in srgb, var(--ui-accent) 16%, transparent)'
              : 'none',
            border: '0',
            padding: '3px 9px',
            font: 'inherit',
            fontSize: '11px',
            color: String(o.id) === String(value) ? 'var(--ui-accent)' : 'var(--ui-text-secondary)',
            fontWeight: String(o.id) === String(value) ? 650 : 400,
            cursor: 'pointer',
            borderRadius: '5px',
          },
          children: o.label,
        },
        o.id,
      ),
    ),
  })
}

// ── port row ──

function PortRow({ port, result, preferred, mode, onAction, onPrefer, onMode, onCopy }) {
  const live = result?.state === 'live'
  const dead = result?.state === 'dead'
  const [busy, setBusy] = useState(null) // 'launch' | 'stop' | 'probe' | null

  const run = async kind => {
    setBusy(kind)
    try {
      await onAction(kind, port)
    } finally {
      setBusy(null)
    }
  }

  // Show launch OR stop depending on confirmed state: a live port gets stop,
  // a dead port gets launch. While an action runs the button reflects the
  // state being reached, so it never flickers.
  const confirming = busy === 'launch' || busy === 'stop'
  const showStop = busy === 'stop' || (live && busy !== 'launch')

  return jsxs('div', {
    'data-cdp-row': String(port),
    className: cn(
      'flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs',
      dead && result && 'opacity-60',
      preferred && 'border-(--ui-accent)',
    ),
    style: { border: preferred ? '1px solid var(--ui-accent)' : '1px solid var(--ui-stroke-secondary)' },
    children: [
      // state dot
      jsx('span', {
        className: 'inline-block size-2 shrink-0 rounded-full',
        style: {
          background: !result
            ? 'var(--ui-text-quaternary)'
            : live
              ? '#22c55e'
              : 'color-mix(in srgb, var(--ui-text-quaternary) 60%, transparent)',
        },
      }),
      // managed checkmark (wire name stays preferredPort for the tool API)
      jsx(Tooltip, {
        label: preferred
          ? `Port ${port} is managed · Hermes starts it when down · click to unmanage`
          : `Manage port ${port}: Hermes keeps it up`,
        children: jsx('button', {
          type: 'button',
          'data-cdp-prefer': String(port),
          onClick: () => onPrefer(preferred ? 0 : port),
          className: cn(
            'inline-flex size-5 shrink-0 cursor-pointer items-center justify-center rounded',
            preferred ? 'text-(--ui-accent)' : 'text-(--ui-text-quaternary) hover:text-(--ui-text-secondary)',
          ),
          children: jsx(Codicon, {
            name: preferred ? 'pass-filled' : 'pass',
            size: '0.9rem',
          }),
        }),
      }),
      jsx('span', {
        className: 'w-12 shrink-0 font-medium tabular-nums',
        children: String(port),
      }),
      jsx('span', {
        className: 'min-w-0 flex-1 truncate',
        style: { color: 'var(--ui-text-secondary)' },
        children: !result
          ? 'checking…'
          : live
            ? `${result.browser}${result.pid ? ` · pid ${result.pid}` : ''}${result.ms != null ? ` · ${result.ms}ms` : ''}`
            : `no listener${result.reason && result.reason !== 'no listener' ? ` (${result.reason})` : ''}`,
      }),
      live && result.ws
        ? jsx(Tooltip, {
            label: 'Copy http URL',
            children: jsx('button', {
              type: 'button',
              onClick: () => onCopy(`http://127.0.0.1:${port}`, 'URL'),
              className: GLYPH_BTN,
              children: jsx(Codicon, { name: 'link', size: GLYPH_SIZE }),
            }),
          })
        : null,
      live && result.ws
        ? jsx(Tooltip, {
            label: 'Copy WebSocket URL',
            children: jsx('button', {
              type: 'button',
              onClick: () => onCopy(result.ws, 'WebSocket URL'),
              className: GLYPH_BTN,
              children: jsx(Codicon, { name: 'clippy', size: GLYPH_SIZE }),
            }),
          })
        : null,
      // launch OR stop, by confirmed state (consts computed above)
      confirming || result
        ? jsx(GlyphButton, {
            glyph: showStop ? 'stop' : 'play',
            label: showStop ? `Stop the listener on port ${port}` : `Launch Chrome on port ${port}${mode === 'headless' ? ' (headless)' : ''}`,
            busy: confirming,
            danger: showStop,
            onClick: () => run(showStop ? 'stop' : 'launch'),
          })
        : null,
      // headless / headful mode dropdown (custom, themed; native selects are OS-drawn)
      jsx(Tooltip, {
        label: `Launch mode for port ${port}: ${mode === 'headless' ? 'headless (no window)' : 'headful (window)'} · applied on next launch`,
        children: jsxs('select', {
          'data-cdp-mode': String(port),
          value: mode || 'headful',
          onChange: e => onMode(port, e.target.value),
          className: 'h-6 shrink-0 cursor-pointer rounded-md border px-1 text-[0.65rem]',
          style: {
            background: 'transparent',
            color: 'var(--ui-text-secondary)',
            borderColor: 'var(--ui-stroke-secondary)',
          },
          children: [
            jsx('option', { value: 'headful', children: 'Headful' }, 'headful'),
            jsx('option', { value: 'headless', children: 'Headless' }, 'headless'),
          ],
        }),
      }),
      jsx(GlyphButton, {
        glyph: 'refresh',
        label: `Recheck port ${port}`,
        busy: busy === 'probe',
        onClick: () => run('probe'),
      }),
    ],
  })
}

// ── dialog ──

function PanelDialog({ open, onOpenChange, cfg, setCfg, onNotify }) {
  const [results, setResults] = useState({})
  const [busy, setBusy] = useState(false)
  const [portsDraft, setPortsDraft] = useState('')
  const abortRef = useRef(null)
  const busyRef = useRef(false)
  const actionLockRef = useRef(false)
  const sweepRef = useRef(null) // set below; the poll timer calls through it
  busyRef.current = busy

  // One probe sweep per open + manual Refresh; probes only while open.
  useEffect(() => {
    if (!open) return undefined
    let alive = true
    const controller = new AbortController()
    abortRef.current = controller
    setPortsDraft(cfg.ports.join(', '))
    setResults({})
    setBusy(true)
    ;(async () => {
      try {
        const r = await api('/status')
        if (!alive) return
        const next = {}
        for (const res of r?.results || []) next[res.port] = res
        setResults(next)
      } catch {
        if (alive) onNotify('backend unreachable')
      } finally {
        if (alive) setBusy(false)
      }
    })()
    return () => {
      alive = false
      controller.abort()
      abortRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Auto-refresh while the dialog is open, at the chosen interval. Interval 0
  // (= Manual) disables the timer. Live timer turns off after a launch/stop
  // action until the sweep confirms the new state, so the button never
  // flips back mid-confirmation. Declared BEFORE the early return: a hook
  // after `if (!open) return null` changes the hook count on open and kills
  // the render with React error #310.
  useEffect(() => {
    if (!open) return undefined
    if (!cfg.pollSeconds) return undefined
    const id = setInterval(() => {
      if (!busyRef.current && !actionLockRef.current) sweepRef.current(cfg.ports)
    }, cfg.pollSeconds * 1000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, cfg.pollSeconds, cfg.ports.join(',')])

  if (!open) return null

  const sweep = async ports => {
    setBusy(true)
    try {
      const r = await api('/probe', { ports })
      const next = {}
      for (const res of r?.results || []) next[res.port] = res
      setResults(next)
    } catch {
      onNotify('probe failed')
    } finally {
      setBusy(false)
    }
  }

  const refresh = () => sweep(cfg.ports)
  sweepRef.current = sweep

  // Per-port action from the glyph buttons. launch/stop hold an action lock
  // so the auto-refresh timer cannot re-probe mid-confirmation and flip the
  // button while Chrome is still settling.
  const act = async (kind, port) => {
    try {
      if (kind === 'probe') {
        const r = await api('/probe', { ports: [port] })
        const res = r?.results?.[0]
        if (res) setResults(prev => ({ ...prev, [port]: res }))
        return
      }
      actionLockRef.current = true
      const mode = cfg?.modes?.[port]
      const r = await api(`/${kind}`, { port, ...(kind === 'launch' && mode ? { mode } : {}) })
      if (r?.error) {
        onNotify(`${kind} failed: ${r.error}`)
        return
      }
      onNotify(kind === 'launch' ? (r.already ? `port ${port} already live` : `port ${port} launched (${r.mode || mode || 'headful'})`) : (r.already ? `port ${port} was not live` : `port ${port} stopped`))
      await sweep(cfg.ports)
    } catch {
      onNotify(`${kind} failed`)
    } finally {
      actionLockRef.current = false
    }
  }

  const prefer = async port => {
    try {
      const r = await api('/preferred', { port: port || null })
      if (r?.ok) {
        setCfg({ preferredPort: r.preferredPort })
        onNotify(port ? `port ${port} is now managed` : 'port no longer managed')
      }
    } catch {
      onNotify('save failed')
    }
  }

  const setMode = (port, mode) => {
    setCfg(prev => ({ ...prev, modes: { ...prev.modes, [port]: mode } }))
    api('/mode', { port, mode }).catch(() => onNotify('mode save failed'))
  }

  const savePorts = () => {
    const parsed = [
      ...new Set(
        portsDraft
          .split(/[,\s]+/)
          .map(s => Number.parseInt(s, 10))
          .filter(n => Number.isInteger(n) && n > 0 && n < 65536),
      ),
    ]
    const next = { ...cfg, ports: parsed.length ? parsed : [...cfg.ports] }
    setCfg(next)
    setPortsDraft(next.ports.join(', '))
    if (parsed.length) api('/ports', { ports: parsed }).catch(() => {})
  }

  const liveCount = cfg.ports.filter(p => results[p]?.state === 'live').length

  // Poll interval segmented selector, RSS Reader ticker style. Values are
  // seconds; 0 = manual (no auto-refresh while the dialog is open).
  const pollOptions = [
    { id: '0', label: 'Manual' },
    { id: '2', label: '2s' },
    { id: '5', label: '5s' },
    { id: '10', label: '10s' },
    { id: '30', label: '30s' },
  ]
  const setPoll = v => {
    const seconds = Number(v)
    setCfg({ pollSeconds: seconds })
    api('/poll', { seconds }).catch(() => {})
  }

  return jsxs(Dialog, {
    open,
    onOpenChange,
    children: [
      jsx(DialogContent, {
        fitContent: true,
        className: 'min-w-[30rem] rounded-xl border-(--ui-accent)',
        bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
        'data-context-menu-skip': '',
        children: jsxs(Fragment, {
          children: [
            jsx(DialogHeader, {
              className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2',
              children: jsx(DialogTitle, { children: 'CDP Manager' }),
            }),
            jsx('p', {
              className: 'text-xs text-(--ui-text-tertiary)',
              children: 'Probes 127.0.0.1 ports on /json/version while this dialog is open.',
            }),
            jsxs('div', {
              className: 'flex flex-col gap-2',
              children: cfg.ports.map(p =>
                jsx(
                  PortRow,
                  {
                    port: p,
                    result: results[p],
                    preferred: cfg.preferredPort === p,
                    mode: cfg?.modes?.[p],
                    onAction: act,
                    onPrefer: prefer,
                    onMode: setMode,
                    onCopy: (text, label) => {
                      navigator.clipboard.writeText(text).then(
                        () => onNotify(`${label} copied`),
                        () => onNotify('copy failed'),
                      )
                    },
                  },
                  p,
                ),
              ),
            }),
            jsxs('div', {
              'data-cdp-config': '',
              className: 'flex flex-col gap-2 rounded-md px-2 py-1.5',
              style: { border: '1px solid var(--ui-stroke-secondary)' },
              children: [
                jsx('span', {
                  className: 'text-xs',
                  style: { color: 'var(--ui-text-secondary)' },
                  children: 'Ports to probe',
                }),
                jsx(Input, {
                  'data-cdp-ports-input': '',
                  value: portsDraft,
                  onChange: e => setPortsDraft(e.target.value),
                  onBlur: savePorts,
                  placeholder: '9222, 9333, 9335',
                  className: 'h-7 rounded-md border px-2 text-xs',
                  style: { background: 'transparent' },
                }),
                jsx('span', {
                  className: 'text-[0.65rem] text-(--ui-text-quaternary)',
                  children: 'Comma or space separated. Saved when the field loses focus.',
                }),
              ],
            }),
            jsxs('div', {
              className: 'flex items-center justify-between gap-3 rounded-md px-2 py-1.5',
              style: { border: '1px solid var(--ui-stroke-secondary)' },
              children: [
                jsx('span', {
                  className: 'text-xs shrink-0',
                  style: { color: 'var(--ui-text-secondary)' },
                  children: 'Auto-refresh',
                }),
                jsx(Segmented, {
                  value: String(cfg.pollSeconds ?? 5),
                  onChange: setPoll,
                  options: pollOptions,
                }),
              ],
            }),
            jsxs('div', {
              className: 'flex items-center justify-between pt-1',
              children: [
                jsxs('span', {
                  className: 'flex items-center gap-1.5 text-[0.65rem] text-(--ui-text-quaternary) tabular-nums',
                  children: [
                    jsx('a', {
                      href: REPO_URL,
                      target: '_blank',
                      rel: 'noreferrer',
                      onClick: e => {
                        e.preventDefault()
                        _openExternal?.(REPO_URL)
                      },
                      className: 'inline-flex items-center text-(--ui-text-quaternary) hover:text-(--ui-text-tertiary)',
                      children: jsx(Codicon, { name: 'github', size: '0.75rem' }),
                    }),
                    busy ? 'probing…' : `${liveCount} of ${cfg.ports.length} live`,
                  ],
                }),
                jsx(Button, { size: 'sm', variant: 'outline', onClick: refresh, children: 'Refresh' }),
              ],
            }),
          ],
        }),
      }),
    ],
  })
}

// ── chip health states ──
// normal = cdp down · bold+normal = up · amber = issues · red = critical
const CHIP_COLORS = {
  down: 'var(--ui-text-tertiary)',
  ok: 'var(--foreground)',
  warn: '#f59e0b',
  critical: '#ef4444',
}
function chipStyle(health, bold) {
  return {
    color: CHIP_COLORS[health] || CHIP_COLORS.down,
    fontWeight: health === 'ok' || bold ? 700 : 400,
  }
}

// ── root ──

function Root() {
  const [cfg, setCfg] = useState(() => ({ ports: [9222, 9333, 9335], preferredPort: null, pollSeconds: 5 }))
  const [dialogOpen, setDialogOpen] = useState(false)
  const [ready, setReady] = useState(false)
  const [note, setNote] = useState('')
  const [healthState, setHealthState] = useState({ health: 'down', reason: null })
  const noteTimer = useRef(null)

  // Hydrate config from the backend once mounted; the backend owns config.json
  // so the dialog and the `cdp` agent tool share one source of truth.
  useEffect(() => {
    api('/status')
      .then(r => {
        if (!r) return
        setCfg({ ports: r.ports, preferredPort: r.preferredPort, pollSeconds: r.pollSeconds, modes: r.modes || {} })
        setReady(true)
      })
      .catch(() => setReady(true))
  }, [])

  // Chip health: cheap cached /health poll every 5s, for the whole app
  // lifetime (the backend supervisor does the actual port work; this only
  // colors the glyph). Runs even while the dialog is closed.
  useEffect(() => {
    let alive = true
    const tick = () => {
      api('/health')
        .then(r => {
          if (alive && r) setHealthState({ health: r.health, reason: r.reason })
        })
        .catch(() => {})
    }
    tick()
    const id = setInterval(tick, 5000)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [])

  // Transient action confirmation, in-dialog only.
  const notify = msg => {
    setNote(msg)
    if (noteTimer.current) clearTimeout(noteTimer.current)
    noteTimer.current = setTimeout(() => setNote(''), 1800)
  }
  useEffect(
    () => () => {
      if (noteTimer.current) clearTimeout(noteTimer.current)
    },
    [],
  )

  const healthLabel = {
    down: 'CDP down',
    ok: 'CDP up',
    warn: `CDP issues${healthState.reason ? `: ${healthState.reason}` : ''}`,
    critical: `CDP CRITICAL${healthState.reason ? `: ${healthState.reason}` : ''}`,
  }[healthState.health] || 'CDP Manager'

  return jsxs(Fragment, {
    children: [
      jsx(Tooltip, {
        label: `${healthLabel} · manage debug ports`,
        children: jsx('span', {
          title: 'CDP Manager',
          onClick: () => setDialogOpen(true),
          className:
            'inline-flex h-full cursor-pointer items-center px-1.5 hover:bg-(--chrome-action-hover)',
          style: chipStyle(healthState.health, ready && healthState.health === 'ok'),
          children: jsx(Codicon, { name: 'plug', size: '0.7rem' }),
        }),
      }),
      jsx(PanelDialog, {
        open: dialogOpen,
        onOpenChange: setDialogOpen,
        cfg,
        setCfg: next => setCfg(prev => ({ ...prev, ...next })),
        onNotify: notify,
      }),
    ],
  })
}

export default {
  id: 'cdp-manager',
  name: 'CDP Manager',
  description: 'Statusbar dialog + `cdp` agent tool for local Chrome CDP ports: probe, launch, stop, managed port with auto-start and reboot, health at a glance.',

  register(ctx) {
    _rest = ctx.rest // plugin-scoped REST door to /api/plugins/cdp-manager (auth handled)
    _openExternal = ctx.os?.openExternal ?? null

    // Native <select> popups are OS-drawn: pin color-scheme to the app's
    // resolved mode or a dark app on a light OS renders a white popup.
    const STYLE_ID = 'cdp-manager-select-theme'
    const style = document.createElement('style')
    style.id = STYLE_ID
    style.textContent = `
      select[data-cdp-mode] { color-scheme: light dark; }
      html[data-hermes-mode='dark'] select[data-cdp-mode],
      html.dark select[data-cdp-mode] { color-scheme: dark; }
      html[data-hermes-mode='light'] select[data-cdp-mode] { color-scheme: light; }
      select[data-cdp-mode] option { background: var(--ui-bg-elevated, var(--ui-bg-secondary)); color: var(--ui-text-primary, var(--foreground)); }
    `
    document.head.appendChild(style)
    ctx.onDispose?.(() => document.getElementById(STYLE_ID)?.remove())

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 121,
      render: () => jsx(Root, {}),
    })
  },
}
