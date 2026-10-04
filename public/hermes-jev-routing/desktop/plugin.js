/**
 * After a user prompt, mount the Jev line under that prompt.
 * The confirm strip sits under the line only when the weight wants a different model.
 */
import { host } from '@hermes/plugin-sdk'

const EVENT = 'plugin.hermes-jev-routing.routed'

function payloadOf(frame) {
  if (!frame || typeof frame !== 'object') return null
  return frame.payload && typeof frame.payload === 'object' ? frame.payload : frame
}

function latestUserRoot() {
  const nodes = document.querySelectorAll('[data-slot="aui_user-message-root"]')
  return nodes.length ? nodes[nodes.length - 1] : null
}

function clearStrips() {
  document.querySelectorAll('[data-jev-strip]').forEach((node) => node.remove())
}

function button(label, bold, onClick) {
  const el = document.createElement('button')
  el.type = 'button'
  if (bold) {
    const strong = document.createElement('span')
    strong.dataset.strong = '1'
    strong.textContent = label
    el.appendChild(strong)
  } else {
    el.textContent = label
  }
  el.addEventListener('click', onClick)
  return el
}

function dot() {
  const el = document.createElement('span')
  el.textContent = '·'
  el.dataset.dot = '1'
  return el
}

async function applyChoice(payload, pick) {
  const sessionId = payload.session_id || ''
  if (!sessionId || !pick) return
  const request = (confirmExpensive) =>
    host.request('config.set', {
      session_id: sessionId,
      key: 'model',
      value: `${pick.model} --provider ${pick.provider}`,
      ...(confirmExpensive ? { confirm_expensive_model: true } : {}),
    })
  let result = await request(false)
  if (result && result.confirm_required) result = await request(true)
  if (pick.thinking) {
    await host.request('config.set', {
      session_id: sessionId,
      key: 'reasoning',
      value: String(pick.thinking),
    })
  }
}

function mountStatus(payload) {
  const stack = document.querySelector('[data-slot="composer-status-stack"]')
  if (!stack || !payload.status) return
  let chip = stack.querySelector('[data-jev-status]')
  if (!chip) {
    chip = document.createElement('span')
    chip.dataset.jevStatus = '1'
    stack.appendChild(chip)
  }
  chip.textContent = payload.status
}

function rememberLine(payload) {
  if (!payload.prompt || !payload.line) return
  const key = 'hermes-jev-routing-lines'
  const rows = JSON.parse(sessionStorage.getItem(key) || '[]')
  const next = [{ prompt: payload.prompt, line: payload.line }, ...rows.filter((row) => row.prompt !== payload.prompt)].slice(0, 20)
  sessionStorage.setItem(key, JSON.stringify(next))
}

function reattach() {
  const raw = sessionStorage.getItem('hermes-jev-routing-lines')
  if (!raw) return
  const rows = JSON.parse(raw)
  document.querySelectorAll('[data-slot="aui_user-message-root"]').forEach((user) => {
    const text = (user.textContent || '').slice(0, 80)
    const row = rows.find((item) => text && item.prompt && text.includes(item.prompt.slice(0, 24)))
    if (!row || user.parentNode.querySelector(':scope > [data-jev-routing]')) return
    const block = document.createElement('div')
    block.dataset.jevRouting = '1'
    block.dataset.jevStored = '1'
    const line = document.createElement('div')
    line.dataset.jevLine = '1'
    line.textContent = row.line
    block.appendChild(line)
    user.insertAdjacentElement('afterend', block)
  })
}

function mount(payload) {
  const user = latestUserRoot()
  if (!user || !user.parentNode) return
  clearStrips()
  let block = user.parentNode.querySelector(':scope > [data-jev-routing]')
  if (!block || block.previousElementSibling !== user) {
    block = document.createElement('div')
    block.dataset.jevRouting = '1'
    user.insertAdjacentElement('afterend', block)
  }
  block.replaceChildren()
  const line = document.createElement('div')
  line.dataset.jevLine = '1'
  line.textContent = payload.line
  block.appendChild(line)
  if (!payload.interrupt) return
  const strip = document.createElement('div')
  strip.dataset.jevStrip = '1'
  const offered = payload.offered_tier || 'premium'
  const yes = button('Yes', true, () => {
    applyChoice(payload, { provider: payload.provider, model: payload.model, thinking: payload.thinking })
    strip.remove()
  })
  const yesTail = document.createElement('span')
  yesTail.textContent = `, ${offered}`
  yes.appendChild(yesTail)
  strip.append(yes, dot(), button('No', false, () => strip.remove()))
  if (payload.free) {
    strip.append(
      dot(),
      button('Free', false, () => {
        applyChoice(payload, payload.free)
        strip.remove()
      }),
    )
  }
  const heads = payload.heads || {}
  for (const tier of Object.keys(heads)) {
    if (tier === offered) continue
    strip.append(
      dot(),
      button(tier, false, () => {
        applyChoice(payload, heads[tier])
        strip.remove()
      }),
    )
  }
  strip.append(
    dot(),
    button('X', true, () => strip.remove()),
  )
  block.appendChild(strip)
}

export default {
  id: 'hermes-jev-routing',
  name: 'Jev Routing',
  description: 'Shows the Jev line under the prompt that was just sent.',
  register(ctx) {
    const off = typeof ctx.onEvent === 'function'
      ? ctx.onEvent(EVENT, (frame) => {
          const payload = payloadOf(frame)
          if (!payload || typeof payload.line !== 'string') return
          mount(payload)
          mountStatus(payload)
          rememberLine(payload)
        })
      : null
    ctx.onDispose(() => {
      if (typeof off === 'function') off()
      document.querySelectorAll('[data-jev-routing]').forEach((node) => node.remove())
      style.remove()
    })
    const style = document.createElement('style')
    style.textContent = `
      [data-jev-routing] {
        font-size: 0.6875rem;
        line-height: 1.25rem;
        color: color-mix(in srgb, var(--muted-foreground) 60%, transparent);
        padding: 0 0.5rem;
        white-space: pre-line;
      }
      [data-jev-strip] { display: flex; align-items: baseline; white-space: nowrap; }
      [data-jev-strip] button {
        font: inherit; line-height: inherit; color: inherit;
        background: transparent; border: 0; padding: 0; cursor: pointer;
      }
      [data-jev-strip] [data-strong] { font-weight: 600; color: var(--foreground); }
      [data-jev-strip] [data-dot] { padding: 0 0.35rem; color: color-mix(in srgb, var(--muted-foreground) 35%, transparent); }
      [data-jev-status] {
        font-size: 0.6875rem;
        line-height: 1.25rem;
        color: color-mix(in srgb, var(--muted-foreground) 60%, transparent);
        padding: 0 0.5rem;
      }
    `
    document.head.appendChild(style)
    reattach()
    const observer = new MutationObserver(() => reattach())
    observer.observe(document.body, { childList: true, subtree: true })
    ctx.onDispose(() => observer.disconnect())
  },
}
