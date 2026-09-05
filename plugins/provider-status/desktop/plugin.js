/**
 * Provider Status — unified multi-provider statusbar plugin.
 * Registers statusbar bars per enabled provider + gear glyph for setup.
 * Uses ctx.rest() to hit the Python backend at /api/plugins/provider-status/.
 */
import {
  cn, Codicon, Dialog, DialogContent, DialogHeader, DialogTitle, Button, Checkbox, Input, Tip as Tooltip, StatusDot,
  STATUSBAR_AREAS, queryClient, useQuery,
} from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import * as React from 'react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'

const _PS_BUILD = 'v12-delete-race'
const STALE_MS = 0 // always refetch on mount — cheap endpoint
const MANUAL_REFRESH_MS = 60_000 // min spacing between click-triggered refetches

// Clicking a chip refetches THAT provider only. Rate-limit is per pid so
// clicking GLM does not block Codex. Gear spins while any chip refresh flies.
const _lastManualRefresh = {}
const _inflightRefresh = new Set()
const REFRESHING_KEY = ['provider-status-refreshing']

// Live Glass setting: html[data-hermes-glass] is set by Appearance → Window
// Translucency. MutationObserver so flipping Glass while a dialog is open
// restyles it without a close/reopen.
function useGlassOn() {
  const [on, setOn] = useState(() =>
    typeof document !== 'undefined' && document.documentElement.hasAttribute('data-hermes-glass'))
  useEffect(() => {
    const el = document.documentElement
    const mo = new MutationObserver(() => setOn(el.hasAttribute('data-hermes-glass')))
    mo.observe(el, { attributes: true, attributeFilter: ['data-hermes-glass'] })
    return () => mo.disconnect()
  }, [])
  return on
}

// FLIP: when row order changes, slide neighbors into their new slots.
function useFlipList(dep) {
  const ref = useRef(null)
  const prev = useRef(new Map())
  useLayoutEffect(() => {
    const root = ref.current
    if (!root) return
    const nodes = [...root.querySelectorAll('[data-pid]')]
    const next = new Map()
    for (const n of nodes) next.set(n.getAttribute('data-pid'), n.getBoundingClientRect())
    for (const n of nodes) {
      const id = n.getAttribute('data-pid')
      const a = prev.current.get(id)
      const b = next.get(id)
      if (!a || !b) continue
      const dy = a.top - b.top
      if (Math.abs(dy) < 1) continue
      n.style.transition = 'none'
      n.style.transform = 'translateY(' + dy + 'px)'
      n.getBoundingClientRect()
      n.style.transition = 'transform 180ms ease'
      n.style.transform = ''
      const clear = () => { n.style.transition = ''; n.style.transform = '' }
      n.addEventListener('transitionend', clear, { once: true })
    }
    prev.current = next
  }, [dep])
  return ref
}


function useClickToRefresh(pollMinutes) {
  return React.useCallback(async (pid) => {
    if (!pid || !_rest) return false
    const now = Date.now()
    if (now - (_lastManualRefresh[pid] || 0) < MANUAL_REFRESH_MS) return false
    if (_inflightRefresh.has(pid)) return false
    _lastManualRefresh[pid] = now
    _inflightRefresh.add(pid)
    queryClient.setQueryData(REFRESHING_KEY, true)
    try {
      const fresh = await _rest('/refresh', { method: 'POST', body: { providers: [pid] } })
      if (fresh && typeof fresh === 'object') {
        queryClient.setQueryData(['provider-status-v4', pollMinutes],
          prev => ({ ...(prev || {}), ...fresh }))
        return true
      }
      return false
    } catch {
      return false
    } finally {
      _inflightRefresh.delete(pid)
      queryClient.setQueryData(REFRESHING_KEY, _inflightRefresh.size > 0)
    }
  }, [pollMinutes])
}

// ── tiny status bar chip ──────────────────────────────────────────

function _ageText(unixSec) {
  const s = Math.max(0, Math.floor(Date.now() / 1000 - unixSec))
  if (s < 60) return s + 's'
  if (s < 3600) return Math.floor(s / 60) + 'm'
  return Math.floor(s / 3600) + 'h'
}

function _countdownText(unixSec) {
  const s = Math.max(0, Math.floor(unixSec - Date.now() / 1000))
  if (s < 3600) return Math.max(1, Math.floor(s / 60)) + 'm'
  if (s < 86400) return Math.floor(s / 3600) + 'h' + String(Math.floor((s % 3600) / 600)) + 'm'
  return Math.floor(s / 86400) + 'd'
}

// 5h refresh remaining: below an hour as m:ss, otherwise hh:mm.
function _fiveHText(unixSec) {
  const s = Math.max(0, Math.floor(unixSec - Date.now() / 1000))
  if (s < 3600) {
    const m = Math.floor(s / 60)
    const ss = String(Math.floor(s % 60)).padStart(2, '0')
    return m + ':' + ss + 'm'
  }
  const h = Math.floor(s / 3600)
  const m = String(Math.floor((s % 3600) / 60)).padStart(2, '0')
  return h + ':' + m + 'h'
}

// GLM + Codex carry a 5h refresh window; their hover is just the two facts.
function _chipTitle(id, status) {
  const fiveH = id === 'glm' || id === 'codex'
  if (fiveH) {
    const p = []
    if (status?.resets_at) p.push('Refresh ' + _fiveHText(status.resets_at))
    if (status?.fetched_at) p.push('Checked ' + _ageText(status.fetched_at) + ' ago')
    return p.join(' · ')
  }
  const parts = []
  if (status?.fetched_at) parts.push('Updated ' + _ageText(status.fetched_at) + ' ago')
  if (status?.resets_at) parts.push('Resets in ' + _countdownText(status.resets_at))
  if (status?.burn?.eta_hours != null && status.burn.eta_hours < 48) {
    parts.push('Estimated ' + (status.burn.eta_hours < 1
      ? Math.max(1, Math.round(status.burn.eta_hours * 60)) + 'm'
      : status.burn.eta_hours + 'h') + ' to ' + (status.burn.rate_per_hour > 0 ? 'cap' : 'empty'))
  }
  return parts.join(' · ')
}

function ProviderChip({ id, name, status, onRefresh, active }) {
  const [okFlash, setOkFlash] = useState(false)
  const loading = status === undefined
  const err = status && status.ok === false
  const pct = status?.percent ?? status?.pct ?? null
  const bal = status?.balance ?? null

  if (loading) {
    return jsxs('span', {
      className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem]',
      style: { color: 'var(--ui-text-quaternary)' },
      children: [
        jsx(Codicon, { name: status?.icon || 'circle-outline', size: '0.6rem' }),
        jsx('span', { children: name + '…' }),
      ],
    })
  }

  if (err) {
    // Short label + error glyph: hover shows detail, click copies full error
    const errText = status.no_plan ? 'no plan' : status.needs_auth ? 'auth?' : 'error'
    return jsx(ErrorChip, { label: name + ': ' + errText, detail: status.error || 'needs authentication' })
  }

  // Two-tone chip: gray label, colored value, gray direction arrow.
    // Tier rules per quota kind:
    //   increase (5h windows):   amber when rising, bold amber at >=80 used,
    //                            red+bold at >=90 used
    //   exhaust (wk/mo/tavily):  displayed as REMAINING; bold when remaining<=20,
    //                            red+bold when remaining<=10
    //   credit (deepseek):       bold when <$5, red+bold when <$1
    // Every value gets a gray direction arrow so the trend reads at a glance.

    const fmtPct = v => (id !== 'grok' && v < 10 ? v.toFixed(1) : Math.round(v)) + '%'
    const AMBER = '#f59e0b' // matches SignalDot warn

  // Which kind is this provider's headline number?
  const kind =
    id === 'deepseek' || id === 'openrouter' ? 'credit'
    : id === 'glm' ? 'increase'            // 5h window, used % rises
    : id === 'tavily' ? 'exhaust'          // monthly pool -> decreasing
    : id === 'opencode' ? 'exhaust'        // headline = worst exhaust window
    : id === 'grok' ? 'exhaust'
    : 'exhaust'                             // glm default (worst across windows)

  // codex: multi-window (↑5h · ↓weekly) rendered like opencode
  const multi = (id === 'opencode' || id === 'codex') && status?.detail

  let valueCls = ''
  let valueStyle = { color: 'var(--ui-accent)' }
  let valueText = ''
  let tag = ''

  if (pct !== null && pct !== undefined) {
    const display = kind === 'exhaust' ? Math.max(0, 100 - pct) : pct
    valueText = fmtPct(display)

    if (kind === 'increase') {
      // 5h-style: value is "used", rises toward a cap. Amber normally,
      // bold amber at >=80, red+bold at >=90.
      if (display >= 90) { valueCls = 'text-destructive font-semibold'; valueStyle = null }
      else if (display >= 80) { valueCls = 'font-semibold'; valueStyle = { color: AMBER } }
      else { valueCls = ''; valueStyle = { color: AMBER } }
      tag = '↑'
    } else {
      // exhaust-style: value shown is what remains, drains to zero.
      // Amber normally, bold amber at <=20 remaining, red+bold at <=10.
      if (display <= 10) { valueCls = 'text-destructive font-semibold'; valueStyle = null }
      else if (display <= 20) { valueCls = 'font-semibold'; valueStyle = { color: AMBER } }
      else { valueCls = ''; valueStyle = { color: AMBER } }
      tag = '↓'
    }
  } else if (bal !== null && bal !== undefined) {
    valueText = '$' + bal.toFixed(2)
    if (bal < 1) { valueCls = 'text-destructive font-semibold'; valueStyle = null }
    else if (bal < 5) { valueCls = 'font-semibold'; valueStyle = null }
    tag = '↑' // balance increases as you top up / decreases as it burns; show ↑ for headroom
  } else if (status?.detail) {
    valueText = status.detail
  }
  // multi-window providers don't show a separate headline value
  if (multi) { valueText = ''; valueCls = ''; valueStyle = { color: 'var(--ui-accent)' }; tag = '' }

  return jsxs('span', {
    className: 'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem] tabular-nums cursor-pointer',
    title: _chipTitle(id, status) + (active ? '  · active model' : ''),
    onClick: async () => {
      const ok = await onRefresh()
      if (!ok) return
      setOkFlash(true)
      setTimeout(() => setOkFlash(false), 400)
    },
    children: [
      jsx(Codicon, { name: id === 'deepseek' ? 'database' : id === 'openrouter' ? 'globe' : id === 'glm' ? 'hubot' : id === 'tavily' ? 'search' : id === 'grok' ? 'comment' : id === 'codex' ? 'code' : 'terminal', size: '0.6rem', style: { color: 'var(--ui-text-quaternary)' } }),
      jsx('span', { style: { color: 'var(--ui-text-tertiary)' }, children: name + ':' }),
      okFlash ? jsx(Codicon, { name: 'check', size: '0.6rem', style: { color: 'var(--ui-text-tertiary)' } }) : null,
      ...(multi
        // multi-window provider: gray arrows + accent values only — no headline repeat
        ? String(status.detail).split(/\s+/).filter(Boolean).map(seg => {
            const arrow = seg[0]
            const payload = parseFloat(seg.slice(1)) // backend sends remaining for both arrows
            let cls = ''
            let segColor = 'var(--ui-accent)'
            let shown = seg.slice(1)
            if (!isNaN(payload)) {
              if (arrow === '↑') {
                // 5h: payload is remaining; show USED (0 = empty window, 100 = burnt).
                // GLM reports firm percentages — round, never decimals.
                const used = 100 - payload
                shown = Math.round(used) + '%'
                if (used >= 90) { cls = 'text-destructive font-semibold'; segColor = null }
                else if (used >= 80) { cls = 'font-semibold'; segColor = AMBER }
                else segColor = AMBER
              } else {
                // decreasing: show remaining as sent
                shown = (payload < 10 ? payload.toFixed(1) : Math.round(payload)) + '%'
                if (payload <= 10) cls = 'text-destructive font-semibold'
                else if (payload <= 20) { cls = 'font-semibold'; segColor = AMBER }
                else segColor = AMBER
              }
            }
            return jsx('span', {
              className: cls,
              children: [
                jsx('span', { style: { color: 'var(--ui-text-quaternary)' }, children: arrow }),
                jsx('span', { style: cls.includes('destructive') ? null : { color: segColor }, children: shown }),
              ],
            })
          })
        : [
            jsx('span', { className: valueCls, style: valueStyle, children: valueText || '—' }),
            valueText ? jsx('span', { style: { color: 'var(--ui-text-quaternary)' }, children: tag }) : null,
          ]),
      status?.stale ? jsx(Codicon, { name: 'warning', size: '0.6rem', style: { color: 'var(--ui-accent-secondary)' } }) : null,
      // Multi-key providers always show the active slot (#1 included) so the
      // bar reads which key is in use; single-key providers stay clean.
      (Number(status?.poolSize) > 1 && status?.slot) ? jsx('span', { style: { color: 'var(--ui-text-quaternary)' }, children: '#' + status.slot }) : null,
    ],
  })
}

// ── status query hook ─────────────────────────────────────────────

let _rest = null // injected at register(ctx) — ctx.rest hits /api/plugins/provider-status

function useProviderStatus(pollMinutes) {
  return useQuery({
    queryKey: ['provider-status-v4', pollMinutes],
    queryFn: () => _rest ? _rest('/status') : Promise.resolve(null),
    refetchInterval: Math.max(1, pollMinutes || 5) * 60_000,
    refetchOnWindowFocus: true,
    refetchOnReconnect: true,
    staleTime: STALE_MS,
  })
}

// ── statusbar item — shows all provider chips inline ───────────────

const SHORT_NAME = {
  grok: 'Grok',
  glm: 'GLM',
  opencode: 'Go',
  openrouter: 'OR',
  codex: 'Codex',
  openai: 'OA',
  anthropic: 'AN',
  groq: 'GQ',
  cerebras: 'CB',
  moonshot: 'MS',
  minimax: 'MX',
  gemini: 'GM',
  huggingface: 'HF',
  mistral: 'MI',
  qwen: 'QW',
}

function chipName(id, full, compact) {
  if (compact && SHORT_NAME[id]) return SHORT_NAME[id]
  return full || id
}

function StatusBarGroup() {
  const cfgQ = useQuery({
    queryKey: ['provider-config-v5'],
    queryFn: () => _rest ? _rest('/config') : Promise.resolve({ providers: {} }),
    staleTime: 5_000,
  })
  const stQ = useProviderStatus(cfgQ.data?.poll_minutes || 5)
  const statuses = stQ.data
  const pollMin = cfgQ.data?.poll_minutes || 5
  const actQ = useQuery({
    queryKey: ['provider-active-v1'],
    queryFn: () => _rest ? _rest('/active') : Promise.resolve(null),
    staleTime: 30_000,
    refetchInterval: 60_000,
    retry: 1,
  })
  const activePid = actQ.data?.pid
  const onChipRefresh = useClickToRefresh(pollMin)
  if (!statuses) return null

  const entries = Object.entries(statuses).filter(([, s]) => s.enabled)
  if (!entries.length) return null

  // honor the saved order from the settings dialog
  const order = cfgQ.data?.order
  if (order?.length) {
    entries.sort((a, b) => {
      const ia = order.indexOf(a[0]); const ib = order.indexOf(b[0])
      return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    })
  }

  return jsxs('span', {
    className: 'inline-flex h-full items-center',
    children: entries.map(([id, s]) => {
      const idx = s.pool_index ?? cfgQ.data?.providers?.[id]?.pool_index ?? 0
      const poolSize = (cfgQ.data?.providers?.[id]?.pool || []).filter(Boolean).length
      return jsx(ProviderChip, { key: id, id, name: chipName(id, s.name || id, entries.length > 2), status: { ...s, slot: Number(idx) + 1, poolSize }, onRefresh: () => onChipRefresh(id), active: id === activePid })
    }),
  })
}

// ── inline error chip (hover = detail, click = copy) ──────────────
// Shows LEFT of the gear. Never replaces any other control.

function ErrorChip({ label, detail }) {
  const [copied, setCopied] = useState(false)
  const copyErr = async () => {
    try { await navigator.clipboard.writeText(detail || label || ''); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch {}
  }
  return jsx(Tooltip, {
    label: (detail || label || 'error') + '  (click to copy)',
    children: jsx('button', {
      type: 'button', onClick: copyErr,
      className: cn('inline-flex h-full items-center gap-1 rounded-none px-1 text-[0.6875rem]',
        'text-(--color-destructive, #e5484d) hover:bg-(--chrome-action-hover)'),
      children: [
        jsx(Codicon, { name: 'error', size: '0.7rem' }),
        label ? jsx('span', { children: copied ? '✓' : label }) : null,
      ],
    }),
  })
}

// Catches render errors inside the bars slot so the boundary chrome never
// swaps the whole contribution for its own error affordance.
class PluginErrorBoundary extends React.Component {
  constructor(props) { super(props); this.state = { err: null } }
  static getDerivedStateFromError(err) { return { err } }
  render() {
    if (this.state.err) {
      const msg = this.state.err?.message || String(this.state.err)
      return jsx(ErrorChip, { label: 'plugin', detail: msg })
    }
    return this.props.children
  }
}

// ── gear icon + modal setup dialog ────────────────────────────────

function GearMenu() {
  const [open, setOpen] = useState(false)
  // inline header poll-interval field: config query + local edit state + save
  const cfgQ = useQuery({
    queryKey: ['provider-config-v5'],
    queryFn: () => _rest ? _rest('/config') : Promise.resolve({ providers: {} }),
    staleTime: 5_000,
  })
  const pollMin = cfgQ.data?.poll_minutes || 5
  const [hdrPoll, setHdrPoll] = useState(pollMin)
  useEffect(() => { setHdrPoll(pollMin) }, [pollMin])
  const saveHdrPoll = async () => {
    const v = Math.max(1, parseInt(hdrPoll, 10) || 5)
    await postJson('config', { providers: cfgQ.data?.providers || {}, order: Object.keys(cfgQ.data?.providers || {}), poll_minutes: v })
    postJson('refresh')
    cfgQ.refetch()
  }
  // subscribe to the shared refresh-in-flight flag (set by chip clicks)
  const refreshQ = useQuery({
    queryKey: REFRESHING_KEY,
    queryFn: () => Promise.resolve(false),
    staleTime: Infinity,
    initialData: false,
  })
  const refreshing = !!refreshQ.data

  return jsxs(Fragment, {
    children: [
      jsx('button', {
        type: 'button',
        title: refreshing ? 'refreshing provider quotas…' : 'provider status setup',
        className: cn(
          'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem]',
          'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
        ),
        onClick: () => setOpen(true),
        children: jsx(Codicon, {
          name: refreshing ? 'refresh' : 'settings-gear', size: '0.7rem',
          className: refreshing ? 'animate-spin' : undefined,
        }),
      }),
      jsx(Dialog, {
        open,
        onOpenChange: setOpen,
        children: jsx(DialogContent, {
          className: cn(
            'max-w-md rounded-xl border-(--ui-stroke-secondary)',
            // Glass UI on (html[data-hermes-glass]): thin the fill so the window
            // material reads through, matching the app popover recipe (92% mix
            // + blur). Otherwise the standard near-opaque dialog fill.
            document.documentElement.hasAttribute('data-hermes-glass')
              ? 'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_80%,transparent)] backdrop-blur-xl'
              : 'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_96%,transparent)] backdrop-blur-md'
          ),
          bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
          children: [
            // h-7 + -mt-1.5 puts the row's vertical center on the absolutely-positioned
            // X button's center (top-2.5 + half of icon-xs), so title/poll/X align.
            jsxs(DialogHeader, { className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2', children: [
              jsx(DialogTitle, { children: 'Provider Status Setup' }),
              // poll interval, inline in the header (left of the X button)
              jsxs('div', { className: 'flex items-center gap-1.5 text-[0.7rem] font-normal shrink-0',
                style: { color: 'var(--ui-text-quaternary)' }, children: [
                jsx('span', { children: 'Refresh every' }),
                jsx('input', { type: 'number', min: 1, max: 60, value: hdrPoll,
                  onChange: e => setHdrPoll(e.target.value),
                  onBlur: () => { if (String(hdrPoll) !== String(pollMin)) saveHdrPoll() },
                  onKeyDown: e => { if (e.key === 'Enter') e.currentTarget.blur() },
                  className: 'h-6 w-12 rounded border bg-transparent px-1.5 text-[0.7rem] tabular-nums text-right',
                  style: { borderColor: 'var(--ui-border)', color: 'var(--ui-text-secondary)' } }),
                jsx('span', { children: 'min' }),
              ]}),
            ]}),
            jsx(SetupBody, { onDone: () => setOpen(false) }),
          ],
        }),
      }),
    ],
  })
}


// ── experimental Hermes-style dialog (second gear) ────────────────
// Parallel to GearMenu. Does not replace it. Same backend, different chrome:
// house Dialog tokens, accent border, glass-raised when Glass is on, title +
// description + footer, grouped settings-style list.

function ExpGearMenu() {
  const [open, setOpen] = useState(false)
  const glass = useGlassOn()
  const cfgQ = useQuery({
    queryKey: ['provider-config-v5'],
    queryFn: () => _rest ? _rest('/config') : Promise.resolve({ providers: {} }),
    staleTime: 5_000,
  })
  const pollMin = cfgQ.data?.poll_minutes || 5
  const [hdrPoll, setHdrPoll] = useState(pollMin)
  useEffect(() => { setHdrPoll(pollMin) }, [pollMin])
  const saveHdrPoll = async () => {
    const v = Math.max(1, parseInt(hdrPoll, 10) || 5)
    await postJson('config', { providers: cfgQ.data?.providers || {}, order: Object.keys(cfgQ.data?.providers || {}), poll_minutes: v })
    postJson('refresh')
    cfgQ.refetch()
  }
  const refreshQ = useQuery({
    queryKey: REFRESHING_KEY,
    queryFn: () => Promise.resolve(false),
    staleTime: Infinity,
    initialData: false,
  })
  const refreshing = !!refreshQ.data

  // House dialog overlay is bg-black/22 — that kills glass. Thin it only while
  // this experimental dialog is open AND Glass is on.
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

  return jsxs(Fragment, {
    children: [
      jsx('button', {
        type: 'button',
        title: 'provider status setup',
        className: cn(
          'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem]',
          'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
        ),
        onClick: () => { if (!refreshing) setOpen(true) },
        children: jsx(Codicon, { name: 'settings-gear', size: '0.7rem' }),
      }),
      jsx(Dialog, {
        open,
        onOpenChange: setOpen,
        children: jsx(DialogContent, {
          className: cn(
            'max-w-lg rounded-xl shadow-nous border-(--ui-accent)',
            glass
              ? 'bg-[color-mix(in_srgb,var(--ui-bg-elevated)_42%,transparent)] backdrop-blur-2xl'
              : 'bg-(--ui-chat-bubble-background)'
          ),
          bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
          children: [
            jsxs(DialogHeader, { className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2', children: [
              jsx(DialogTitle, { children: 'Providers' }),
              jsxs('div', { className: 'flex items-center gap-1.5 text-[0.7rem] font-normal shrink-0',
                style: { color: 'var(--ui-text-quaternary)' }, children: [
                jsx('span', { children: 'Refresh every' }),
                jsx('input', { type: 'number', min: 1, max: 60, value: hdrPoll,
                  onChange: e => setHdrPoll(e.target.value),
                  onBlur: () => { if (String(hdrPoll) !== String(pollMin)) saveHdrPoll() },
                  onKeyDown: e => { if (e.key === 'Enter') e.currentTarget.blur() },
                  className: 'h-6 w-12 rounded border bg-transparent px-1.5 text-[0.7rem] tabular-nums text-right',
                  style: { borderColor: 'var(--ui-border)', color: 'var(--ui-text-secondary)' } }),
                jsx('span', { children: 'min' }),
              ]}),
            ]}),
            jsx(SetupBody, { variant: 'hermes' }),
          ],
        }),
      }),
    ],
  })
}


// ── setup dialog body ─────────────────────────────────────────────

// Static copy of backend PROVIDER_META. Used when /meta is 404 (desktop
// backend started before the plugin existed). has_env stays false until
// the Python half actually mounts.
const FALLBACK_META = {
  deepseek: { name: 'DeepSeek', icon: 'database', env: ['DEEPSEEK_API_KEY'], has_env: false },
  glm: { name: 'GLM (z.ai)', icon: 'hubot', env: ['ZAI_API_KEY', 'GLM_API_KEY'], has_env: false },
  tavily: { name: 'Tavily', icon: 'search', env: ['TAVILY_API_KEY'], has_env: false },
  grok: { name: 'Grok (xAI)', icon: 'comment', env: [], has_env: false },
  codex: { name: 'Codex (OpenAI)', icon: 'code', env: [], has_env: false },
  opencode: { name: 'OpenCode Go', icon: 'terminal', env: ['OPENCODE_GO_API_KEY'], has_env: false },
  openrouter: { name: 'OpenRouter', icon: 'globe', env: ['OPENROUTER_API_KEY'], has_env: false },
  openai: { name: 'OpenAI', icon: 'cloud', env: ['OPENAI_API_KEY'], has_env: false },
  anthropic: { name: 'Anthropic', icon: 'comment-discussion', env: ['ANTHROPIC_API_KEY'], has_env: false },
  groq: { name: 'Groq', icon: 'zap', env: ['GROQ_API_KEY'], has_env: false },
  cerebras: { name: 'Cerebras', icon: 'chip', env: ['CEREBRAS_API_KEY'], has_env: false },
  moonshot: { name: 'Moonshot Kimi', icon: 'moon', env: ['MOONSHOT_API_KEY'], has_env: false },
  minimax: { name: 'MiniMax', icon: 'symbol-numeric', env: ['MINIMAX_API_KEY'], has_env: false },
  gemini: { name: 'Google Gemini', icon: 'sparkle', env: ['GEMINI_API_KEY'], has_env: false },
  huggingface: { name: 'Hugging Face', icon: 'smiley', env: ['HUGGINGFACE_API_KEY'], has_env: false },
  mistral: { name: 'Mistral', icon: 'wind', env: ['MISTRAL_API_KEY'], has_env: false },
  qwen: { name: 'Qwen', icon: 'archive', env: ['DASHSCOPE_API_KEY'], has_env: false },
}

function _isMetaMap(v) {
  return !!(v && typeof v === 'object' && !Array.isArray(v) && Object.keys(v).length)
}

function useProviderData() {
  const metaQ = useQuery({
    queryKey: ['provider-meta-v5'],
    queryFn: async () => {
      if (!_rest) throw new Error('plugin REST door missing')
      const r = await _rest('/meta')
      if (!_isMetaMap(r)) throw new Error('backend /meta empty or missing (desktop backend not remounted)')
      return r
    },
    staleTime: 60_000,
    retry: 1,
  })
  const cfgQ = useQuery({
    queryKey: ['provider-config-v5'],
    queryFn: () => _rest ? _rest('/config') : Promise.resolve({ providers: {} }),
  })
  const stQ = useProviderStatus(cfgQ.data?.poll_minutes || 5)
  const live = _isMetaMap(metaQ.data)
  return {
    meta: live ? metaQ.data : FALLBACK_META,
    metaLive: live,
    metaWaiting: metaQ.isPending || (metaQ.isFetching && !live && !metaQ.isFetched),
    metaError: metaQ.isError ? (metaQ.error?.message || String(metaQ.error)) : (!live && metaQ.isFetched ? 'backend /meta not mounted' : ''),
    refetchMeta: metaQ.refetch,
    cfg: cfgQ.data || { providers: {} },
    statuses: stQ.data,
    refetchCfg: cfgQ.refetch,
  }
}

async function postJson(path, body) {
  if (!_rest) return null
  try {
    const r = await _rest('/' + path, { method: 'POST', body: body || {} })
    // after any write: mark status + config stale so both bar and dialog refresh
    queryClient.invalidateQueries({ queryKey: ['provider-config-v5'], exact: false, refetchType: 'all' })
    queryClient.invalidateQueries({ queryKey: ['provider-status-v4'], exact: false, refetchType: 'all' })
    queryClient.invalidateQueries({ queryKey: ['provider-meta-v5'], exact: false, refetchType: 'all' })
    return r
  } catch {
    return null
  }
}



function StatusBadge({ st }) {
  if (!st || !st.enabled) return null
  if (st.ok === false && st.needs_auth)
    return jsx('span', { className: 'text-xs', style: { color: 'var(--ui-accent-secondary)' }, children: 'needs auth' })
  if (st.ok === false)
    return jsx('span', { className: 'text-xs text-destructive', children: st.error })
  if (st.ok === true)
    return jsx('span', { className: 'text-xs', style: { color: 'var(--ui-accent)' }, children: 'active' })
  return null
}

// ── per-provider setup row (card) ─────────────────────────────────
// Header: [gripper] [Name] [Login/OAuth] [Key field flex-1] [Badge] [☐] [+]
// SDK Button/Input/Tooltip for a polished look matching Hermes dialogs.

function _quotaText(quotas) {
  return (quotas || []).map(q => (q.display != null ? `${q.label}: ${q.display}` : `${q.label}: ${q.percent}%`)).join('\n')
}

function _quotaData(status) {
  if (Array.isArray(status?.quotas) && status.quotas.length) return status.quotas
  const labels = { '5h': '5-Hours', wk: 'Weekly', weekly: 'Weekly', mo: 'Monthly', monthly: 'Monthly' }
  const out = (status?.windows || []).flatMap(w => {
    const label = labels[String(w?.label || '').toLowerCase()]
    const pct = Number(w?.pct)
    return label && Number.isFinite(pct)
      ? [{ label, percent: Math.max(0, Math.min(100, Math.round((100 - pct) * 10) / 10)) }]
      : []
  })
  if (out.length) return out

  // Cached account providers use compact detail strings instead of windows:
  // ↑95% is 5h remaining; following ↓ values are weekly then monthly.
  const detail = String(status?.detail || '')
  const compact = [...detail.matchAll(/([↑↓])\s*(\d+(?:\.\d+)?)%/g)]
  if (compact.length) {
    let downIndex = 0
    return compact.map((m) => {
      const arrow = m[1]
      const percent = Number(m[2])
      const label = arrow === '↑' ? '5-Hours' : downIndex++ === 0 ? 'Weekly' : 'Monthly'
      return { label, percent }
    })
  }

  // Some cached status responses retain only the numeric headline fields.
  const used = Number(status?.percent)
  const exhaust = Number(status?.exhaust_percent)
  const period = String(status?.period || '').toLowerCase()
  const numeric = []
  if (Number.isFinite(used) && period !== 'weekly' && period !== 'monthly') numeric.push({ label: '5-Hours', percent: Math.max(0, Math.min(100, Math.round((100 - used) * 10) / 10)) })
  if (Number.isFinite(exhaust)) numeric.push({ label: 'Weekly', percent: Math.max(0, Math.min(100, Math.round((100 - exhaust) * 10) / 10)) })
  if (numeric.length) return numeric

  // Grok returns one billing period and percent used.
  if (Number.isFinite(used) && (period === 'weekly' || period === 'monthly')) {
    return [{ label: period === 'weekly' ? 'Weekly' : 'Monthly', percent: Math.max(0, Math.min(100, Math.round((100 - used) * 10) / 10)) }]
  }
  return []
}

function SignalDot({ pid, tone, reason, age, quotas, onCheck }) {
  const color = tone === 'ok' ? '#22c55e'
    : tone === 'warn' ? '#f59e0b'
    : tone === 'error' ? '#ef4444'
    : '#6b7280'
  const [hoverResult, setHoverResult] = useState(null)
  const effectiveTone = hoverResult?.tone || tone
  const effectiveQuotas = hoverResult?.quotas?.length ? hoverResult.quotas : quotas
  const fallback = hoverResult?.reason || reason || (effectiveTone === 'ok' ? 'Healthy' : effectiveTone === 'warn' ? 'Quota / retry' : effectiveTone === 'error' ? 'Not working' : 'Checking')
  // Quota rows show on ok AND warn (warn = quota pressure, so rows matter most);
  // error keeps the plain reason. Everything renders on ONE line with a fine
  // dot (spaced both sides) between segments — single line-box, so the app's
  // tooltip chip background covers the whole label.
  const quotaRows = _quotaText(effectiveQuotas)
  const segments = [
    effectiveTone === 'ok' ? 'Healthy' : fallback,
    ...(quotaRows ? quotaRows.split('\n') : []),
  ].map(s => s.trim()).filter(Boolean) // empty quota entries would leave a dangling trailing dot
  // Join with a breakable space before the dot and NBSP after: the label
  // wraps inside the 256px chip, and a plain-space join let lines break right
  // after the dot — a 'trailing' dot with empty space at the end of a line.
  let text = segments.join(' \u00b7\u00a0')
  if (effectiveTone !== 'ok' && age != null) {
    text += ` (checked ${age < 60 ? Math.round(age) + 's' : age < 3600 ? Math.round(age / 60) + 'm' : Math.round(age / 3600) + 'h'} ago)`
  }
  const check = async () => {
    if (onCheck) {
      const result = await onCheck(pid)
      if (result) setHoverResult(result)
    }
  }
  // Plain string label: the chip hugs each wrapped line. A span child would be
  // forced inline-flex (atomic box) and the chip would paint one rectangle
  // behind it — trailing empty space on short wrapped lines.
  return jsx(Tooltip, {
    label: text,
    children: jsx('span', {
      onMouseEnter: check,
      className: 'inline-block shrink-0 rounded-full',
      style: { width: 8, height: 8, background: color, boxShadow: `0 0 0 1px color-mix(in srgb, ${color} 40%, transparent)` },
    }),
  })
}

function ProviderRow({ pid, pmeta, pc, st, onSave, probe, probeAge, onCheck, variant, dragging, dropOver, onDragStart, onDragOver, onDrop, onDragEnd, onRemove }) {
  const [enabled, setEnabled] = useState(!!pc.enabled)
  const [keys, setKeys] = useState(pc.pool?.length ? [...pc.pool] : [''])
  const [flow, setFlow] = useState(null)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const isOAuth = pid === 'grok' || pid === 'codex'
  const isResetDay = pid === 'opencode'   // per-key renewal-day dropdown
  const [resetDays, setResetDays] = useState(() => (pc.reset_days || []).map(d => (typeof d === 'number' && d >= 1 && d <= 31) ? d : 0))
  useEffect(() => {
    setResetDays((pc.reset_days || []).map(d => (typeof d === 'number' && d >= 1 && d <= 31) ? d : 0))
  }, [(pc.reset_days || []).join(',')])

  // Renewal-day dropdown: None + 1..31. Compact as the widest value ("None"/"31"),
  // never wraps. Selecting a day marks that key's subscription renewal date.
    // Renewal-day dropdown: fully custom instead of a native <select> — the
  // OS-drawn popup ignores page theming and rendered light-on-white in dark
  // mode. A themed button + popover list takes all colors from ui vars.
  const [dayMenuFor, setDayMenuFor] = useState(null) // index of open menu
  useEffect(() => {
    if (dayMenuFor === null) return
    const close = e => {
      // Ignore presses inside any dropdown UI (button, menu, its scrollbar) —
      // otherwise the capture-phase mousedown closes the menu before the click
      // lands and the scrollbar becomes unusable.
      const t = e.target
      if (t && t.closest && t.closest('[data-day-menu],[data-day-button]')) return
      setDayMenuFor(null)
    }
    document.addEventListener('mousedown', close, true)
    return () => document.removeEventListener('mousedown', close, true)
  }, [dayMenuFor])

  const resetDaySelect = (i, extraCls) => {
    if (!isResetDay) return null
    const val = resetDays[i] || 0
    const open = dayMenuFor === i
    const pick = d => {
      const n = [...resetDays]
      while (n.length <= i) n.push(0)
      n[i] = d
      setResetDays(n)
      setDayMenuFor(null)
      // normalize: 0 = None (stored as null/omitted)
      const days = n.map(x => x || null)
      persist(undefined, undefined, { reset_days: days })
    }
    return jsx('div', {
      className: 'relative shrink-0 ' + (extraCls || ''),
      children: [
        jsx('button', {
          type: 'button',
          'data-day-button': '',
          title: 'Day of month this subscription renews on.\nSwitches to this key after the day passes.',
          onClick: e => { e.stopPropagation(); setDayMenuFor(open ? null : i) },
          className: 'h-6 w-2.6rem rounded border px-0.5 text-[0.65rem] tabular-nums text-center ' + (open ? 'border-(--ui-accent) ' : ''),
          style: {
            width: '2.6rem',
            background: 'transparent',
            borderColor: open ? 'var(--ui-accent)' : 'var(--ui-border)',
            color: val ? 'var(--ui-text-secondary, var(--foreground))' : 'var(--ui-text-quaternary, var(--foreground))',
          },
          children: val ? String(val) : 'None',
        }),
        open ? jsx('div', {
          'data-day-menu': '',
          className: 'absolute right-0 top-7 z-50 rounded-md border py-1 shadow-lg',
          style: {
            background: 'var(--ui-bg-elevated, var(--background))',
            borderColor: 'var(--ui-border)',
            maxHeight: '16rem',
            overflowY: 'auto',
            minWidth: '4rem',
          },
          children: [jsx('button', {
            key: 'n', type: 'button',
            onClick: () => pick(0),
            className: 'block w-full px-2 py-0.5 text-left text-[0.65rem] hover:bg-(--ui-control-hover-background)',
            style: { color: !val ? 'var(--ui-accent)' : 'var(--ui-text-secondary, var(--foreground))' },
            children: 'None',
          })].concat(Array.from({ length: 31 }, (_, k) => k + 1).map(d => jsx('button', {
            key: d, type: 'button',
            onClick: () => pick(d),
            className: 'block w-full px-2 py-0.5 text-left text-[0.65rem] tabular-nums hover:bg-(--ui-control-hover-background)',
            style: { color: val === d ? 'var(--ui-accent)' : 'var(--ui-text-secondary, var(--foreground))' },
            children: String(d),
          }))),
        }) : null,
      ],
    })
  }

  useEffect(() => {
    setEnabled(!!pc.enabled)
    setKeys(pc.pool?.length ? [...pc.pool] : [''])
  }, [pc.enabled, (pc.pool || []).join('\n')])

  const persist = async (nextEnabled, nextKeys, updates) => {
    const pool = (nextKeys ?? keys).map(s => s.trim()).filter(Boolean)
    await onSave(pid, { ...pc, enabled: nextEnabled ?? enabled, pool, ...updates })
  }
  const setKeyAt = (i, v) => { const n = [...keys]; n[i] = v; setKeys(n) }
  const addKey = () => { setKeys([...keys, '']) }
  const delKey = (i) => {
    const n = keys.filter((_, j) => j !== i)
    setKeys(n.length ? n : [''])
    // keep the radio honest: deleting the active key falls back to #1; deleting
    // one before it shifts the active index up by one
    let nextIdx = activeIdx
    if (i === activeIdx) nextIdx = 0
    else if (i < activeIdx) nextIdx = activeIdx - 1
    setActiveIdx(nextIdx)
    persist(undefined, n.length ? n : [''], { pool_index: nextIdx })
  }

  const [activeIdx, setActiveIdx] = useState(() => {
    const n = Math.max(1, (pc.pool || []).filter(Boolean).length)
    const idx = Number(pc.pool_index) || 0
    return idx < n ? idx : 0
  })
  useEffect(() => {
    const n = Math.max(1, (pc.pool || []).filter(Boolean).length)
    const idx = Number(pc.pool_index) || 0
    setActiveIdx(idx < n ? idx : 0)
  }, [Number(pc.pool_index) || 0, (pc.pool || []).length])

  // Active-key radio: one per key row. Selecting a row persists pool_index;
  // the backend applies the key to the Hermes env and the dialog refreshes
  // that provider so the statusbar shows the new account immediately.
  const keyActiveRadio = (i) => {
    if (isOAuth) return null
    const n = Math.max(1, keys.map(s => s.trim()).filter(Boolean).length)
    if (n < 2) return null
    const active = i === activeIdx
    return jsx('button', {
      type: 'button',
      title: active ? 'Active key' : 'Use this key',
      onClick: () => {
        if (active) return
        setActiveIdx(i)
        persist(undefined, undefined, { pool_index: i })
        postJson('refresh', { providers: [pid] })
      },
      className: 'shrink-0 inline-flex items-center justify-center w-4 h-4 rounded-full border transition-colors ' +
        (active ? 'border-(--ui-accent)' : 'border-(--ui-stroke-secondary) hover:border-(--ui-text-tertiary)'),
      style: { background: active ? 'var(--ui-accent)' : 'transparent' },
      children: active ? jsx('span', { className: 'w-1.5 h-1.5 rounded-full', style: { background: 'var(--background, #fff)' } }) : null,
    })
  }

  const startLogin = async () => {
    setBusy(true)
    if (pid === 'codex') {
      // Browser flow: backend starts a localhost catcher, we open the authorize page.
      // NOTE: requires the desktop backend to own port 1455 (same as codex CLI).
      try {
        const res = await _rest('/codex/browser/start', { method: 'POST', body: { port: 1455 } })
        setBusy(false)
        if (res?.ok && res.authorize_url) {
          setFlow({ browser: true, authorize_url: res.authorize_url, port: 1455 })
          window.open(res.authorize_url, '_blank', 'width=560,height=760')
        }
        return
      } catch { setBusy(false); return }
    }
    const res = await postJson(pid + '/device/start')
    setBusy(false)
    if (res?.ok && res.verification_uri) setFlow(res)
  }
  const logout = () => { setFlow(null); persist(undefined, undefined, { access_token: '', refresh_token: '', expires_at: 0 }) }
  const copyCode = async () => {
    try { await navigator.clipboard.writeText(flow.user_code); setCopied(true); setTimeout(() => setCopied(false), 1200) } catch {}
  }

  useEffect(() => {
    // codex browser flow: poll the backend until the localhost catcher got the code
    if (flow?.browser && flow?.port) {
      let cancel = false
      const tick = async () => {
        if (cancel) return
        try {
          const r = await _rest('/codex/browser/poll?port=' + flow.port)
          if (!cancel && r?.ok) {
            setFlow(null)
            queryClient.invalidateQueries({ queryKey: ['provider-config-v5'], exact: false, refetchType: 'all' })
            postJson('refresh')
          }
        } catch {}
      }
      const id = setInterval(tick, 2500)
      return () => { cancel = true; clearInterval(id) }
    }
    // grok device flow
    if (!flow?.device_code) return
    let cancel = false
    const tick = async () => {
      if (cancel) return
      const r = await postJson(pid + '/device/poll', { device_code: flow.device_code })
      if (!cancel && r?.ok) {
        setFlow(null)
        queryClient.invalidateQueries({ queryKey: ['provider-config-v5'], exact: false, refetchType: 'all' })
        postJson('refresh')
      }
    }
    const id = setInterval(tick, 4000)
    return () => { cancel = true; clearInterval(id) }
  }, [flow?.device_code, flow?.browser])

  // ── OAuth login slot ─────────────────────────────────────────
  let loginSlot = null
  if (isOAuth) {
    if (flow?.browser) {
      loginSlot = jsx('span', { className: 'text-[0.7rem] shrink-0', style: { color: 'var(--ui-text-tertiary)' }, children: 'Finish in the browser…' })
    } else if (flow?.user_code) {
      loginSlot = jsxs('span', { className: 'flex items-center gap-1.5 shrink-0', children: [
        jsx(Tooltip, { label: 'click to copy', children: jsxs('code', { onClick: copyCode, className: 'font-mono text-[0.7rem] font-medium tracking-wider cursor-pointer select-all inline-flex items-center gap-1', style: { color: 'var(--ui-warning)' }, children: [
          flow.user_code,
          copied ? jsx('span', { style: { color: copied ? 'var(--ui-accent)' : 'inherit' }, children: '✓' }) : null,
        ] }) }),
        jsx(Button, { variant: 'default', size: 'sm', className: 'h-6 px-2 text-[0.7rem] shrink-0', onClick: () => window.open(flow.verification_uri, '_blank', 'width=560,height=760'), children: 'Connect ↗' }),
      ]})
    } else {
      loginSlot = pc.access_token
        ? jsx(Button, { variant: 'secondary', size: 'sm', className: 'h-6 px-2.5 text-[0.7rem] shrink-0', onClick: logout, title: st?.email || pc.email || '', children: 'Log out' })
        : jsx(Button, { variant: 'default', size: 'sm', className: 'h-6 px-3 text-[0.7rem] shrink-0', onClick: startLogin, disabled: busy, children: busy ? '…' : 'Log in' })
    }
  }

  const ph = pmeta.has_env ? 'Key used from Hermes secrets.' : ''

  const hermes = variant === 'hermes'
  return jsxs('div', {
    'data-pid': pid,
    className: cn(
      hermes ? 'px-3 py-2.5 flex flex-col gap-2' : 'rounded-lg p-2.5 flex flex-col gap-2',
      dragging && 'opacity-40',
      dropOver && !dragging && 'outline outline-1 outline-(--ui-accent) outline-offset-[-1px]'
    ),
    style: hermes ? undefined : { background: 'var(--ui-bg-secondary, rgba(255,255,255,0.03))', border: '1px solid var(--ui-border)' },
    onDragOver: e => {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      onDragOver && onDragOver(e, pid)
    },
    onDrop: e => {
      e.preventDefault()
      const from = e.dataTransfer.getData('application/x-hermes-pid') || e.dataTransfer.getData('text/plain')
      onDrop && onDrop(from, pid)
    },
    children: [
      // ── header row ──
      jsxs('div', { className: 'flex items-center gap-2 min-h-[28px]', children: [
        // HTML5 drag handle (only the gripper is draggable so inputs stay usable)
        jsx('span', {
          draggable: true,
          title: 'Drag to reorder',
          className: 'inline-flex h-6 w-5 shrink-0 cursor-grab items-center justify-center select-none text-(--ui-text-quaternary) active:cursor-grabbing',
          onDragStart: e => {
            e.dataTransfer.setData('text/plain', pid)
            e.dataTransfer.setData('application/x-hermes-pid', pid)
            e.dataTransfer.effectAllowed = 'move'
            onDragStart && onDragStart(pid)
          },
          onDragEnd: () => { onDragEnd && onDragEnd() },
          children: jsx(Codicon, { name: 'gripper', size: '0.85rem' }),
        }),
        // provider name
        jsx('span', { className: 'font-medium text-sm shrink-0', children: pmeta.name }),
        // oauth login / code + connect
        loginSlot,
        // active-key radio (multi-key providers): marks which key is in use
        !isOAuth && pmeta.env?.length ? keyActiveRadio(0) : null,
        // key field #1 — spans the space between name/login and the right controls
        !isOAuth && pmeta.env?.length
          ? jsx(Input, { type: 'password', value: keys[0] || '', onChange: e => setKeyAt(0, e.target.value), onBlur: () => persist(), placeholder: ph, size: 'sm', className: 'flex-1 h-6 font-mono text-[0.7rem] min-w-0' })
          : null,
        // renewal-day dropdown (Go only): after the key field, before the dot
        !isOAuth && pmeta.env?.length ? resetDaySelect(0) : null,
        // spacer pushes status+controls to the right edge (OAuth rows w/o key field)
        isOAuth || !pmeta.env?.length ? jsx('span', { className: 'flex-1' }) : null,
        // status dot — right-aligned (tooltip notes when the value is a cached sweep)
        jsx(SignalDot, { pid, tone: (probe?.keys || []).find(k => k.index === 0)?.tone, reason: (probe?.keys || []).find(k => k.index === 0)?.reason, quotas: ((probe?.keys || []).find(k => k.index === 0)?.quotas?.length ? (probe?.keys || []).find(k => k.index === 0)?.quotas : _quotaData(st)), age: probeAge, onCheck }),
        // + button (env providers only) — square icon button with add glyph
        !isOAuth && pmeta.env?.length ? jsx(Button, { variant: 'outline', size: 'icon-xs', className: 'shrink-0 items-center justify-center', onClick: addKey, title: 'add another key', children: jsx(Codicon, { name: 'add', size: '0.75rem' }) }) : null,
        // checkbox
        jsx(Checkbox, { checked: enabled, onCheckedChange: v => { setEnabled(v); persist(v) }, className: 'shrink-0', size: 'sm' }),
        // delete provider — rightmost. Removes the row + key entirely.
        jsx(Button, { variant: 'ghost', size: 'icon-xs', className: 'shrink-0 text-(--ui-text-quaternary) hover:text-destructive', onClick: () => onRemove && onRemove(pid), title: 'delete provider', children: jsx(Codicon, { name: 'trash', size: '0.75rem' }) }),
      ]}),
      // ── extra key rows ──
      keys.slice(1).map((k, i) => jsxs('div', { className: 'flex items-center gap-2', children: [
        keyActiveRadio(i + 1),
        jsx('span', { className: 'text-[0.65rem] tabular-nums shrink-0 w-5 text-right', style: { color: 'var(--ui-text-quaternary)' }, children: '#' + (i + 2) }),
        jsx(Input, { type: 'password', value: k, onChange: e => setKeyAt(i + 1, e.target.value), onBlur: () => persist(), placeholder: `Key #${i + 2}`, size: 'sm', className: 'flex-1 h-6 font-mono text-[0.7rem]' }),
        resetDaySelect(i + 1),
        jsx(SignalDot, { pid, tone: (probe?.keys || []).find(row => row.index === i + 1)?.tone, reason: (probe?.keys || []).find(row => row.index === i + 1)?.reason, quotas: (probe?.keys || []).find(row => row.index === i + 1)?.quotas, age: probeAge, onCheck }),
        jsx(Button, { variant: 'ghost', size: 'icon-xs', className: 'text-destructive', onClick: () => delKey(i + 1), title: 'remove', children: jsx(Codicon, { name: 'close', size: '0.7rem' }) }),
      ]}, i + 1)),
    ],
  }, pid)
}
function SetupBody({ variant } = {}) {
  const { meta, metaLive, metaWaiting, metaError, refetchMeta, cfg, statuses, refetchCfg } = useProviderData()
  const provCfg = cfg.providers || {}

  // Row order: persisted in config as `order` (array of pids). New pids append.
  // Local state mirrors it so HTML5 drops render INSTANTLY; save follows async.
  const savedOrder = cfg.order?.length ? cfg.order : []
  const [order, setOrder] = useState(null) // null = not yet derived
  const [dragPid, setDragPid] = useState(null)
  const [overPid, setOverPid] = useState(null)
  // Rows follow saved `order` only. The catalog is the dropdown, never auto-appended.
  const pidsRaw = savedOrder.filter(p => meta[p])
  const pids = order ?? pidsRaw

  // Rapid add/delete: keep the intended order in a ref, serialize POSTs, and
  // ignore a cfg refetch that still contains a pid we just removed.
  const orderRef = useRef(pids)
  orderRef.current = pids
  const pendingRemove = useRef(new Set())
  const saveChain = useRef(Promise.resolve())
  const savingN = useRef(0)

  const persistNow = async (extra = {}) => {
    const latest = [...orderRef.current]
    const gone = [...pendingRemove.current]
    const rest = { ...extra }
    for (const [k, v] of Object.entries(provCfg)) {
      if (gone.includes(k) || !latest.includes(k)) continue
      if (!rest[k]) rest[k] = v
    }
    for (const k of Object.keys(rest)) {
      if (!latest.includes(k)) delete rest[k]
    }
    await postJson('config', { providers: rest, remove: gone, order: latest, poll_minutes: cfg.poll_minutes || undefined })
    postJson('refresh')
    await refetchCfg()
    if (savingN.current <= 1) {
      for (const p of gone) {
        if (!orderRef.current.includes(p)) pendingRemove.current.delete(p)
      }
    }
  }
  const enqueueCfg = (fn) => {
    savingN.current += 1
    saveChain.current = saveChain.current.then(fn).catch(() => {}).finally(() => { savingN.current -= 1 })
    return saveChain.current
  }

  const [toAdd, setToAdd] = useState('')
  const addable = Object.keys(meta).filter(p => !(pids).includes(p))

  const addProvider = () => {
    if (!toAdd || !meta[toAdd]) return
    const id = toAdd
    pendingRemove.current.delete(id)
    const next = [...orderRef.current, id]
    orderRef.current = next
    setOrder(next)
    setToAdd('')
    enqueueCfg(() => persistNow({ [id]: { ...(provCfg[id] || {}), enabled: false, pool: (provCfg[id] && provCfg[id].pool) || [] } }))
  }

  const removeProvider = (pid) => {
    pendingRemove.current.add(pid)
    const next = orderRef.current.filter(p => p !== pid)
    orderRef.current = next
    setOrder(next)
    enqueueCfg(() => persistNow())
  }

  useEffect(() => {
    if (savingN.current) return
    const server = (cfg.order || []).filter(p => meta[p])
    if ([...pendingRemove.current].some(p => server.includes(p))) return
    setOrder(null)
  }, [cfg])

  const persistOrder = (nextPids) => {
    orderRef.current = nextPids
    setOrder(nextPids)
    enqueueCfg(() => persistNow())
  }
  // Live HTML5 sortable: as the pointer crosses a row midpoint, splice now
  // (no persist). Persist once on drop / dragend.
  const hoverReorder = (e, toPid) => {
    setOverPid(toPid)
    if (!dragPid || !toPid) return
    const rect = e.currentTarget.getBoundingClientRect()
    const before = e.clientY < rect.top + rect.height / 2
    setOrder(prev => {
      const cur = prev ?? pidsRaw
      const from = cur.indexOf(dragPid)
      const hover = cur.indexOf(toPid)
      if (from < 0 || hover < 0) return prev
      let dest = before ? hover : hover + 1
      if (from < dest) dest -= 1
      if (from === dest) return prev
      const next = [...cur]
      const [item] = next.splice(from, 1)
      next.splice(dest, 0, item)
      return next
    })
  }
  const finishDrag = () => {
    setDragPid(null)
    setOverPid(null)
    const cur = order ?? pidsRaw
    if (cur.join(',') !== pidsRaw.join(',')) persistOrder(cur)
  }

  const flipRef = useFlipList((order ?? pidsRaw).join(','))

  const [probes, setProbes] = useState({})
  const [probeAges, setProbeAges] = useState({})   // pid -> cache age seconds
  const pollMinutes = Math.max(1, Number(cfg.poll_minutes) || 5)
  const statusesRef = useRef(statuses)
  statusesRef.current = statuses
  const checkProbe = React.useCallback(async (pid, force = false) => {
    if (!_rest || !pid) return null
    try {
      let result = null
      let age = null
      if (!force) {
        const cache = await _rest('/probe-cache')
        const entry = cache?.[pid]
        const maxAge = pollMinutes * 60 * 6
        result = entry?.result
        age = entry?.age_s
        if (!result || age == null || age > maxAge) result = null
      }
      if (!result) {
        // Fire-and-forget queue: the backend probes on a worker thread and
        // marks the pid pending in /probe-cache. Poll until it lands (or give
        // up) instead of holding the request open — a slow provider can then
        // never stall a hover or the dialog.
        await _rest('/probe', { method: 'POST', body: { provider: pid } })
        const deadline = Date.now() + 20000
        while (Date.now() < deadline) {
          await new Promise(r => setTimeout(r, force ? 500 : 1200))
          const cache = await _rest('/probe-cache')
          const entry = cache?.[pid]
          if (entry?.result && !entry?.pending) {
            result = entry.result
            age = entry.age_s
            break
          }
          if (!entry?.pending && entry?.result == null && Date.now() > deadline - 19000) break
        }
        if (!result) return null
      }
      if (result?.keys) {
        // Read statuses through a ref: this callback's deps are [pollMinutes],
        // so a direct closure would freeze the value from the first render
        // (usually undefined) and the quota fallback would always be empty.
        const fallbackQuotas = _quotaData(statusesRef.current?.[pid])
        const primary = result.keys.find(k => k.index === 0) || null
        const withQuotas = primary && !primary.quotas?.length && fallbackQuotas.length
          ? { ...primary, quotas: fallbackQuotas }
          : primary
        setProbes(prev => ({ ...prev, [pid]: result }))
        setProbeAges(prev => ({ ...prev, [pid]: age }))
        return withQuotas
      }
    } catch {}
    return null
  }, [pollMinutes])

  // Dialog open = probe everything (all providers, all keys per provider — the
  // backend walks the key pool of a provider in one queued probe, keys in
  // parallel). Queued AFTER the dialog has rendered (small delay) so the
  // entrance animation never competes with probe work; results stream into
  // `probes` state as the cache fills. Deliberately not awaited anywhere.
  const openedRef = useRef(false)
  useEffect(() => {
    if (openedRef.current || metaWaiting || !metaLive) return
    if (!pids.length) return
    openedRef.current = true
    const t = setTimeout(() => {
      for (const pid of pids) {
        checkProbe(pid, true)
      }
    }, 400)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [metaWaiting, metaLive, pids.join(',')])
  // Add-provider picker: custom themed dropdown (native select popup ignores
  // page theming — white popup in dark mode).
  const [addMenuOpen, setAddMenuOpen] = useState(false)
  useEffect(() => {
    if (!addMenuOpen) return
    const close = e => {
      const t = e.target
      if (t && t.closest && t.closest('[data-add-picker]')) return
      setAddMenuOpen(false)
    }
    document.addEventListener('mousedown', close, true)
    return () => document.removeEventListener('mousedown', close, true)
  }, [addMenuOpen])

  if (metaWaiting) return jsx('div', { className: 'p-2 text-xs', children: 'Loading…' })

  const banner = (!metaLive) ? jsxs('div', {
    className: 'rounded-md border px-2 py-1.5 text-[0.7rem] leading-snug',
    style: { borderColor: 'var(--ui-stroke-secondary)', color: 'var(--ui-text-secondary)' },
    children: [
      jsx('div', { children: 'Backend /meta is not mounted. Gateway restart does not remount it. Fully quit and reopen the Hermes desktop app.' }),
      metaError ? jsx('div', { className: 'mt-1 font-mono text-[0.65rem]', style: { color: 'var(--ui-text-quaternary)' }, children: String(metaError) }) : null,
      jsx(Button, { variant: 'ghost', size: 'sm', className: 'mt-1 h-6 px-2', onClick: () => refetchMeta(), children: 'Retry' }),
    ],
  }) : null

  const saveProvider = async (pid, next) => {
    await postJson('config', { providers: { ...provCfg, [pid]: next }, order: pids, poll_minutes: cfg.poll_minutes || undefined })
    postJson('refresh')
    refetchCfg()
  }

  const rows = pids.map((pid) =>
    jsx(ProviderRow, {
      key: pid, pid, pmeta: meta[pid], pc: provCfg[pid] || {}, st: statuses?.[pid], probe: probes[pid], probeAge: probeAges[pid], onCheck: checkProbe, onSave: saveProvider,
      variant,
      dragging: dragPid === pid,
      dropOver: overPid === pid,
      onDragStart: setDragPid,
      onDragOver: hoverReorder,
      onDrop: finishDrag,
      onDragEnd: finishDrag,
      onRemove: removeProvider,
    }))
  const addRow = addable.length
    ? jsxs('div', { className: 'flex items-center gap-2', children: [
        jsxs('div', { 'data-add-picker': '', className: 'relative flex-1 min-w-0', children: [
          jsx('button', {
            type: 'button',
            onClick: () => setAddMenuOpen(v => !v),
            className: 'h-7 w-full flex items-center justify-between rounded border px-2 text-[0.75rem]',
            style: {
              background: 'var(--ui-bg-elevated, var(--background))',
              borderColor: addMenuOpen ? 'var(--ui-accent)' : 'var(--ui-border)',
              color: toAdd ? 'var(--ui-text-secondary, var(--foreground))' : 'var(--ui-text-quaternary, var(--foreground))',
            },
            children: [
              jsx('span', { children: toAdd ? (meta[toAdd]?.name || toAdd) : 'Add a provider…' }),
              jsx('span', { style: { color: 'var(--ui-text-quaternary, var(--foreground))' }, children: '▾' }),
            ],
          }),
          addMenuOpen ? jsx('div', {
            className: 'absolute left-0 top-8 z-50 rounded-md border py-1 shadow-lg',
            style: {
              background: 'var(--ui-bg-elevated, var(--background))',
              borderColor: 'var(--ui-border)',
              maxHeight: '16rem',
              overflowY: 'auto',
              width: '100%',
            },
            children: addable.map(p => jsx('button', {
              key: p, type: 'button',
              onClick: () => { setToAdd(p); setAddMenuOpen(false) },
              className: 'block w-full px-2 py-1 text-left text-[0.75rem] hover:bg-(--ui-control-hover-background)',
              style: { color: toAdd === p ? 'var(--ui-accent)' : 'var(--ui-text-secondary, var(--foreground))' },
              children: meta[p].name || p,
            })),
          }) : null,
        ] }),
        jsx(Button, { variant: 'outline', size: 'icon-xs', className: 'shrink-0 h-7 w-7 items-center justify-center', disabled: !toAdd, onClick: addProvider, title: 'add provider', children: jsx(Codicon, { name: 'add', size: '0.8rem' }) }),
      ] })
    : null

  return jsxs('div', { className: 'flex flex-col gap-3', style: { fontSize: '0.8125rem' },
    children: [
      banner,
      addRow,
      variant === 'hermes'
        ? jsx('div', { ref: flipRef, className: 'overflow-hidden rounded-lg border border-(--stroke-nous) divide-y divide-(--ui-stroke-secondary)', children: rows })
        : jsx('div', { ref: flipRef, className: 'flex flex-col gap-2', children: rows }),
    ] })
}

// ── plugin registration ───────────────────────────────────────────

const PLUGIN_ID = 'provider-status'

export default {
  id: PLUGIN_ID,
  name: 'Provider Status',
  description: 'Unified multi-provider usage bars in the statusbar with a setup modal.',

  register(ctx) {
    _rest = ctx.rest // plugin-scoped REST door to /api/plugins/provider-status (auth handled)

  // Theme fixes: native <select> popups ignore inherited colors and render
  // light-on-light in dark mode; the SDK checkbox checked fill (bg-primary) is
  // near-white in dark mode and reads harsh. Both are scoped to this plugin.
  const STYLE_ID = 'provider-status-theme-fix'
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = `
    select[data-ps-select] option {
      background: var(--ui-bg-elevated, var(--background, inherit));
      color: var(--ui-text-secondary, var(--foreground));
    }
    [data-slot="checkbox"][data-state="checked"],
    [data-slot="checkbox"][data-state="indeterminate"] {
      background: color-mix(in srgb, var(--ui-accent, var(--foreground)) 55%, transparent) !important;
      border-color: color-mix(in srgb, var(--ui-accent, var(--foreground)) 70%, transparent) !important;
      color: var(--ui-text-primary, var(--foreground)) !important;
    }
  `
  document.head.appendChild(style)
  ctx.onDispose(() => document.getElementById(STYLE_ID)?.remove())


    // Statusbar group — compact chips for all enabled providers.
    // ErrorBoundary keeps a render failure contained to this slot; the gear
    // contribution below is separate and can never be replaced by an error.
    ctx.register({
      id: 'bars',
      area: STATUSBAR_AREAS.right,
      order: 50,
      render: () => jsx(PluginErrorBoundary, { children: jsx(StatusBarGroup, {}) }),
    })

    // Old card-style GearMenu is parked (function kept). Hermes-style dialog is the live gear.
    ctx.register({
      id: 'gear',
      area: STATUSBAR_AREAS.right,
      order: 210,
      render: () => jsx(PluginErrorBoundary, { children: jsx(ExpGearMenu, {}) }),
    })
  },
}
