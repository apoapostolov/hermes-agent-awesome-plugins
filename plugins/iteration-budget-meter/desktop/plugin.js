/**
 * Iteration Budget Meter — statusbar chip showing the FOCUSED SESSION's
 * per-turn iteration usage (N/60) while a turn runs, with a one-line hover
 * tooltip and a click popover for recent turn peaks and the last cap-forced
 * summary.
 *
 * Data source (pure renderer, no backend, no polling, no writes):
 *   - "is a turn running" -> host.state.busy
 *   - raw counter         -> host.state.focusedUsage.calls
 *
 * v1.1.0 FIX (was 1.0.0, cron build): focusedUsage.calls is
 * session_api_calls — CUMULATIVE for the whole session, never reset per
 * turn. 1.0.0 displayed it raw, so after the cap the chip kept counting up
 * across turns (70/60, 90/60). The real per-turn budget
 * (agent.iteration_budget) is NOT in the usage payload, so the delta is
 * computed renderer-side: every idle observation records the cumulative
 * counter as the baseline, and the chip displays max(0, calls - baseline)
 * during the next turn. A defensive clamp (calls < baseline -> rebaseline)
 * keeps session switches from ever showing a bogus number. The chip can
 * therefore never display the cumulative counter.
 */
import { cn, host, Tip as Tooltip, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import * as React from 'react'
import { useEffect, useRef, useState } from 'react'

const CAP = 60
const AMBER_AT = 45
const ACCENT = 'var(--ui-accent)'
const AMBER = '#f59e0b' // same warn tone the app's status dot uses
const RED = '#ef4444'

// Module-scoped history, kept across chip mounts for the life of the window.
// `_peaks` holds the last 10 completed turns' observed peak count (oldest->newest).
const _peaks = []
const MAX_PEAKS = 10
let _lastCapHitAt = 0 // ms epoch when this chip first observed a turn reach the cap

function pushPeak(v) {
  _peaks.push(v)
  if (_peaks.length > MAX_PEAKS) _peaks.shift()
}

function fmtWhen(ms) {
  if (!ms) return 'never'
  const d = new Date(ms)
  const today = new Date()
  const sameDay = d.toDateString() === today.toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return sameDay ? 'today, ' + time : d.toLocaleDateString() + ' ' + time
}

function IterBudgetChip() {
  const busy = useValue(host.state.busy)
  const usage = useValue(host.state.focusedUsage)
  // Bumping this re-renders the chip so the popover re-reads module history
  // (turn peaks, last cap-hit) on click and on each turn boundary.
  const [, bump] = useState(0)

  const wasBusy = useRef(false)
  const peak = useRef(0)
  // Cumulative session counter observed at the last turn boundary (idle).
  // Null until the first observation; set while idle, clamped while running.
  const base = useRef(null)

  useEffect(() => {
    const isBusy = !!busy
    const calls = usage && typeof usage.calls === 'number' && usage.calls >= 0 ? usage.calls : null

    if (!isBusy) {
      // Turn just ended: record this turn's peak BEFORE rebaselining.
      if (wasBusy.current) {
        const finalDelta = base.current !== null && calls !== null ? Math.max(0, calls - base.current) : peak.current
        if (finalDelta > 0) pushPeak(finalDelta)
        peak.current = 0
        bump(Date.now())
      }
      // Idle: whatever the focused session shows now IS the next turn's zero.
      if (calls !== null) base.current = calls
    } else {
      if (!wasBusy.current) {
        peak.current = 0 // fresh turn
        bump(Date.now())
      }
      if (calls !== null) {
        // Rebaseline on session switch / first mount (prevents negatives and
        // cumulative leaks); never let the display run backwards.
        if (base.current === null || calls < base.current) base.current = calls
        const delta = calls - base.current
        if (delta > peak.current) peak.current = delta
        if (delta >= CAP && !_lastCapHitAt) _lastCapHitAt = Date.now()
      }
    }
    wasBusy.current = isBusy
  }, [busy, usage])

  // Hidden while idle — the chip only exists during a running turn.
  if (!busy) return null

  const calls = usage && typeof usage.calls === 'number' && usage.calls >= 0 ? usage.calls : null
  const n = base.current !== null && calls !== null ? Math.max(0, calls - base.current) : null
  const atCap = n !== null && n >= CAP
  const warn = n !== null && n >= AMBER_AT
  const color = atCap ? RED : warn ? AMBER : ACCENT

  const countText = n === null ? '–' : String(n)
  const dot = ' \u00b7\u00a0' // breakable before the dot, NBSP after (label won't wrap here)
  // One line, middle-dot separators: 'iteration budget · 52/60 · this turn · cap 60'
  const label = 'iteration budget' + dot + countText + '/60' + dot + 'this turn' + dot + 'cap 60'

  const peak10 = _peaks.length ? Math.max(..._peaks.slice(-10)) : null

  return jsx(Popover, {
    children: [
      jsx(PopoverTrigger, {
        children: jsx(Tooltip, {
          label,
          children: jsx('button', {
            type: 'button',
            title: 'iteration budget details',
            className: cn(
              'inline-flex h-full items-center rounded-none px-1.5 text-[0.6875rem] font-medium',
              'hover:bg-(--chrome-action-hover) hover:text-foreground'
            ),
            style: { color },
            onClick: () => bump(Date.now()), // refresh only this chip's details
            children: jsxs(Fragment, {
              children: [
                jsx('i', {
                  className: 'codicon codicon-debug-restart',
                  'aria-hidden': 'true',
                  style: { fontSize: '12px', marginRight: '3px', opacity: 0.9 },
                }),
                jsx('span', { children: countText + '/60' }),
              ],
            }),
          }),
        }),
      }),
      jsx(PopoverContent, {
        side: 'top',
        align: 'end',
        className: 'min-w-[15rem] p-3 text-[0.75rem]',
        children: jsxs(Fragment, {
          children: [
            jsxs('div', {
              className: 'text-[0.8125rem] font-medium',
              children: [
                'Iterations used this turn: ',
                jsx('span', { style: { color }, children: countText + ' of 60' }),
              ],
            }),
            jsx('div', {
              className: 'mt-1 text-(--ui-text-tertiary)',
              children:
                peak10 !== null
                  ? 'Highest of the last 10 turns: ' + peak10 + ' of 60'
                  : 'No finished turns recorded yet.',
            }),
            jsx('div', {
              className: 'mt-1 text-(--ui-text-tertiary)',
              children: 'Last time the cap forced a summary: ' + fmtWhen(_lastCapHitAt),
            }),
            atCap
              ? jsx('div', {
                  className: 'mt-2 text-[0.6875rem]',
                  style: { color: RED },
                  children: 'At the cap — the model is asked to summarise and wrap up.',
                })
              : null,
            jsx('div', {
              className: 'mt-2 text-[0.6875rem] text-(--ui-text-quaternary)',
              children: 'Counts this turn only. Resets when a new turn starts.',
            }),
          ],
        }),
      }),
    ],
  })
}

export default {
  id: 'iteration-budget-meter',
  name: 'Iteration Budget Meter',
  description: 'Shows the live per-turn iteration budget (N/60) of the running turn in the status bar.',

  register(ctx) {
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 205,
      render: () => jsx(IterBudgetChip, {}),
    })
  },
}
