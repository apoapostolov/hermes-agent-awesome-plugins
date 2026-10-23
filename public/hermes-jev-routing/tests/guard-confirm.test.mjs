// Core's model guard belongs to the user. This loads the shipped
// desktop/plugin.js with stubbed SDK and React imports, so the test drives the
// real applyChoice / confirmPick flow rather than a copy of it.
// Run: node --test tests/guard-confirm.test.mjs
import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const source = readFileSync(join(here, '..', 'desktop', 'plugin.js'), 'utf8')

const PRELUDE = `
export const __host = { request: async () => ({}), submit: () => {} }
export const __calls = { request: [], submit: [] }
let __store = null
const COMPOSER_AREAS = { underside: 'underside' }
const jsx = (type, props, key) => ({ type, props, key })
const jsxs = jsx
const useState = (initial) => {
  if (__store === null && initial !== null && initial !== undefined) __store = initial
  return [__store, (next) => { __store = next }]
}
const useEffect = (fn) => { fn() }
const host = {
  state: { focusedSessionId: { get: () => 'sess-1' } },
  request: async (op, args) => {
    __calls.request.push({ op, args })
    return __host.request(op, args)
  },
  composer: {
    submit: (...args) => {
      __calls.submit.push(args)
      return __host.submit(...args)
    },
  },
}
`

const body = source
  .split('\n')
  .filter((line) => !/^import\s/.test(line))
  .join('\n')

const mod = await import(`data:text/javascript;base64,${Buffer.from(PRELUDE + body).toString('base64')}`)

const EVENT = 'plugin.hermes-jev-routing.routed'

function wire() {
  mod.__calls.request.length = 0
  mod.__calls.submit.length = 0
  mod.__host.request = async () => ({})
  mod.__host.submit = () => {}
  let contribution = null
  let handler = null
  const plugin = mod.default
  plugin.register({
    register: (item) => { contribution = item },
    onEvent: (name, fn) => {
      if (name === EVENT) handler = fn
      return () => {}
    },
    onDispose: () => () => {},
  })
  // Mount the strip once so its listener is registered, the way the app mounts
  // the contribution before any routed event arrives.
  expand(contribution.render().type({}))
  return {
    contribution,
    emit: (payload) => handler({ payload }),
    render: () => expand(contribution.render().type({})),
    calls: mod.__calls,
  }
}

// The stub jsx keeps component types as plain nodes, so inline them the way a
// renderer would: a function type is called with its props.
function expand(node) {
  if (Array.isArray(node)) return node.map(expand)
  if (!node || typeof node !== 'object') return node
  const props = node.props || {}
  const children = expand(props.children)
  if (typeof node.type === 'function') return expand(node.type({ ...props, children }))
  return { ...node, props: { ...props, children } }
}

function textOf(node) {
  if (node === null || node === undefined || node === false) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textOf).join('')
  if (node.props) return textOf(node.props.children)
  return ''
}

function buttons(node, out = []) {
  if (!node || typeof node !== 'object') return out
  if (Array.isArray(node)) {
    node.forEach((child) => buttons(child, out))
    return out
  }
  if (node.type === 'button') out.push(node)
  if (node.props) buttons(node.props.children, out)
  return out
}

function label(button) {
  return textOf(button.props.children)
}

async function until(check, what) {
  for (let i = 0; i < 100; i += 1) {
    if (check()) return
    await new Promise((resolve) => setTimeout(resolve, 5))
  }
  throw new Error(`timed out waiting for ${what}`)
}

function acquirePayload(over = {}) {
  return {
    session_id: 'sess-1',
    line: '> tier premium · openai-codex/gpt-6-sol',
    apply: false,
    interrupt: true,
    offered_tier: 'premium',
    provider: 'openai-codex',
    model: 'gpt-6-sol',
    thinking: 'high',
    owed_prompt: 'ship the fix',
    heads: { standard: { provider: 'opencode-go', model: 'glm-5.3', thinking: 'medium' } },
    ...over,
  }
}

const GUARD = { confirm_required: true, confirm_message: 'gpt-6-sol is an expensive model.' }

test('a user pick shows the guard message and resends only after Confirm', async () => {
  const w = wire()
  mod.__host.request = async (op, args) => (args.confirm_expensive_model ? {} : GUARD)

  w.emit(acquirePayload())
  let tree = w.render()
  assert.ok(textOf(tree).includes('Approve:'), 'strip renders the approve row')

  const yes = buttons(tree).find((button) => label(button) === 'Yes, premium')
  assert.ok(yes, 'Yes button is offered')
  yes.props.onClick()

  await until(
    () => buttons(w.render()).some((button) => label(button) === 'Confirm gpt-6-sol'),
    'the confirm choice',
  )
  assert.equal(w.calls.request.length, 1, 'the guard is not answered with a silent resend')
  assert.equal(w.calls.request[0].args.confirm_expensive_model, undefined)

  const asked = w.render()
  assert.ok(textOf(asked).includes('gpt-6-sol is an expensive model.'), 'confirm_message reaches the strip')
  const confirm = buttons(asked).find((button) => label(button) === 'Confirm gpt-6-sol')
  assert.ok(buttons(asked).some((button) => label(button) === 'Cancel'), 'a cancel choice is offered')
  assert.equal(w.calls.request.length, 1, 'still nothing resent before the click')

  confirm.props.onClick()
  await until(() => w.calls.request.length === 3, 'the confirmed model set and the reasoning set')
  assert.deepEqual(w.calls.request.map((call) => call.args.key), ['model', 'model', 'reasoning'])
  assert.equal(w.calls.request[1].args.confirm_expensive_model, true)
  assert.equal(w.calls.request[2].args.value, 'high')
  assert.deepEqual(w.calls.submit, [['sess-1', 'ship the fix']], 'the owed prompt is resubmitted after the click')
  assert.ok(!textOf(w.render()).includes('Confirm gpt-6-sol'), 'the confirm row clears')
})

test('an automatic apply never answers the guard and stays on the current model', async () => {
  const w = wire()
  mod.__host.request = async () => GUARD

  w.emit(acquirePayload({ apply: true, interrupt: false }))
  await until(() => w.calls.request.length === 1, 'the automatic config.set')
  await new Promise((resolve) => setTimeout(resolve, 20))

  assert.equal(w.calls.request.length, 1, 'the automatic path never retries')
  assert.equal(w.calls.request[0].args.confirm_expensive_model, undefined)
  assert.equal(w.calls.submit.length, 0, 'the held prompt is not resubmitted')

  const tree = w.render()
  assert.ok(textOf(tree).includes('gpt-6-sol is an expensive model.'), 'the message is surfaced')
  assert.ok(!buttons(tree).some((button) => label(button).startsWith('Confirm ')), 'no confirm choice without a click')
})

test('cancel leaves the session on its current model', async () => {
  const w = wire()
  mod.__host.request = async (op, args) => (args.confirm_expensive_model ? {} : GUARD)

  w.emit(acquirePayload())
  buttons(w.render()).find((button) => label(button) === 'Yes, premium').props.onClick()
  await until(() => buttons(w.render()).some((button) => label(button) === 'Cancel'), 'the cancel choice')

  const cancel = buttons(w.render()).find((button) => label(button) === 'Cancel')
  cancel.props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 20))

  assert.equal(w.calls.request.length, 1, 'cancel sends nothing')
  assert.equal(w.calls.submit.length, 0, 'cancel does not resubmit the prompt')
  assert.ok(!textOf(w.render()).includes('expensive model'), 'the confirm row clears')
})
