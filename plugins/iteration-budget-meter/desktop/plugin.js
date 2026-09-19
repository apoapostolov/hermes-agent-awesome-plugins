/**
 * Iteration Budget Meter — statusbar chip showing the FOCUSED SESSION's
 * per-turn iteration usage (N/60) while a turn runs, with a one-line hover
 * tooltip and a click popover with per-request stats.
 *
 * Data source (pure renderer, no backend, no polling, no writes):
 *   - "is a turn running" -> host.state.busy
 *   - raw counter         -> host.state.focusedUsage.calls
 *
 * v1.2.0: popover redesigned — average tool calls per request, ratio of
 * requests hitting the max, and a ceiling suggestion derived from both
 * (see ceilingSuggestion).
 * v1.2.1: chained-continuation fix. The gateway emits message.complete and a
 * busy dip between chained segments of one logical request (goal follow-ups,
 * queued drains, auto-continue), which reset the counter mid-request.
 * v1.2.2: every observed busy->idle edge is a per-round boundary, and focused
 * session changes reset the baseline before the next usage sample.
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

// Module-scoped per-request history (oldest->newest), kept across chip mounts
// for the life of the window. Feeds the popover's average / hit-ratio /
// ceiling-suggestion stats.
const _turnPeaks = []
const MAX_TURNS = 30
const MIN_SAMPLE_FOR_SUGGESTION = 5 // finished requests before suggesting a ceiling
const MIN_HITS = 2 // ...and the cap must have been hit at least twice
const MIN_HIT_RATIO = 0.2 // suggest only when >= 20% of requests hit the cap
const MIN_AVG_FRAC = 0.5 // ...and the average is at least half the cap

function pushPeak(v) {
  _turnPeaks.push(v)
  if (_turnPeaks.length > MAX_TURNS) _turnPeaks.shift()
}

function fmtPct(r) {
  return (r * 100).toFixed(2).replace(/\.00$/, '').replace(/(\.\d)0$/, '$1') + '%'
}

// Ceiling suggestion: the new cap must cover the observed average plus an
// allowance that grows with how often requests get truncated. Anchor case
// (Apo): avg 45/60 with ~30% of requests hitting the cap -> suggest 90.
//   need = max(avg * (2 - ratio), cap * (1 + ratio)); round UP to a multiple
//   of 15; suggest only when the result exceeds the current cap.
function ceilingSuggestion(peaks) {
  const n = peaks.length
  if (n < MIN_SAMPLE_FOR_SUGGESTION) return null
  const avg = peaks.reduce((a, b) => a + b, 0) / n
  const hits = peaks.filter((p) => p >= CAP).length
  const ratio = hits / n
  if (hits < MIN_HITS || ratio < MIN_HIT_RATIO || avg < CAP * MIN_AVG_FRAC) return null
  const need = Math.max(avg * (2 - ratio), CAP * (1 + ratio))
  const suggested = Math.ceil(need / 15) * 15
  return suggested > CAP ? suggested : null
}

function IterBudgetChip() {
  const busy = useValue(host.state.busy)
  const usage = useValue(host.state.focusedUsage)
  // Bumping this re-renders the chip so the popover re-reads module history
  // (per-request stats) on click and on each turn boundary.
  const [, bump] = useState(0)

  const sessionId = useValue(host.state.focusedSessionId)
  const previousSessionId = useRef(null)
  const hasSession = useRef(false)
  const wasBusy = useRef(false)
  const peak = useRef(0)
  // Cumulative session counter observed at the current round's start.
  const base = useRef(null)

  useEffect(() => {
    const isBusy = !!busy
    const calls = usage && typeof usage.calls === 'number' && usage.calls >= 0 ? usage.calls : null
    const sessionChanged = hasSession.current && previousSessionId.current !== sessionId

    // A focused-session change is a hard boundary. Never compare cumulative
    // usage from one session with the baseline of another session.
    if (sessionChanged) {
      if (peak.current > 0) pushPeak(peak.current)
      base.current = calls
      peak.current = 0
      wasBusy.current = isBusy
      previousSessionId.current = sessionId
      hasSession.current = true
      bump(Date.now())
      return
    }
    previousSessionId.current = sessionId
    hasSession.current = true

    if (!isBusy) {
      if (wasBusy.current) {
        // Every observed idle edge closes one normal round. This deliberately
        // resets goal, queue, loop, and auto-continue segments independently.
        if (peak.current > 0) pushPeak(peak.current)
        peak.current = 0
        if (calls !== null) base.current = calls
        bump(Date.now())
      } else if (calls !== null) {
        // Idle usage may arrive after message.complete. Keep the next round's
        // baseline at the latest settled cumulative value.
        base.current = calls
      }
    } else if (calls !== null) {
      if (base.current === null || calls < base.current) {
        base.current = calls
        peak.current = 0
      }
      const delta = calls - base.current
      if (delta > peak.current) peak.current = delta
    }
    wasBusy.current = isBusy
  }, [busy, usage, sessionId])

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

  // Per-request stats over the recorded window.
  const nDone = _turnPeaks.length
  const avg = nDone ? Math.round(_turnPeaks.reduce((a, b) => a + b, 0) / nDone) : null
  const hits = nDone ? _turnPeaks.filter((p) => p >= CAP).length : 0
  const ratio = nDone ? hits / nDone : null
  const suggest = ceilingSuggestion(_turnPeaks)

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
                  className: 'codicon codicon-tools',
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
        className: 'w-max max-w-[24rem] p-3 text-[0.75rem]',
        children: jsxs(Fragment, {
          children: [
            jsxs('div', {
              className: 'text-[0.8125rem] font-medium',
              children: [
                'Iterations used this turn: ',
                jsx('span', { style: { color }, children: countText + ' of 60' }),
              ],
            }),
            nDone === 0
              ? jsx('div', {
                  className: 'mt-1 text-(--ui-text-tertiary)',
                  children: 'No finished requests recorded yet.',
                })
              : jsxs(Fragment, {
                  children: [
                    jsxs('div', {
                      className: 'mt-1',
                      children: [
                        'Average tool calls per request: ',
                        jsx('span', { className: 'font-medium', children: String(avg) }),
                      ],
                    }),
                    jsxs('div', {
                      className: 'mt-1 whitespace-nowrap',
                      children: [
                        'Max tool calls requests: ',
                        jsx('span', {
                          className: 'font-medium',
                          children: fmtPct(ratio) + ' (' + hits + ' of ' + nDone + ')',
                        }),
                      ],
                    }),
                    suggest !== null
                      ? jsxs('div', {
                          className: 'mt-1 whitespace-nowrap',
                          style: { color: ACCENT },
                          children: [
                            jsx('i', {
                              className: 'codicon codicon-light-bulb',
                              'aria-hidden': 'true',
                              style: { fontSize: '12px', marginRight: '4px' },
                            }),
                            'Consider increasing tool calls to: ',
                            jsx('span', { className: 'font-medium', children: '~' + suggest }),
                          ],
                        })
                      : null,
                    jsx('div', {
                      className: 'mt-1 text-[0.6875rem] text-(--ui-text-quaternary)',
                      children:
                        'Based on the last ' + nDone + ' finished request' + (nDone === 1 ? '' : 's') + '.',
                    }),
                  ],
                }),
            atCap
              ? jsx('div', {
                  className: 'mt-2 text-[0.6875rem]',
                  style: { color: RED },
                  children: 'At the cap — the model is asked to summarise and wrap up.',
                })
              : null,
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
