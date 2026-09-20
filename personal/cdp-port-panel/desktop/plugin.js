/**
 * CDP Port Panel - statusbar gear + dialog that probes known local Chrome
 * DevTools Protocol ports (default 9222, 9333, 9335; editable in dialog).
 *
 * While the dialog is open each port is probed against /json/version with a
 * 1s timeout: live ports show browser, pid, WebSocket URL with Test and
 * Copy actions; dead ports show plain "no listener" with a copyable launch
 * command for this box. Nothing probes while the dialog is closed: no
 * background polling, no statusbar noise.
 *
 * Read-only: the plugin never launches Chrome, never kills processes, and
 * never writes outside its own plugin storage.
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

// ── config shape ──
// { ports: number[], chromePath: string, userDataDir: string }

const DEFAULT_PORTS = [9222, 9333, 9335]
const PROBE_TIMEOUT_MS = 1000

function loadConfig(storage) {
  const saved = storage.get('config', null)
  const ports =
    Array.isArray(saved?.ports) && saved.ports.length
      ? saved.ports.map(Number).filter(n => Number.isInteger(n) && n > 0 && n < 65536)
      : [...DEFAULT_PORTS]
  return {
    ports,
    chromePath:
      typeof saved?.chromePath === 'string' && saved.chromePath
        ? saved.chromePath
        : 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    userDataDir:
      typeof saved?.userDataDir === 'string' && saved.userDataDir
        ? saved.userDataDir
        : 'C:/Users/theap/AppData/Local/hermes/chrome-profile',
  }
}

// ── probing ──

async function probePort(port, signal) {
  const t0 = Date.now()
  try {
    const res = await fetch(`http://127.0.0.1:${port}/json/version`, { signal })
    if (!res.ok) return { state: 'dead', reason: `HTTP ${res.status}` }
    const j = await res.json()
    return {
      state: 'live',
      browser: j.Browser || 'unknown browser',
      pid: Number.isFinite(j['Process Id']) ? j['Process Id'] : null,
      ws: j.webSocketDebuggerUrl || null,
      ms: Date.now() - t0,
    }
  } catch (err) {
    if (signal.aborted) return { state: 'dead', reason: 'timeout' }
    return { state: 'dead', reason: 'no listener' }
  }
}

// ── statusbar chip ──

function GearChip({ onOpenDialog }) {
  return jsx(Tooltip, {
    label: 'CDP ports \u00b7 which debug port is live',
    children: jsx('span', {
      title: 'CDP Port Panel',
      onClick: onOpenDialog,
      className:
        'inline-flex h-full cursor-pointer items-center px-1.5 text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground',
      children: jsx(Codicon, { name: 'plug', size: '0.7rem' }),
    }),
  })
}

// ── dialog ──

function PortRow({ port, result, chromePath, userDataDir, onCopy }) {
  const live = result?.state === 'live'
  const dead = result?.state === 'dead'
  const launchCmd = `& "${chromePath}" --remote-debugging-port=${port} --user-data-dir="${userDataDir}"`

  const copy = (text, label) => {
    navigator.clipboard.writeText(text).then(
      () => onCopy(`${label} copied`),
      () => onCopy('copy failed'),
    )
  }

  return jsxs('div', {
    'data-cpp-row': '',
    className: cn(
      'flex items-center gap-2 rounded-md px-2 py-1.5 text-xs',
      dead && result && 'opacity-60',
    ),
    style: { border: '1px solid var(--ui-stroke-secondary)' },
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
      jsx('span', {
        className: 'w-12 shrink-0 font-medium tabular-nums',
        children: String(port),
      }),
      jsx('span', {
        className: 'min-w-0 flex-1 truncate',
        style: { color: 'var(--ui-text-secondary)' },
        children: !result
          ? 'checking\u2026'
          : live
            ? `${result.browser}${result.pid ? ` \u00b7 pid ${result.pid}` : ''}${result.ms != null ? ` \u00b7 ${result.ms}ms` : ''}`
            : `no listener${result.reason && result.reason !== 'no listener' ? ` (${result.reason})` : ''}`,
      }),
      live && result.ws
        ? jsxs(Fragment, {
            children: [
              jsx(Button, {
                size: 'sm',
                variant: 'outline',
                onClick: () => copy(`http://127.0.0.1:${port}`, 'URL'),
                children: 'Copy URL',
              }),
              jsx(Button, {
                size: 'sm',
                variant: 'outline',
                onClick: () => copy(result.ws, 'WebSocket URL'),
                children: 'Copy WS',
              }),
            ],
          })
        : null,
      dead
        ? jsx(Tooltip, {
            label: `${launchCmd} \u00b7 copied as PowerShell, never run for you`,
            children: jsx(Button, {
              size: 'sm',
              variant: 'outline',
              onClick: () => copy(launchCmd, 'Launch command'),
              children: 'Copy launch',
            }),
          })
        : null,
    ],
  })
}

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
      const next = {}
      await Promise.all(
        cfg.ports.map(async p => {
          const r = await probePort(p, controller.signal)
          if (!alive) return
          next[p] = r
          setResults(prev => ({ ...prev, [p]: r }))
        }),
      )
      if (alive) setBusy(false)
    })()
    return () => {
      alive = false
      controller.abort()
      abortRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  if (!open) return null

  const refresh = () => {
    setResults({})
    setBusy(true)
    const controller = new AbortController()
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = controller
    Promise.all(
      cfg.ports.map(async p => {
        const r = await probePort(p, controller.signal)
        setResults(prev => ({ ...prev, [p]: r }))
        return r
      }),
    ).then(() => setBusy(false))
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
    const next = { ...cfg, ports: parsed.length ? parsed : [...DEFAULT_PORTS] }
    setCfg(next)
    setPortsDraft(next.ports.join(', '))
  }

  const liveCount = cfg.ports.filter(p => results[p]?.state === 'live').length

  return jsxs(Dialog, {
    open,
    onOpenChange,
    children: [
      jsx(DialogContent, {
        fitContent: true,
        className: 'min-w-[26rem] rounded-xl border-(--ui-accent)',
        bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
        'data-context-menu-skip': '',
        children: jsxs(Fragment, {
          children: [
            jsx(DialogHeader, {
              className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2',
              children: jsx(DialogTitle, { children: 'CDP Ports' }),
            }),
            jsx('p', {
              className: 'text-xs text-(--ui-text-tertiary)',
              children: 'Probes 127.0.0.1 ports on /json/version while this dialog is open. Read-only: nothing is launched or killed.',
            }),
            jsxs('div', {
              className: 'flex flex-col gap-2',
              children: cfg.ports.map(p =>
                jsx(
                  PortRow,
                  {
                    port: p,
                    result: results[p],
                    chromePath: cfg.chromePath,
                    userDataDir: cfg.userDataDir,
                    onCopy: msg => onNotify(msg),
                  },
                  p,
                ),
              ),
            }),
            jsxs('div', {
              'data-cpp-config': '',
              className: 'flex flex-col gap-2 rounded-md px-2 py-1.5',
              style: { border: '1px solid var(--ui-stroke-secondary)' },
              children: [
                jsx('span', {
                  className: 'text-xs',
                  style: { color: 'var(--ui-text-secondary)' },
                  children: 'Ports to probe',
                }),
                jsx(Input, {
                  'data-cpp-ports-input': '',
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
                jsx('span', {
                  className: 'text-[0.65rem] text-(--ui-text-quaternary) tabular-nums',
                  children: busy
                    ? 'probing\u2026'
                    : `${liveCount} of ${cfg.ports.length} live`,
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
  const [cfg, setCfg] = useState(() => loadConfig(_storage))
  const [dialogOpen, setDialogOpen] = useState(false)
  const cfgRef = useRef(cfg)
  cfgRef.current = cfg
  const [note, setNote] = useState('')
  const noteTimer = useRef(null)

  useEffect(() => {
    _storage.set('config', cfg)
  }, [cfg])

  // Transient copy confirmation, in-dialog only.
  const notify = msg => {
    setNote(msg)
    if (noteTimer.current) clearTimeout(noteTimer.current)
    noteTimer.current = setTimeout(() => setNote(''), 1600)
  }
  useEffect(
    () => () => {
      if (noteTimer.current) clearTimeout(noteTimer.current)
    },
    [],
  )

  return jsxs(Fragment, {
    children: [
      jsx(GearChip, { onOpenDialog: () => setDialogOpen(true) }),
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

let _storage = null

export default {
  id: 'cdp-port-panel',
  name: 'CDP Port Panel',
  description: 'Statusbar dialog that shows which local Chrome CDP port is live, with copyable URLs and launch commands.',

  register(ctx) {
    _storage = ctx.storage

    ctx.register({
      id: 'chip',
      area: STATUSBAR_AREAS.right,
      order: 121,
      render: () => jsx(Root, {}),
    })
  },
}
