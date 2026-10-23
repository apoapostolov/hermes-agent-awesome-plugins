/**
 * The Jev line renders in the composer underside strip.
 *
 * The listing edition uses the sanctioned composer contribution area: one line
 * under the input for the turn that was just routed, plus the approve row when
 * the weight wants another model. Nothing here reads or writes app-owned nodes,
 * so the desktop surface check stays inside the plugin SDK.
 */
import { COMPOSER_AREAS, host } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useState } from 'react'

const EVENT = 'plugin.hermes-jev-routing.routed'

let current = null
const listeners = new Set()

function publish(next) {
  current = next
  listeners.forEach((fn) => fn())
}

function payloadOf(frame) {
  if (!frame || typeof frame !== 'object') return null
  return frame.payload && typeof frame.payload === 'object' ? frame.payload : frame
}

function runtimeSessionId(payload) {
  const focused = host.state && host.state.focusedSessionId && typeof host.state.focusedSessionId.get === 'function'
    ? host.state.focusedSessionId.get()
    : ''
  return focused || payload.session_id || ''
}

function modelSet(payload, pick) {
  const sessionId = runtimeSessionId(payload)
  if (!sessionId || !pick) return null
  return {
    session_id: sessionId,
    key: 'model',
    value: `${pick.model} --provider ${pick.provider}`,
  }
}

// The rest of a pick, once the session is on the accepted model.
async function settle(payload, pick) {
  const sessionId = runtimeSessionId(payload)
  if (!sessionId || !pick) return
  if (pick.thinking) {
    await host.request('config.set', {
      session_id: sessionId,
      key: 'reasoning',
      value: String(pick.thinking),
    })
  }
  // A held turn was interrupted before it sent, so the approved prompt still
  // owes an answer. Resubmit it once the session is on the accepted model.
  const owed = payload.owed_prompt
  if (owed && typeof host.composer?.submit === 'function') {
    host.composer.submit(sessionId, owed)
  }
}

function guardMessage(result, pick) {
  const text = result && typeof result.confirm_message === 'string' ? result.confirm_message : ''
  return text || `Confirm ${pick.model}?`
}

// Core guards an expensive, data-policy, or large-context model. Answering that
// guard here would approve it for the user, so leave the session on its current
// model and let the strip ask. `auto` is the payload.apply path, which has no
// click behind it: surface the message and never send the confirmation.
async function applyChoice(payload, pick, auto) {
  const body = modelSet(payload, pick)
  if (!body) return
  const result = await host.request('config.set', body)
  if (result && result.confirm_required) {
    const message = guardMessage(result, pick)
    publish({ ...payload, interrupt: false, confirm: auto ? { message } : { message, pick } })
    return
  }
  await settle(payload, pick)
}

async function confirmPick(payload) {
  const pending = payload.confirm
  if (!pending || !pending.pick) return
  const body = modelSet(payload, pending.pick)
  if (!body) return
  const result = await host.request('config.set', { ...body, confirm_expensive_model: true })
  if (result && result.confirm_required) {
    // A second guard question stays with the user rather than being answered.
    publish({ ...payload, interrupt: false, confirm: { message: guardMessage(result, pending.pick), pick: pending.pick } })
    return
  }
  publish({ ...payload, interrupt: false, confirm: null })
  await settle(payload, pending.pick)
}

function cancelPick(payload) {
  publish({ ...payload, interrupt: false, confirm: null })
}

const WRAP = {
  fontSize: '0.6875rem',
  lineHeight: '1.25rem',
  color: 'color-mix(in oklab, var(--ui-text-tertiary, var(--foreground)) 70%, transparent)',
  padding: '0 0.5rem',
}

const ROW = { display: 'flex', flexWrap: 'wrap', alignItems: 'baseline' }

function choiceStyle(bold) {
  return {
    font: 'inherit',
    lineHeight: 'inherit',
    padding: 0,
    border: 0,
    background: 'transparent',
    cursor: 'pointer',
    color: bold ? 'var(--ui-text-primary, var(--foreground))' : 'inherit',
    fontWeight: bold ? 600 : 400,
  }
}

function Choice({ label, bold, onClick }) {
  return jsx('button', { type: 'button', onClick, style: choiceStyle(bold), children: label })
}

function JevLine() {
  const [payload, setPayload] = useState(current)

  useEffect(() => {
    const sync = () => setPayload(current)
    listeners.add(sync)
    sync()
    return () => {
      listeners.delete(sync)
    }
  }, [])

  if (!payload || typeof payload.line !== 'string' || !payload.line) return null

  const dismiss = () => publish({ ...payload, interrupt: false })
  const pick = (target) => {
    dismiss()
    applyChoice(payload, target)
  }
  const offered = payload.offered_tier || 'premium'
  const heads = payload.heads || {}
  const kinds = payload.kinds || {}
  const kindNames = Object.keys(kinds)
  const otherTiers = Object.keys(heads).filter((tier) => tier !== offered)

  const row = [
    jsx(Choice, { label: 'Approve:', bold: true, onClick: dismiss }, 'approve'),
    jsx('span', { children: ' ' }, 'gap-one'),
    jsx(Choice, {
      label: `Yes, ${offered}`,
      onClick: () => pick({ provider: payload.provider, model: payload.model, thinking: payload.thinking }),
    }, 'yes'),
  ]
  row.push(jsx('span', { children: ' \u00b7 ' }, 'gap-two'))
  row.push(jsx(Choice, { label: 'No', onClick: dismiss }, 'no'))
  if (payload.free) {
    row.push(jsx('span', { children: ' \u00b7 ' }, 'gap-free'))
    row.push(jsx(Choice, { label: 'Free', onClick: () => pick(payload.free) }, 'free'))
  }
  otherTiers.forEach((tier, index) => {
    row.push(jsx('span', { children: ' \u00b7 ' }, `gap-tier-${index}`))
    row.push(jsx(Choice, { label: tier, onClick: () => pick(heads[tier]) }, `tier-${tier}`))
  })

  if (kindNames.length) {
    const kindRow = []
    kindNames.forEach((kind) => {
      kindRow.push(jsx(Choice, { label: kind, onClick: () => pick(kinds[kind]) }, `kind-${kind}`))
      kindRow.push(jsx('span', { children: ' ' }, `kind-gap-${kind}`))
    })
    kindRow.push(jsx(Choice, { label: 'X', onClick: dismiss }, 'x-kind'))
    row.push(jsx('span', { style: { flexBasis: '100%' }, children: kindRow }, 'kinds'))
  } else {
    row.push(jsx('span', { children: ' \u00b7 ' }, 'gap-x'))
    row.push(jsx(Choice, { label: 'X', onClick: dismiss }, 'x'))
  }

  const confirm = payload.confirm && typeof payload.confirm.message === 'string' ? payload.confirm : null
  const confirmRow = []
  if (confirm) {
    confirmRow.push(jsx('span', { children: `${confirm.message} ` }, 'confirm-message'))
    if (confirm.pick) {
      confirmRow.push(jsx(Choice, {
        label: `Confirm ${confirm.pick.model}`,
        bold: true,
        onClick: () => confirmPick(payload),
      }, 'confirm-yes'))
      confirmRow.push(jsx('span', { children: ' \u00b7 ' }, 'confirm-gap'))
      confirmRow.push(jsx(Choice, { label: 'Cancel', onClick: () => cancelPick(payload) }, 'confirm-no'))
    }
  }

  return jsxs('div', {
    style: { ...WRAP, whiteSpace: 'normal' },
    children: [
      jsx('div', { style: { whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }, children: payload.line }, 'line'),
      payload.interrupt ? jsx('div', { style: ROW, children: row }, 'row') : null,
      confirm ? jsx('div', { style: ROW, children: confirmRow }, 'confirm') : null,
    ],
  })
}

export default {
  id: 'hermes-jev-routing',
  name: 'Jev Routing',
  description: 'Shows the Jev line for the turn that was just routed, under the composer.',

  register(ctx) {
    publish(null)

    ctx.register({
      id: 'jev-line',
      area: COMPOSER_AREAS.underside,
      order: 10,
      render: () => jsx(JevLine, {}),
    })

    const off = typeof ctx.onEvent === 'function'
      ? ctx.onEvent(EVENT, (frame) => {
          const payload = payloadOf(frame)
          if (!payload || typeof payload.line !== 'string') return
          publish(payload)
          if (payload.apply) {
            // The automatic path has no click behind it, so it may apply a pick
            // but it never answers core's model guard (third argument).
            applyChoice(payload, { provider: payload.provider, model: payload.model, thinking: payload.thinking }, true)
          }
        })
      : null

    ctx.onDispose(() => {
      if (typeof off === 'function') off()
      listeners.clear()
      current = null
    })
  },
}
