/**
 * CDP Manager - statusbar gear + dialog + Python backend for local Chrome
 * DevTools Protocol ports (default 9222, 9333, 9335; editable in dialog).
 *
 * While the dialog is open each port is probed against /json/version via the
 * backend at /api/plugins/cdp-manager/. Per-port glyph buttons:
 *   play   launch Chrome on that port (backend spawn, no visible terminal)
 *   stop   close the listener cleanly (Browser.close over its WS)
 *   refresh  re-probe that port
 *   pass-filled checkmark marks the port preferred (the `cdp` agent tool and
 *   launch/stop default to it); one preferred port at a time.
 *
 * The github glyph before the footer hint opens the plugin's repo.
 * Nothing probes while the dialog is closed: no background polling.
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

// ── port row ──

function PortRow({ port, result, preferred, onAction, onPrefer, onCopy }) {
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
      // preferred checkmark
      jsx(Tooltip, {
        label: preferred
          ? `Port ${port} is the preferred default \\u00b7 click to clear`
          : `Mark port ${port} as preferred default`,
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
          ? 'checking\\u2026'
          : live
            ? `${result.browser}${result.pid ? ` \\u00b7 pid ${result.pid}` : ''}${result.ms != null ? ` \\u00b7 ${result.ms}ms` : ''}`
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
      jsx(GlyphButton, {
        glyph: 'play',
        label: `Launch Chrome on port ${port}`,
        busy: busy === 'launch',
        onClick: () => run('launch'),
      }),
      jsx(GlyphButton, {
        glyph: 'stop',
        label: `Stop the listener on port ${port}`,
        busy: busy === 'stop',
        danger: true,
        onClick: () => run('stop'),
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

  // Per-port action from the glyph buttons.
  const act = async (kind, port) => {
    try {
      if (kind === 'probe') {
        const r = await api('/probe', { ports: [port] })
        const res = r?.results?.[0]
        if (res) setResults(prev => ({ ...prev, [port]: res }))
        return
      }
      const r = await api(`/${kind}`, { port })
      if (r?.error) {
        onNotify(`${kind} failed: ${r.error}`)
        return
      }
      onNotify(kind === 'launch' ? (r.already ? `port ${port} already live` : `port ${port} launched`) : (r.already ? `port ${port} was not live` : `port ${port} stopped`))
      await sweep(cfg.ports)
    } catch {
      onNotify(`${kind} failed`)
    }
  }

  const prefer = async port => {
    try {
      const r = await api('/preferred', { port: port || null })
      if (r?.ok) {
        setCfg({ preferredPort: r.preferredPort })
        onNotify(port ? `port ${port} is now the preferred default` : 'preferred port cleared')
      }
    } catch {
      onNotify('save failed')
    }
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
                    onAction: act,
                    onPrefer: prefer,
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
                    busy ? 'probing\\u2026' : `${liveCount} of ${cfg.ports.length} live`,
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

// ── root ──

function Root() {
  const [cfg, setCfg] = useState(() => ({ ports: [9222, 9333, 9335], preferredPort: null }))
  const [dialogOpen, setDialogOpen] = useState(false)
  const [ready, setReady] = useState(false)
  const [note, setNote] = useState('')
  const noteTimer = useRef(null)

  // Hydrate config from the backend once mounted; the backend owns config.json
  // so the dialog and the `cdp` agent tool share one source of truth.
  useEffect(() => {
    api('/status')
      .then(r => {
        if (!r) return
        setCfg({ ports: r.ports, preferredPort: r.preferredPort })
        setReady(true)
      })
      .catch(() => setReady(true))
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

  return jsxs(Fragment, {
    children: [
      jsx(Tooltip, {
        label: 'CDP Manager \\u00b7 which debug port is live',
        children: jsx('span', {
          title: 'CDP Manager',
          onClick: () => setDialogOpen(true),
          className:
            'inline-flex h-full cursor-pointer items-center px-1.5 text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
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
  description: 'Statusbar dialog + `cdp` agent tool for local Chrome CDP ports: probe, launch, stop, preferred default.',

  register(ctx) {
    _rest = ctx.rest // plugin-scoped REST door to /api/plugins/cdp-manager (auth handled)
    _openExternal = ctx.os?.openExternal ?? null

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 121,
      render: () => jsx(Root, {}),
    })
  },
}
