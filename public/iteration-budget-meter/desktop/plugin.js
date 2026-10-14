/**
 * Iteration Budget Meter — statusbar chip showing the FOCUSED SESSION's
 * cumulative totals ("12 turns · 181 steps", the same counters the CLI bar
 * keeps), with a one-line hover tooltip and a click popover carrying the
 * per-turn readout and per-request stats.
 *
 * Data source:
 *   - session totals  -> `session.resume` RPC (durable display transcript;
 *     user rows -> turns, assistant rows -> steps — the same count the
 *     sessions table keeps), re-anchored on session switches and turn
 *     boundaries. Light payloads only (`inline_images: false`); falls back
 *     to the live runtime usage counters.
 *   - live step delta -> host.state.focusedUsage.calls while a turn runs
 *     (display = fetched base + delta since the fetch anchor, so it stays
 *     correct whether or not the runtime counter survives restarts).
 *
 * v1.3.1: the live step count anchors at the running turn's start (a
 * mid-turn fetch never reads 0 steps), and the chip stays plain — the
 * per-turn warning color lives in the popover only.
 * v1.3.0: the chip switched from the per-turn counter to the session's
 * cumulative totals — the per-turn readout stays in the popover. Loads are
 * race-proofed (settle delay, timeout, idle-safe retries; the chip stays
 * hidden until totals land), session switches and fresh drafts never bleed
 * across, and the chrome matches the native statusbar items.
 * v1.2.2: every observed busy->idle edge is a per-round boundary, and focused
 * session changes reset the baseline before the next usage sample.
 * v1.2.1: chained-continuation fix. The gateway emits message.complete and a
 * busy dip between chained segments of one logical request (goal follow-ups,
 * queued drains, auto-continue), which reset the counter mid-request.
 * v1.2.0: popover redesigned — average tool calls per request, ratio of
 * requests hitting the max, and a ceiling suggestion derived from both
 * (see ceilingSuggestion).
 */
import { cn, host, Tip as Tooltip, Popover, PopoverContent, PopoverTrigger, useValue } from '@hermes/plugin-sdk'
import { Fragment, jsx, jsxs } from 'react/jsx-runtime'
import * as React from 'react'
import { useEffect, useRef, useState } from 'react'

const CAP = 60
const AMBER_AT = 45

// PET_HELPERS_START
let _pet = null
let _petLast = ''
let _petAt = 0

function turnPetPayload(n, busy) {
  if (!busy || n === null || n < 1) return null
  const tone = n >= CAP ? 'error' : n >= AMBER_AT ? 'wait' : 'info'
  return { text: n + '/' + CAP, tone }
}

function pushTurnPet(n, busy) {
  const pet = _pet
  if (!pet || typeof pet.say !== 'function') return
  const payload = turnPetPayload(n, busy)
  if (!payload) {
    if (_petLast) {
      _petLast = ''
      if (typeof pet.clear === 'function') pet.clear('turn')
    }
    return
  }
  if (pet.visible && typeof pet.visible.get === 'function' && !pet.visible.get()) return
  const key = payload.tone + '\0' + payload.text
  const now = Date.now()
  const prevTone = _petLast.split('\0')[0]
  const escalate = (prevTone === 'info' && payload.tone !== 'info') || (prevTone === 'wait' && payload.tone === 'error')
  if (key === _petLast) return
  if (!escalate && _petAt && now - _petAt < 1200) return
  _petLast = key
  _petAt = now
  pet.say(payload.text, { id: 'turn', tone: payload.tone, ttlMs: 8000 })
}
// PET_HELPERS_END
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
  const storedId = useValue(host.state.focusedStoredSessionId)
  const previousSessionId = useRef(null)
  const hasSession = useRef(false)
  const wasBusy = useRef(false)
  const peak = useRef(0)
  // Cumulative session counter observed at the current round's start.
  const base = useRef(null)
  // Session-level stats cache (turns / steps) + fetch bookkeeping.
  const stats = useRef({ key: null, stored: null, runtime: null, turns: null, stepsBase: null, stepsAnchor: null, fetchedAt: 0, retryAt: 0, retryTimer: null, inflight: false, gen: 0, pending: null })
  // Drop cached totals (session switch / fresh draft / retry housekeeping).
  const resetStats = () => {
    const s = stats.current

    if (s.retryTimer) { clearTimeout(s.retryTimer); s.retryTimer = null }
    s.key = null
    s.stored = null
    s.runtime = null
    s.turns = null
    s.stepsBase = null
    s.stepsAnchor = null
    s.fetchedAt = 0
    s.retryAt = 0
    // Orphan any in-flight fetch so it can neither block nor overwrite the
    // new session's totals.
    s.gen += 1
    s.inflight = false
    s.pending = null
  }
  // Fetch session totals via the gateway: `session.resume` returns the
  // durable display transcript (user rows -> turns) plus, when present,
  // `info.usage.calls` (cumulative steps). Falls back to `session.usage`.
  const refreshStats = (stored, runtime, liveCalls, force) => {
    const st = stats.current

    if (!stored) return
    // Latest request wins: queue it and re-run once the current fetch ends.
    if (st.inflight) { st.pending = { stored, runtime, liveCalls }; return }

    const now = Date.now()

    if (!force && st.retryAt && now < st.retryAt) return
    if (!force && st.key === stored && now - st.fetchedAt < 2000) return
    const gen = st.gen

    st.inflight = true
    st.key = stored
    st.stored = stored
    st.runtime = runtime

    ;(async () => {
      try {
        // Let the desktop's own resume win the attach race (cold sessions).
        await new Promise((resolve) => setTimeout(resolve, 900))
        if (st.gen !== gen || st.key !== stored) return // switched during settle — abort
        const res = await host.request('session.resume', { session_id: stored, inline_images: false }, 8000)
        const messages = res && Array.isArray(res.messages) ? res.messages : []

        // A payload with no rows for a non-empty session is not ready yet.
        if (messages.length === 0 && res && res.message_count > 0) throw new Error('transcript pending')
        const turns = messages.filter((m) => m && m.role === 'user').length
        // Steps = assistant rows in the durable display transcript (one per
        // model call); monotonic across runtime restarts and compactions.
        let steps = messages.length ? messages.filter((m) => m && m.role === 'assistant').length : null

        if (steps === null && res && res.info && res.info.usage && typeof res.info.usage.calls === 'number') {
          steps = res.info.usage.calls
        }

        if (steps === null && runtime) {
          try {
            const u = await host.request('session.usage', { session_id: runtime }, 5000)

            if (u && typeof u.calls === 'number') steps = u.calls
          } catch (_e2) { /* keep null */ }
        }
        if (st.gen !== gen || st.key !== stored) return // switched mid-fetch — drop
        st.turns = turns
        st.stepsBase = steps
        // Anchor the live delta at the RUNNING turn's start. The display
        // transcript carries completed turns only, so a fetch landing mid-turn
        // (cold retry, catch-up, queued pending) must count this turn's
        // iterations from its first busy tick — anchoring at the fetch moment
        // reads 0 steps for a turn that is already underway.
        const busyNow = !!host.state.busy.get()
        const anchor = busyNow && base.current !== null ? base.current : liveCalls

        st.stepsAnchor = typeof anchor === 'number' ? anchor : null
        st.retryAt = 0
        if (st.retryTimer) { clearTimeout(st.retryTimer); st.retryTimer = null }
      } catch (_e) {
        if (st.gen !== gen) return // orphaned by a session switch
        // Keep last known values; retry soon — a timer covers the idle case
        // where no turn edge would otherwise re-trigger the fetch.
        st.retryAt = Date.now() + 3000
        st.key = null
        if (st.retryTimer) clearTimeout(st.retryTimer)
        st.retryTimer = setTimeout(() => {
          const s = stats.current

          if (!s.inflight && s.stored) {
            const live = host.state.focusedUsage.get()

            refreshStats(s.stored, s.runtime, live && typeof live.calls === 'number' ? live.calls : null)
          }
        }, 3200)
      } finally {
        if (st.gen === gen) {
          st.fetchedAt = Date.now()
          st.inflight = false
          const next = st.pending

          st.pending = null
          if (next) refreshStats(next.stored, next.runtime, next.liveCalls, true)
          bump(Date.now())
        }
      }
    })()
  }

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
      // A different session gets its own numbers — drop the old ones so the
      // chip never shows another session's totals (hidden until fetched).
      resetStats()
      refreshStats(storedId, sessionId, calls)
      bump(Date.now())
      return
    }
    previousSessionId.current = sessionId
    hasSession.current = true
    // Fresh draft (no session yet): nothing to count — clear, so a stale
    // session's totals never linger under an empty chat.
    if (!storedId && (stats.current.key !== null || stats.current.stored !== null)) {
      resetStats()
      bump(Date.now())
    }
    // Mount / switch catch-up: fetch once per new session (edges retry).
    if (storedId && (stats.current.key !== storedId || stats.current.fetchedAt === 0)) {
      refreshStats(storedId, sessionId, calls)
    }

    if (!isBusy) {
      if (wasBusy.current) {
        // Every observed idle edge closes one normal round. This deliberately
        // resets goal, queue, loop, and auto-continue segments independently.
        if (peak.current > 0) pushPeak(peak.current)
        peak.current = 0
        if (calls !== null) base.current = calls
        refreshStats(storedId, sessionId, calls, true)
        bump(Date.now())
      } else if (calls !== null) {
        // Idle usage may arrive after message.complete. Keep the next round's
        // baseline at the latest settled cumulative value.
        base.current = calls
      }
    } else if (calls !== null) {
      if (!wasBusy.current) refreshStats(storedId, sessionId, calls)
      if (base.current === null || calls < base.current) {
        base.current = calls
        peak.current = 0
      }
      const delta = calls - base.current
      if (delta > peak.current) peak.current = delta
    }
    wasBusy.current = isBusy
  }, [busy, usage, sessionId, storedId])

  const calls = usage && typeof usage.calls === 'number' && usage.calls >= 0 ? usage.calls : null
  const n = base.current !== null && calls !== null ? Math.max(0, calls - base.current) : null
  const atCap = n !== null && n >= CAP
  const warn = n !== null && n >= AMBER_AT
  const color = atCap ? RED : warn ? AMBER : null
  const countText = n === null ? '–' : String(n)

  // Session totals (the CLI bar's counters): turns from the last transcript
  // fetch; steps = fetched base + live delta since the fetch anchor.
  const st = stats.current
  let stepsTotal = null

  if (st.stepsBase !== null) {
    const delta = st.stepsAnchor !== null && calls !== null ? Math.max(0, calls - st.stepsAnchor) : 0

    stepsTotal = st.stepsBase + delta
  } else if (calls !== null) {
    stepsTotal = calls
  }

  const turnsTotal = st.turns

  useEffect(() => {
    pushTurnPet(n, !!busy)
  }, [n, busy])
  useEffect(() => () => {
    if (_pet && typeof _pet.clear === 'function') _pet.clear('turn')
    _petLast = ''
  }, [])

  const turnsText = turnsTotal === null ? '–' : String(turnsTotal)
  const stepsText = stepsTotal === null ? '–' : String(stepsTotal)

  // Loaded only: no placeholder while a session's totals are being fetched
  // (fresh drafts and cold sessions stay hidden until their numbers land).
  if (turnsTotal === null) return null

  const dot = ' \u00b7\u00a0' // breakable before the dot, NBSP after (label won't wrap here)
  const label = 'session totals' + dot + turnsText + ' turns' + dot + stepsText + ' steps'

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
            title: 'session stats details',
            className: cn(
              'inline-flex h-full items-center gap-1 rounded-none px-1.5 text-[0.6875rem] text-(--ui-text-tertiary) transition-colors',
              'hover:bg-(--chrome-action-hover) hover:text-foreground'
            ),
            onClick: () => bump(Date.now()), // refresh only this chip's details
            children: jsxs(Fragment, {
              children: [
                jsx('i', {
                  className: 'codicon codicon-pulse',
                  'aria-hidden': 'true',
                  style: { fontSize: '12px', opacity: 0.9 },
                }),
                jsx('span', { children: turnsText + ' turns · ' + stepsText + ' steps' }),
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
              children: ['Session totals: ', jsx('span', { children: turnsText + ' turns · ' + stepsText + ' steps' })],
            }),
            jsxs('div', {
              className: 'mt-1 text-[0.8125rem] font-medium',
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
  description: 'Shows the focused session totals — cumulative turns and steps — plus per-turn iteration details.',

  register(ctx) {
    _pet = ctx.pet && typeof ctx.pet.say === 'function' ? ctx.pet : null
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 205,
      render: () => jsx(IterBudgetChip, {}),
    })
  },
}
