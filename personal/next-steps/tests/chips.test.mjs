// Renderer harness for desktop/plugin.js: no app, no React, no dependencies.
//
// The plugin only needs three imports (TRANSCRIPT_DIRECTIVE_AREA, host, jsx), so
// this test writes tiny stub packages into a temp dir, copies the plugin in as
// ESM, and drives the directive renderer directly. Components are plain functions
// under the stubs, so calling one gives an element tree we can assert on.
//
//   node tests/chips.test.mjs
import { mkdtempSync, mkdirSync, writeFileSync, copyFileSync, rmSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import assert from 'node:assert/strict'

const here = dirname(fileURLToPath(import.meta.url))
const pluginSource = resolve(here, '..', 'desktop', 'plugin.js')
const dir = mkdtempSync(join(tmpdir(), 'next-steps-test-'))
const nm = join(dir, 'node_modules')

function pkg(name, files) {
  const root = join(nm, name)
  mkdirSync(root, { recursive: true })
  for (const [file, body] of Object.entries(files)) {
    writeFileSync(join(root, file), body)
  }
}

pkg('@hermes/plugin-sdk', {
  'package.json': JSON.stringify({ name: '@hermes/plugin-sdk', type: 'module', main: 'index.js' }),
  'index.js': [
    "export const TRANSCRIPT_DIRECTIVE_AREA = 'transcript.directives'",
    '// The test mutates this object the way the app would provide it.',
    'export const host = { composer: { submit: () => false }, notify: () => {}, request: null, state: null }',
    "export const Checkbox = 'Checkbox'",
    "export const Input = 'Input'",
  ].join('\n'),
})

// Minimal hooks: state is kept per call order so a component can be called again
// and see the values the last call produced, which is enough for one flat tree.
pkg('react', {
  'package.json': JSON.stringify({
    name: 'react',
    type: 'module',
    main: 'index.js',
    exports: { '.': './index.js', './jsx-runtime': './jsx-runtime.js' },
  }),
  'index.js': [
    'const states = new Map()',
    'const effectDeps = new Map()',
    'const cleanups = []',
    'let cursor = 0',
    'let effectCursor = 0',
    'export function __reset() {',
    '  cursor = 0',
    '  effectCursor = 0',
    '  states.clear()',
    '  effectDeps.clear()',
    '  while (cleanups.length) { const c = cleanups.pop(); try { c() } catch (e) {} }',
    '}',
    'export function useState(initial) {',
    '  const slot = cursor++',
    '  if (!states.has(slot)) states.set(slot, typeof initial === "function" ? initial() : initial)',
    '  const set = (next) => { states.set(slot, typeof next === "function" ? next(states.get(slot)) : next) }',
    '  return [states.get(slot), set]',
    '}',
    '// Effects run on the spot, honouring deps the way React would on a mount.',
    'export function useEffect(fn, deps) {',
    '  const slot = effectCursor++',
    '  const key = deps ? JSON.stringify(deps) : null',
    '  if (deps && effectDeps.get(slot) === key) return',
    '  effectDeps.set(slot, key)',
    '  const cleanup = fn()',
    '  if (typeof cleanup === "function") cleanups.push(cleanup)',
    '}',
  ].join('\n'),
  'jsx-runtime.js': [
    'export function jsx(type, props, key) { return { type, props: props || {}, key } }',
    'export const jsxs = jsx',
    'export const Fragment = "Fragment"',
  ].join('\n'),
})

writeFileSync(join(dir, 'package.json'), JSON.stringify({ type: 'module' }))
const entry = join(dir, 'plugin.mjs')
copyFileSync(pluginSource, entry)

const sdk = await import(pathToFileURL(join(nm, '@hermes/plugin-sdk', 'index.js')).href)
const react = await import(pathToFileURL(join(nm, 'react', 'index.js')).href)
const plugin = (await import(pathToFileURL(entry).href)).default

/* ---- a renderer: expand function components into element trees ---------- */
function render(node) {
  if (node == null || typeof node !== 'object') return node
  if (Array.isArray(node)) return node.map(render)
  if (typeof node.type === 'function') {
    react.__reset()
    return render(node.type(node.props))
  }
  const props = Object.assign({}, node.props)
  if (props.children != null) props.children = render(props.children)
  return { type: node.type, props, key: node.key }
}

function roots(el) {
  // A chips block is a div whose children are chip buttons, then an optional footer
  // row holding the send button and the cleanup. Flattened here so a case can talk
  // about the block in order without caring which row wraps what.
  assert.equal(el.type, 'div')
  const out = []
  for (const child of el.props.children) {
    if (child && child.props && child.props.className === 'fu-footer') {
      const inner = child.props.children
      out.push(...(Array.isArray(inner) ? inner : [inner]))
    } else out.push(child)
  }
  return out
}

function footerRow(el) {
  return (el.props.children || []).find((c) => c && c.props && c.props.className === 'fu-footer') || null
}

function cleanButton(el) {
  const row = footerRow(el)
  if (!row) return null
  return row.props.children.find((c) => c && c.props.className === 'fu-clean') || null
}

function chips(el) {
  return roots(el).filter((c) => c.props.className.indexOf('fu-send') === -1)
}

function send(el) {
  return roots(el).find((c) => c.props.className.indexOf('fu-send') !== -1)
}

function steer(el) {
  return roots(el).find((c) => c && c.props.className && c.props.className.indexOf('fu-steer') !== -1)
}

function label(el) {
  if (typeof el.props.children === 'string') return el.props.children
  const first = el.props.children[0]
  if (first == null || typeof first !== 'object') return first
  let inner = first.props.children
  // A chip body is [tick span, text span], or [row span, subtitle] when the option
  // carries a second line; only what is visible counts, so an unpicked chip reads as
  // its text and a picked one keeps the ✓.
  if (Array.isArray(inner) && inner[0] && inner[0].props && Array.isArray(inner[0].props.children)) {
    inner = inner[0].props.children
  }
  if (Array.isArray(inner)) {
    return inner
      .filter((part) => !(part && part.props && part.props.className === 'fu-sub'))
      .filter((part) => !(part && part.props && part.props.style && part.props.style.visibility === 'hidden'))
      .map((part) => (part && typeof part === 'object' ? part.props.children : part))
      /* The tick and the label are separate cells joined by a gap, so the reading is
         spelled with a space even though the glyph no longer carries one. */
      .join(' ')
  }
  return inner
}

/* The chip's second line, or undefined when the option carries no subtitle. */
function subtitle(el) {
  const body = el.props.children[0]
  const kids = body && body.props && body.props.children
  if (!Array.isArray(kids)) return undefined
  const sub = kids.find((k) => k && k.props && k.props.className === 'fu-sub')
  return sub ? sub.props : undefined
}

function tickReserved(el) {
  const label = el.props.children[0]
  const inner = label && label.props && label.props.children
  if (!Array.isArray(inner)) return false
  /* Nested one level: a chip with a subtitle wraps the tick in a grid, so the children
     array sits inside the label span rather than directly on it. */
  const walk = (parts) =>
    parts.some((part) => {
      if (!part || !part.props) return false
      if (part.props.children === '✓') return true
      return Array.isArray(part.props.children) ? walk(part.props.children) : false
    })
  return walk(inner)
}

function badge(el) {
  const mark = el.props.children.find(
    (child) => child && typeof child === 'object' && child.props && child.props.children === 'Recommended'
  )
  return mark ? mark.props : null
}

/* ---- harness state ------------------------------------------------------ */
const submits = []
sdk.host.composer.submit = (sessionId, text) => {
  submits.push([sessionId, text])
  return true
}
sdk.host.notify = (n) => submits.push(['notify', n])

const store = new Map()
const events = {}
let directive = null
plugin.register({
  storage: {
    get: (key, fallback) => (store.has(key) ? structuredClone(store.get(key)) : fallback),
    set: (key, value) => store.set(key, structuredClone(value)),
  },
  onEvent: (name, fn) => {
    ;(events[name] = events[name] || []).push(fn)
  },
  register: (contribution) => {
    directive = contribution
  },
})

assert.equal(directive.id, 'nextsteps', 'registers the nextsteps directive')
assert.equal(directive.area, 'transcript.directives', 'registers into the transcript area')
const register = directive.data.render

const results = []
const cases = []
function test(name, fn) {
  /* Run every case in registration order below. Firing them all at load time used
     to mark an async case ok before its post-await assertions ran, and concurrent
     async cases also shared the host stubs, so one case's await let the next case
     change the arrays under it. */
  cases.push([name, fn])
}

/* ---- single select: unchanged behaviour --------------------------------- */
test('multi="0" sends on one click and shows no send button', () => {
  submits.length = 0
  const el = render(
    register({ attrs: { multi: '0', q1: 'Push it?', q2: 'Tag it?' }, sessionId: 's1', source: 'src-a' })
  )
  assert.equal(chips(el).length, 2)
  assert.equal(send(el), undefined, 'single select has no send button')
  chips(el)[1].props.onClick()
  assert.deepEqual(submits, [['s1', 'Tag it?']])
})

test('multi="0" marks the chosen chip and settles on message.complete', () => {
  const attrs = { multi: '0', q1: 'Push it?', q2: 'Tag it?' }
  let el = render(register({ attrs, sessionId: 's2', source: 'src-b' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 's2', source: 'src-b' }))
  assert.match(chips(el)[0].props.className, /fu-chosen/)
  assert.match(chips(el)[0].props.className, /fu-running/)
  assert.equal(label(chips(el)[0]), '✓ Push it?')
  events['message.complete'][0]('s2')
  el = render(register({ attrs, sessionId: 's2', source: 'src-b' }))
  assert.doesNotMatch(chips(el)[0].props.className, /fu-running/)
})

/* ---- multi select ------------------------------------------------------- */
test('multi renders a disabled send button until something is picked', () => {
  const el = render(
    register({ attrs: { multi: '1', q1: 'A', q2: 'B', q3: 'C' }, sessionId: 'm1', source: 'src-m1' })
  )
  assert.equal(chips(el).length, 3)
  const button = send(el)
  assert.ok(button, 'multi select shows a send button')
  assert.equal(button.props.disabled, true)
  assert.equal(label(button), 'Send')
})

test('multi chip click toggles instead of sending', () => {
  submits.length = 0
  const attrs = { multi: '1', q1: 'Add docs', q2: 'Add a test', q3: 'Bump' }
  let el = render(register({ attrs, sessionId: 'm2', source: 'src-m2' }))
  chips(el)[0].props.onClick()
  assert.equal(submits.length, 0, 'nothing is sent on a chip click')
  el = render(register({ attrs, sessionId: 'm2', source: 'src-m2' }))
  assert.equal(label(chips(el)[0]), '✓ Add docs')
  assert.equal(chips(el)[0].props['aria-pressed'], true)
  assert.equal(chips(el)[1].props['aria-pressed'], false, 'other chips stay unpressed')
  assert.equal(send(el).props.disabled, false)
  assert.equal(label(send(el)), 'Send 1')
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 'm2', source: 'src-m2' }))
  assert.equal(label(chips(el)[0]), 'Add docs', 'a second click un-picks')
  assert.equal(send(el).props.disabled, true)
})

test('multi send carries every pick in q order as one turn', () => {
  submits.length = 0
  const attrs = { multi: '1', q1: 'Add docs', q2: 'Add a test', q3: 'Bump' }
  let el = render(register({ attrs, sessionId: 'm3', source: 'src-m3' }))
  chips(el)[2].props.onClick()
  el = render(register({ attrs, sessionId: 'm3', source: 'src-m3' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 'm3', source: 'src-m3' }))
  assert.equal(label(send(el)), 'Send 2')
  send(el).props.onClick()
  assert.deepEqual(submits, [['m3', 'Add docs\nBump']], 'one message, picks in q order')
})

test('a sent block cannot be picked again and keeps its marks', () => {
  submits.length = 0
  const attrs = { multi: '1', q1: 'A', q2: 'B' }
  let el = render(register({ attrs, sessionId: 'm4', source: 'src-m4' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 'm4', source: 'src-m4' }))
  send(el).props.onClick()
  el = render(register({ attrs, sessionId: 'm4', source: 'src-m4' }))
  assert.equal(label(send(el)), '✓ Sent')
  assert.equal(send(el).props.disabled, true)
  chips(el)[1].props.onClick()
  el = render(register({ attrs, sessionId: 'm4', source: 'src-m4' }))
  assert.equal(label(chips(el)[1]), 'B', 'no picking after the turn was sent')
})

test('picks persist across a reload from ctx.storage', () => {
  const attrs = { multi: '1', q1: 'A', q2: 'B' }
  const saved = store.get('choices')
  const key = Object.keys(saved).find((k) => k.indexOf('src-m4') !== -1)
  assert.ok(key, 'the block has a stored entry')
  assert.deepEqual(saved[key].picked, [0])
  assert.equal(saved[key].sent, true)
})

test('a failed submit warns instead of marking the block', () => {
  sdk.host.composer.submit = () => false
  submits.length = 0
  const attrs = { multi: '1', q1: 'A', q2: 'B' }
  let el = render(register({ attrs, sessionId: 'm5', source: 'src-m5' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 'm5', source: 'src-m5' }))
  send(el).props.onClick()
  assert.equal(submits[0][0], 'notify')
  el = render(register({ attrs, sessionId: 'm5', source: 'src-m5' }))
  assert.equal(label(send(el)), 'Send 1', 'the block stays unsent')
  sdk.host.composer.submit = (sessionId, text) => {
    submits.push([sessionId, text])
    return true
  }
})

test('multi accepts 1/true/yes/on, and 0/false/no/off opts out', () => {
  for (const flag of ['1', 'true', 'yes', 'on', true]) {
    const el = render(register({ attrs: { multi: flag, q1: 'A', q2: 'B' }, sessionId: 'f', source: 'src-' + flag }))
    assert.ok(send(el), 'pickable via ' + JSON.stringify(flag))
  }
  for (const flag of ['0', 'false', 'no', 'off', false]) {
    const el = render(register({ attrs: { multi: flag, q1: 'A', q2: 'B' }, sessionId: 'x', source: 'src-x-' + flag }))
    assert.equal(send(el), undefined, 'one-click via ' + JSON.stringify(flag))
  }
})

test('two chips are pickable when the directive says nothing', () => {
  submits.length = 0
  const attrs = { q1: 'Push the branch', q2: 'Tag a release' }
  let el = render(register({ attrs, sessionId: 'd1', source: 'src-d1' }))
  assert.ok(send(el), 'a plain two-option block shows the send button')
  chips(el)[0].props.onClick()
  assert.equal(submits.length, 0, 'the click picks instead of sending')
  el = render(register({ attrs, sessionId: 'd1', source: 'src-d1' }))
  assert.equal(label(send(el)), 'Send 1')
})

test('one chip has nothing to pick, so it sends on one click', () => {
  submits.length = 0
  const el = render(register({ attrs: { q1: 'Only option' }, sessionId: 'd2', source: 'src-d2' }))
  assert.equal(send(el), undefined, 'no send button for a single chip')
  chips(el)[0].props.onClick()
  assert.deepEqual(submits, [['d2', 'Only option']])
})

test('q order is numeric, not lexicographic', () => {
  const attrs = { multi: '1', q10: 'Tenth', q2: 'Second', q1: 'First' }
  const el = render(register({ attrs, sessionId: 'o', source: 'src-order' }))
  assert.deepEqual(
    chips(el).map((c) => label(c)),
    ['First', 'Second', 'Tenth']
  )
})

test('an empty directive renders nothing', () => {
  assert.equal(render(register({ attrs: { multi: '1' }, sessionId: 'e', source: 'empty' })), null)
})

/* ---- recommended options ------------------------------------------------ */
const recAttrs = { multi: '1', rec: '1,3', q1: 'Push it', q2: 'Tag it', q3: 'Write the notes' }

test('rec pre-picks the recommended chips and tags them', () => {
  const el = render(register({ attrs: recAttrs, sessionId: 'r1', source: 'src-r1' }))
  assert.equal(label(chips(el)[0]), '✓ Push it')
  assert.equal(chips(el)[0].props['aria-pressed'], true)
  assert.ok(badge(chips(el)[0]), 'recommended chip carries the tag')
  assert.equal(chips(el)[1].props['aria-pressed'], false, 'unrecommended chip stays unmarked')
  assert.equal(badge(chips(el)[1]), null)
  assert.ok(badge(chips(el)[2]))
  assert.equal(label(send(el)), 'Send 2')
})

test('un-ticking a recommended chip is never undone by the defaults', () => {
  const first = render(register({ attrs: recAttrs, sessionId: 'r2', source: 'src-r2' }))
  assert.equal(label(send(first)), 'Send 2')
  chips(first)[0].props.onClick()
  const second = render(register({ attrs: recAttrs, sessionId: 'r2', source: 'src-r2' }))
  assert.equal(label(chips(second)[0]), 'Push it', 'the unticked chip stays unticked')
  assert.equal(label(send(second)), 'Send 1')
})

test('a stored block does not re-seed its recommended picks on reload', () => {
  const first = render(register({ attrs: recAttrs, sessionId: 'r3', source: 'src-r3' }))
  chips(first)[1].props.onClick()
  const second = render(register({ attrs: recAttrs, sessionId: 'r3', source: 'src-r3' }))
  assert.equal(label(send(second)), 'Send 3')
  const stored = store.get('choices')['r3::src-r3']
  assert.equal(stored.touched, true, 'the block is marked as used')
  assert.deepEqual(stored.picked, [0, 1, 2])
})

test('multi="0" shows the tag but never pre-chooses', () => {
  const el = render(
    register({ attrs: { multi: '0', rec: '2', q1: 'Push it', q2: 'Tag it' }, sessionId: 'r4', source: 'src-r4' })
  )
  assert.equal(label(chips(el)[1]), 'Tag it', 'no ✓ before a click')
  assert.ok(badge(chips(el)[1]))
  assert.equal(send(el), undefined)
})

test('junk rec values are ignored instead of trusted', () => {
  for (const rec of ['0', '9', 'abc', '', '2,2', ' 1 ; 3 ']) {
    const el = render(register({ attrs: { multi: '1', rec, q1: 'A', q2: 'B', q3: 'C' }, sessionId: 'r5-' + rec, source: 'src-r5-' + rec }))
    const picked = chips(el).filter((c) => c.props['aria-pressed'] === true)
    assert.ok(picked.length <= 2, 'rec=' + JSON.stringify(rec) + ' picked ' + picked.length)
  }
})

/* ---- polish: accent tint and one width for the row ---------------------- */

test('a recommended chip is accented by default, even when it is not picked', () => {
  const el = render(
    register({ attrs: { multi: '0', rec: '2', q1: 'Push it', q2: 'Tag it' }, sessionId: 'p1', source: 'src-p1' })
  )
  const recommended = chips(el)[1]
  assert.ok(recommended.props.className.includes('fu-recommended'), 'recommended chip carries the accent class')
  assert.ok(/color-mix\(in srgb, var\(--dt-primary[\s\S]*70%/.test(recommended.props.style.border), 'accent border: ' + recommended.props.style.border)
  assert.ok(!chips(el)[0].props.className.includes('fu-recommended'), 'a plain chip is not accented')
})

test('accent="0" drops the tint but keeps the Recommended tag', () => {
  const el = render(
    register({ attrs: { multi: '0', rec: '2', accent: '0', q1: 'Push it', q2: 'Tag it' }, sessionId: 'p2', source: 'src-p2' })
  )
  assert.ok(!chips(el)[1].props.className.includes('fu-recommended'), 'no accent class at all')
  assert.ok(chips(el)[1].props.style.border.includes('ui-stroke-secondary'), 'neutral border')
  assert.equal(chips(el)[1].props.style.background, 'transparent')
  assert.ok(badge(chips(el)[1]), 'the tag stays')
  assert.ok(
    badge(chips(el)[1]).style.color.includes('ui-text-secondary'),
    'the tag goes neutral too: ' + badge(chips(el)[1]).style.color
  )
})

test('accent on, the tag carries the accent', () => {
  const el = render(register({ attrs: { rec: '1', q1: 'A', q2: 'B' }, sessionId: 'p2b', source: 'src-p2b' }))
  assert.ok(badge(chips(el)[0]).style.color.includes('--dt-primary'), 'accented tag: ' + badge(chips(el)[0]).style.color)
  assert.equal(badge(chips(el)[0]).style.marginLeft, 'auto', 'tags line up on the right edge')
})

test('accent accepts the same spellings as multi, and junk leaves it on', () => {
  for (const [value, wants] of [['0', false], ['false', false], ['off', false], ['1', true], ['yes', true], ['', true], ['nonsense', true]]) {
    const attrs = { rec: '1', accent: value, q1: 'A', q2: 'B' }
    const el = render(register({ attrs, sessionId: 'p3-' + value, source: 'src-p3-' + value }))
    const accented = chips(el)[0].props.className.includes('fu-recommended')
    assert.equal(accented, wants, 'accent=' + JSON.stringify(value))
  }
})

test('the tick slot is laid out on every chip so a pick cannot resize the row', () => {
  const el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'p4', source: 'src-p4' }))
  for (const chip of chips(el)) {
    assert.ok(tickReserved(chip), 'tick span present')
    assert.equal(label(chip), chip.props.title, 'no ✓ before a pick')
  }
  chips(el)[0].props.onClick()
  const after = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'p4', source: 'src-p4' }))
  assert.ok(tickReserved(chips(after)[0]), 'the slot survives the pick')
  assert.equal(label(chips(after)[0]), '✓ A')
  assert.equal(label(chips(after)[1]), 'B', 'the other chip keeps its own text')
})

test('the row is one grid column sized to the widest chip, with Send outside it', () => {
  const el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'A much longer option' }, sessionId: 'p5', source: 'src-p5' }))
  assert.equal(el.props.style.display, 'grid')
  assert.equal(el.props.style.gridTemplateColumns, 'minmax(0, max-content)')
  for (const chip of chips(el)) {
    assert.equal(chip.props.style.width, undefined, 'no per-chip width to fight the grid')
    assert.equal(chip.props.style.boxSizing, 'border-box')
  }
  assert.equal(send(el).props.style.justifySelf, 'start', 'Send keeps its own width')
})

/* ---- carry over: unanswered proposals follow their session --------------- */
function freshChips(el) {
  return roots(el).filter(
    (c) =>
      c &&
      c.props &&
      typeof c.props.className === 'string' &&
      c.props.className.indexOf('fu-chip') === 0 &&
      c.props.className.indexOf('fu-stale-row') === -1 &&
      c.props.className.indexOf('fu-send') === -1
  )
}

function staleRows(el) {
  return roots(el).filter((c) => c && c.props && c.props.className === 'fu-stale-row')
}

function staleButton(row) {
  return row.props.children[0]
}

function staleDismiss(row) {
  return row.props.children[1]
}

function staleLabels(el) {
  return staleRows(el).map((row) => label(staleButton(row)))
}

/* The age badge: "2 responses ago", and a jump button in its own right. */
function ageBadge(row) {
  return staleButton(row).props.children.find(
    (c) => c && typeof c === 'object' && c.props && c.props.className === 'fu-age'
  )
}

function ageText(row) {
  return ageBadge(row).props.children
}

test('carry: a reply that proposes nothing still shows the unanswered chips', () => {
  const s = 'carry-none'
  render(register({ attrs: { carry: '1', q1: 'Push it', q2: 'Tag it', q3: 'Write notes' }, sessionId: s, source: 'r1' }))
  const el = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'r2' }))
  assert.deepEqual(staleLabels(el), ['Push it', 'Tag it', 'Write notes'])
  assert.ok(staleRows(el).every((row) => ageBadge(row)), 'every carried chip says how old it is')
  assert.deepEqual(staleRows(el).map(ageText), ['1 response ago', '1 response ago', '1 response ago'])
  assert.equal(freshChips(el).length, 0, 'this reply proposed nothing of its own')
  assert.ok(cleanButton(el), 'a block showing only carried chips still offers the cleanup')
})

test('carry: the newest reply shows its own chips first, then the older ones', () => {
  const s = 'carry-mix'
  render(register({ attrs: { carry: '1', q1: 'Push the branch', q2: 'Tag a release', q3: 'Write the notes' }, sessionId: s, source: 'm1' }))
  render(register({ attrs: { carry: '1' }, sessionId: s, source: 'm2' }))
  const el = render(register({ attrs: { carry: '1', q1: 'Add a test', q2: 'Update the docs' }, sessionId: s, source: 'm3' }))
  assert.deepEqual(freshChips(el).map(label), ['Add a test', 'Update the docs'])
  assert.deepEqual(staleLabels(el), ['Push the branch', 'Tag a release', 'Write the notes'])
  assert.equal(freshChips(el).length + staleRows(el).length, 5, 'two new plus three stale')
})

test('carry: a carried chip sends exactly itself', () => {
  const s = 'carry-click'
  render(register({ attrs: { carry: '1', multi: '1', q1: 'A', q2: 'B' }, sessionId: s, source: 'k1' }))
  const el = render(register({ attrs: { carry: '1', multi: '1', q1: 'C' }, sessionId: s, source: 'k2' }))
  submits.length = 0
  staleButton(staleRows(el)[0]).props.onClick()
  assert.deepEqual(submits, [[s, 'A']])
})

test('carry: the X retires a proposal and a reload does not bring it back', () => {
  const s = 'carry-x'
  render(register({ attrs: { carry: '1', q1: 'A', q2: 'B' }, sessionId: s, source: 'x1' }))
  const el = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'x2' }))
  staleDismiss(staleRows(el)[0]).props.onClick()
  const after = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'x3' }))
  assert.deepEqual(staleLabels(after), ['B'], 'the dismissed one is gone')
  /* A reload re-mounts the original reply, which re-registers its own chips.
     The tombstone is what stops the dismissed chip coming back. */
  render(register({ attrs: { carry: '1', q1: 'A', q2: 'B' }, sessionId: s, source: 'x1' }))
  const reloaded = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'x4' }))
  assert.deepEqual(staleLabels(reloaded), ['B'], 're-registering does not resurrect it')
})

test('carry: answering a block retires its own proposals', () => {
  const s = 'carry-answer'
  /* Two chips are pickable by default, so answering means picking then sending. */
  const attrs = { carry: '1', q1: 'A', q2: 'B' }
  let first = render(register({ attrs, sessionId: s, source: 'a1' }))
  freshChips(first)[0].props.onClick()
  first = render(register({ attrs, sessionId: s, source: 'a1' }))
  send(first).props.onClick()
  /* Nothing is carried any more, so the next reply draws no chips line at all. */
  const next = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'a2' }))
  assert.equal(next, null, 'an answered reply is not carried')
})

test('carry: the send button sits below the carried chips, not above them', () => {
  const s = 'order-send'
  /* multi="1" spelled out: this slice predates pickable-by-default, and the point
     here is the order of the rows, not how the row became pickable. */
  render(
    register({ attrs: { carry: '1', multi: '1', q1: 'Fresh A', q2: 'Fresh B' }, sessionId: s, source: 'ord-a' })
  )
  const el = render(register({ attrs: { carry: '1', multi: '1', q1: 'Now A', q2: 'Now B' }, sessionId: s, source: 'ord-b' }))
  const classes = (el.props.children || []).filter(Boolean).map(function (c) {
    return c.props.className
  })
  /* This reply's own chips, then what it carries, then the footer: the button that
     answers them, and the cleanup that ends the row. */
  assert.deepEqual(classes, ['fu-chip', 'fu-chip', 'fu-stale-row', 'fu-stale-row', 'fu-footer'])
  const footer = (el.props.children || []).find((c) => c.props.className === 'fu-footer')
  assert.deepEqual(
    footer.props.children.map((c) => c.props.className),
    ['fu-chip fu-send', 'fu-chip fu-send fu-steer', 'fu-clean'],
    'the cleanup sits after the finalisation buttons, pushed to the end of the row'
  )
  assert.equal(footer.props.children[2].props.style.marginLeft, 'auto', 'right-aligned in that row')
})

test('carry: proposals never cross chats when the render prop is empty', () => {
  /* The shape that leaked: no sessionId prop, one sid per chat, both stamped. */
  render(register({ attrs: { carry: '1', sid: 'chat-a', q1: 'A1' }, source: 'x1' }))
  const other = render(register({ attrs: { carry: '1', sid: 'chat-b', q1: 'B1' }, source: 'x2' }))
  assert.equal(staleRows(other).length, 0, 'chat b carries nothing from chat a')

  const same = render(register({ attrs: { carry: '1', sid: 'chat-a' }, source: 'x3' }))
  assert.equal(staleRows(same).length, 1, 'chat a still carries its own')
})

test('carry: a block with no chat identity records and carries nothing', () => {
  render(register({ attrs: { carry: '1', q1: 'Loose A' }, source: 'n1' }))
  const el = render(register({ attrs: { carry: '1' }, source: 'n2' }))
  assert.equal(el, null, 'no identity means no queue, never a shared one')
})

test('carry: the sid wins over the render prop', () => {
  /* A stale prop must not pull another chat's queue in. */
  render(register({ attrs: { carry: '1', sid: 'chat-x', q1: 'X1' }, sessionId: 'prop-1', source: 'y1' }))
  const other = render(register({ attrs: { carry: '1', sid: 'chat-y' }, sessionId: 'prop-1', source: 'y2' }))
  assert.equal(other, null, 'chat y draws nothing rather than chat x queue')
  const same = render(register({ attrs: { carry: '1', sid: 'chat-x' }, sessionId: 'prop-1', source: 'y3' }))
  assert.equal(staleRows(same).length, 1)
})

test('carry: a block without the attribute ignores the queue', () => {
  const s = 'carry-off'
  render(register({ attrs: { carry: '1', q1: 'A' }, sessionId: s, source: 'o1' }))
  const el = render(register({ attrs: { q1: 'B' }, sessionId: s, source: 'o2' }))
  assert.equal(staleRows(el).length, 0)
})

test('carry: an empty queue draws no block at all', () => {
  const el = render(register({ attrs: { carry: '1' }, sessionId: 'carry-empty', source: 'e1' }))
  assert.equal(el, null, 'nothing to carry and nothing proposed means no chips line')
})

test('carry: proposals stay inside their own session', () => {
  render(register({ attrs: { carry: '1', q1: 'A' }, sessionId: 'carry-sess-a', source: 'p1' }))
  const other = render(register({ attrs: { carry: '1' }, sessionId: 'carry-sess-b', source: 'p2' }))
  assert.equal(other, null)
})

test('carry: the queue is capped and keeps the newest options', () => {
  const s = 'carry-cap'
  const many = { carry: '1' }
  for (let i = 1; i <= 33; i += 1) many['q' + i] = 'Option ' + i
  render(register({ attrs: many, sessionId: s, source: 'cap1' }))
  const el = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'cap2' }))
  const labels = staleRows(el).map((row) => label(staleButton(row)))
  assert.equal(labels.length, 30, 'keeps 30')
  assert.equal(labels[0], 'Option 4', 'the three oldest were retired; one reply keeps its own order')
  assert.equal(labels[labels.length - 1], 'Option 33')
})

test('carry: at the cap a recommended proposal is not retired', () => {
  const s = 'carry-rec'
  const many = { carry: '1', rec: '1,2,3' }
  for (let i = 1; i <= 33; i += 1) many['q' + i] = 'Option ' + i
  render(register({ attrs: many, sessionId: s, source: 'rc1' }))
  const el = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'rc2' }))
  const labels = staleRows(el).map((row) => label(staleButton(row)))
  assert.equal(labels.length, 30)
  assert.ok(labels.includes('Option 1'), 'the oldest recommended survives')
  assert.ok(labels.includes('Option 2'))
  assert.ok(labels.includes('Option 3'))
  assert.ok(!labels.includes('Option 4'), 'the oldest unmarked goes first')
  assert.ok(!labels.includes('Option 6'))
  assert.ok(labels.includes('Option 7'))
})

test('carry: once everything is recommended the oldest recommended retires', () => {
  const s = 'carry-allrec'
  const many = { carry: '1' }
  const all = []
  for (let i = 1; i <= 33; i += 1) {
    many['q' + i] = 'Option ' + i
    all.push(i)
  }
  many.rec = all.join(',')
  render(register({ attrs: many, sessionId: s, source: 'ar1' }))
  const el = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'ar2' }))
  const labels = staleRows(el).map((row) => label(staleButton(row)))
  assert.equal(labels.length, 30)
  assert.ok(!labels.includes('Option 1'), 'the oldest recommendation retires next')
  assert.ok(labels.includes('Option 33'), 'and the newest recommended is shown')
  assert.equal(labels[0], 'Option 4', 'one reply keeps its own order')
})


test('carry: the youngest reply sits on top and the oldest sinks to the bottom', () => {
  const s = 'carry-order'
  render(register({ attrs: { carry: '1', q1: 'Old A', q2: 'Old B' }, sessionId: s, source: 'r1' }))
  render(register({ attrs: { carry: '1' }, sessionId: s, source: 'r2' }))
  render(register({ attrs: { carry: '1', q1: 'Mid A' }, sessionId: s, source: 'r3' }))
  render(register({ attrs: { carry: '1' }, sessionId: s, source: 'r4' }))
  const el = render(register({ attrs: { carry: '1', q1: 'Now A' }, sessionId: s, source: 'r5' }))
  const rows = staleRows(el).map((row) => label(staleButton(row)))
  assert.deepEqual(rows, ['Mid A', 'Old A', 'Old B'], 'youngest reply first, oldest last, one reply in its own order')
  const ages = staleRows(el).map(ageText)
  assert.deepEqual(ages, ['2 responses ago', '4 responses ago', '4 responses ago'])
})

test('carry: the badge counts replies, not chips', () => {
  const s = 'carry-age'
  render(register({ attrs: { carry: '1', q1: 'A', q2: 'B' }, sessionId: s, source: 'g1' }))
  const second = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'g2' }))
  assert.deepEqual(staleRows(second).map(ageText), ['1 response ago', '1 response ago'])
  const third = render(register({ attrs: { carry: '1', q1: 'C' }, sessionId: s, source: 'g3' }))
  assert.deepEqual(staleRows(third).map(ageText), ['2 responses ago', '2 responses ago'])
})

test('carry: the age badge jumps to the offering reply and sends nothing', () => {
  const s = 'carry-jump'
  const first = render(register({ attrs: { carry: '1', q1: 'A' }, sessionId: s, source: 'j1' }))
  const originId = first.props.id
  assert.ok(/^fu-block-[a-z0-9]+-1$/.test(originId || ''), 'the offering block has a stable address')
  const el = render(register({ attrs: { carry: '1', q1: 'B' }, sessionId: s, source: 'j2' }))
  assert.notEqual(el.props.id, originId, 'each reply has its own address')
  const row = staleRows(el)[0]
  const badge = ageBadge(row)
  assert.equal(ageText(row), '1 response ago')

  const jumps = []
  globalThis.document = {
    getElementById: (id) => (id === originId ? { scrollIntoView: (opts) => jumps.push(opts) } : null),
    createElement: () => ({ id: '', textContent: '' }),
    head: { appendChild: () => {} },
  }
  submits.length = 0
  let stopped = false
  badge.props.onClick({ stopPropagation: () => { stopped = true } })
  delete globalThis.document

  assert.equal(stopped, true, 'the badge click never reaches the pill')
  assert.equal(submits.length, 0, 'jumping is not sending')
  assert.equal(jumps.length, 1, 'it scrolls the offering reply into view')
  assert.equal(jumps[0].block, 'center')
})

test('carry: a missing offering reply notifies instead of throwing', () => {
  const s = 'carry-gone'
  render(register({ attrs: { carry: '1', q1: 'A' }, sessionId: s, source: 'z1' }))
  const el = render(register({ attrs: { carry: '1', q1: 'B' }, sessionId: s, source: 'z2' }))
  globalThis.document = { getElementById: () => null, createElement: () => ({ id: '', textContent: '' }), head: { appendChild: () => {} } }
  submits.length = 0
  ageBadge(staleRows(el)[0]).props.onClick({ stopPropagation: () => {} })
  delete globalThis.document
  assert.equal(submits.length, 1)
  assert.equal(submits[0][0], 'notify')
})

test('carry: pressing the pill with the keyboard sends it, Enter and Space alike', () => {
  const s = 'carry-keys'
  render(register({ attrs: { carry: '1', q1: 'A' }, sessionId: s, source: 'y1' }))
  const el = render(register({ attrs: { carry: '1', q1: 'B' }, sessionId: s, source: 'y2' }))
  const pill = staleButton(staleRows(el)[0])
  assert.equal(pill.props.role, 'button')
  assert.equal(pill.props.tabIndex, 0)
  submits.length = 0
  let prevented = 0
  pill.props.onKeyDown({ key: 'Enter', preventDefault: () => { prevented += 1 } })
  pill.props.onKeyDown({ key: ' ', preventDefault: () => { prevented += 1 } })
  assert.deepEqual(submits, [[s, 'A'], [s, 'A']])
  assert.equal(prevented, 2, 'space must not also scroll the transcript')
})

/* ---- report ------------------------------------------------------------- */
/* Root plugin.js is the single-file copy of this same renderer. Two copies drift
   silently, so the harness fails the moment they differ. */
/* ---- steering a live turn ------------------------------------------------ */
test('steer="1": the click steers the live turn and submits nothing', async () => {
  const calls = []
  const lines = []
  sdk.host.request = (method, params) => {
    calls.push([method, params])
    return Promise.resolve({ status: 'queued' })
  }
  sdk.host.composer.submit = (sessionId, text) => {
    lines.push([sessionId, text])
    return true
  }
  busyIn('st1', true)
  const el = render(register({ attrs: { steer: '1', multi: '0', q1: 'Tighten the rule', q2: 'Leave it' }, sessionId: 'st1', source: 'st-a' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], 'session.steer')
  assert.deepEqual(calls[0][1], { session_id: 'st1', text: 'Tighten the rule' })
  assert.equal(lines.length, 0, 'a steered click is not also a new message')

  const after = render(register({ attrs: { steer: '1', multi: '0', q1: 'Tighten the rule', q2: 'Leave it' }, sessionId: 'st1', source: 'st-a' }))
  assert.match(chips(after)[0].props.className, /fu-chosen/, 'the click still reads as answered')
  sdk.host.request = null
  resetHost()
})

test('steer="1": a rejected steer still reaches the agent as a normal message', async () => {
  const lines = []
  sdk.host.request = () => Promise.resolve({ status: 'rejected', delivered: false })
  sdk.host.composer.submit = (sessionId, text) => {
    lines.push([sessionId, text])
    return true
  }
  const el = render(register({ attrs: { steer: '1', q1: 'Only step' }, sessionId: 'st2', source: 'st-b' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(lines, [['st2', 'Only step']], 'nothing live took it, so it queues as before')
  sdk.host.request = null
  resetHost()
})

test('steer="1": a failing request falls back instead of losing the click', async () => {
  const lines = []
  sdk.host.request = () => Promise.reject(new Error('gateway down'))
  sdk.host.composer.submit = (sessionId, text) => {
    lines.push([sessionId, text])
    return true
  }
  const el = render(
    register({ attrs: { steer: '1', multi: '1', q1: 'A step', q2: 'Another' }, sessionId: 'st3', source: 'st-c' })
  )
  chips(el)[0].props.onClick()
  const rerendered = render(
    register({ attrs: { steer: '1', multi: '1', q1: 'A step', q2: 'Another' }, sessionId: 'st3', source: 'st-c' })
  )
  send(rerendered).props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(lines, [['st3', 'A step']], 'the multi send fell back to the composer')
  sdk.host.request = null
  resetHost()
})

test('without steer="1" the request door is never used', async () => {
  let asked = 0
  sdk.host.request = () => { asked += 1; return Promise.resolve({ status: 'queued' }) }
  submits.length = 0
  const el = render(register({ attrs: { q1: 'Normal' }, sessionId: 'st4', source: 'st-d' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(asked, 0)
  assert.deepEqual(submits, [['st4', 'Normal']])
  sdk.host.request = null
})

/* ---- the busy queue ------------------------------------------------------ */
function busyIn(sessionId, on) {
  sdk.host.state = { busyBySession: { get: () => ({ [sessionId]: on }) } }
}
function resetHost(submit) {
  sdk.host.state = null
  sdk.host.request = null
  sdk.host.composer.submit = submit || ((sessionId, text) => { submits.push([sessionId, text]); return true })
}

test('busy: the click is admitted to the queue, not steered or interrupted', async () => {
  const calls = []
  const lines = []
  sdk.host.request = (method, params) => { calls.push([method, params]); return Promise.resolve({ status: 'queued' }) }
  sdk.host.composer.submit = (sid, text) => { lines.push([sid, text]); return true }
  busyIn('q1', true)
  const el = render(register({ attrs: { q1: 'Do the next thing' }, sessionId: 'q1', source: 'q-a' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(calls.length, 1)
  assert.equal(calls[0][0], 'prompt.submit')
  assert.equal(calls[0][1].session_id, 'q1')
  assert.equal(calls[0][1].text, 'Do the next thing')
  assert.match(calls[0][1].submission_id, /^next-steps-/, 'the admission carries its own id')
  assert.equal(lines.length, 0, 'a busy click does not go through the composer busy route')
  const after = render(register({ attrs: { q1: 'Do the next thing' }, sessionId: 'q1', source: 'q-a' }))
  assert.match(chips(after)[0].props.className, /fu-chosen/)
  resetHost()
})

test('busy with steer="1": the live turn is steered and nothing is queued', async () => {
  const calls = []
  sdk.host.request = (method, params) => { calls.push([method, params]); return Promise.resolve({ status: 'queued' }) }
  busyIn('q2', true)
  const el = render(register({ attrs: { steer: '1', q1: 'Tighten it' }, sessionId: 'q2', source: 'q-b' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(calls.map((c) => c[0]), ['session.steer'])
  resetHost()
})

test('busy with steer="1": a rejected steer still reaches the queue', async () => {
  const calls = []
  sdk.host.request = (method, params) => { calls.push([method, params]); return Promise.resolve({ status: 'rejected', delivered: false }) }
  busyIn('q3', true)
  const el = render(register({ attrs: { steer: '1', q1: 'Tighten it' }, sessionId: 'q3', source: 'q-c' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(calls.map((c) => c[0]), ['session.steer', 'prompt.submit'], 'the queue is the floor')
  resetHost()
})

test('busy: a refused admission falls back to submit instead of losing the click', async () => {
  const lines = []
  sdk.host.request = () => Promise.reject(new Error('no subscription'))
  sdk.host.composer.submit = (sid, text) => { lines.push([sid, text]); return true }
  busyIn('q4', true)
  const el = render(register({ attrs: { q1: 'Still here' }, sessionId: 'q4', source: 'q-d' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(lines, [['q4', 'Still here']])
  resetHost()
})

test('idle with steer="1": plain submit, no steer and no queue entry', async () => {
  let asked = 0
  const lines = []
  sdk.host.request = () => { asked += 1; return Promise.resolve({ status: 'queued' }) }
  sdk.host.composer.submit = (sid, text) => { lines.push([sid, text]); return true }
  busyIn('q5', false)
  const el = render(register({ attrs: { steer: '1', q1: 'Just do it' }, sessionId: 'q5', source: 'q-e' }))
  chips(el)[0].props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(asked, 0)
  assert.deepEqual(lines, [['q5', 'Just do it']])
  resetHost()
})


/* ---- the Steer button ---------------------------------------------------- */
test('multi shows a small Steer button right after Send', () => {
  const el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb1', source: 'src-sb1' }))
  const row = footerRow(el)
  const buttons = row.props.children.filter((c) => c && c.props.className && c.props.className.indexOf('fu-send') !== -1)
  assert.equal(buttons.length, 2, 'two finalisation buttons')
  assert.equal(label(buttons[0]), 'Send')
  assert.equal(label(buttons[1]), 'Steer')
  assert.ok(buttons[1].props.className.indexOf('fu-steer') !== -1)
  assert.ok(parseFloat(buttons[1].props.style.fontSize) < parseFloat(buttons[0].props.style.fontSize), 'Steer is the small button')
  assert.equal(steer(el), buttons[1], 'the helper finds the same button')
})

test('busy: Steer reaches the live turn and never becomes a queue entry', async () => {
  const calls = []
  sdk.host.request = (method, params) => { calls.push([method, params]); return Promise.resolve({ status: 'queued' }) }
  busyIn('sb2', true)
  let el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb2', source: 'src-sb2' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb2', source: 'src-sb2' }))
  steer(el).props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(calls.map((c) => c[0]), ['session.steer'])
  assert.deepEqual(calls[0][1], { session_id: 'sb2', text: 'A' })
  const after = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb2', source: 'src-sb2' }))
  assert.equal(label(steer(after)), 'Steer', 'the sent block keeps its buttons marked')
  resetHost()
})

test('busy: a refused Steer warns and leaves the block unsent', async () => {
  const calls = []
  sdk.host.request = (method, params) => { calls.push([method, params]); return Promise.resolve({ status: 'rejected', delivered: false }) }
  const lines = []
  sdk.host.composer.submit = (sid, text) => { lines.push([sid, text]); return true }
  submits.length = 0
  busyIn('sb3', true)
  let el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb3', source: 'src-sb3' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb3', source: 'src-sb3' }))
  steer(el).props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(calls.map((c) => c[0]), ['session.steer'], 'no queue fallback')
  assert.deepEqual(lines, [], 'no new turn was admitted')
  assert.deepEqual(submits[0], ['notify', { kind: 'warning', message: 'That turn would not take a steer; use Send to queue it' }])
  const after = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb3', source: 'src-sb3' }))
  assert.equal(label(send(after)), 'Send 1', 'the block can still be sent with Send')
  resetHost()
})

test('idle: Steer starts a normal turn', async () => {
  const calls = []
  sdk.host.request = (method) => { calls.push(method); return Promise.resolve({ status: 'queued' }) }
  submits.length = 0
  busyIn('sb4', false)
  let el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb4', source: 'src-sb4' }))
  chips(el)[1].props.onClick()
  el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'sb4', source: 'src-sb4' }))
  steer(el).props.onClick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.deepEqual(calls, [], 'nothing is running, so there is nothing to steer')
  assert.deepEqual(submits, [['sb4', 'B']])
  resetHost()
})

test('answer mode draws Steer beside Send', () => {
  const nodes = answerNodes(render(register({ attrs: { answer: '1', q1: 'One?', q2: 'Two?' }, sessionId: 'sb5', source: 'src-sb5' })))
  assert.equal(label(answerSend(nodes)), 'Send')
  assert.equal(label(answerSteer(nodes)), 'Steer')
})

/* ---- cleaning the carried chips ------------------------------------------ */
test('clean: labelled with an arrow pointing at the chips it clears', () => {
  const s = 'clean-label'
  render(register({ attrs: { carry: '1', q1: 'Earlier step' }, sessionId: s, source: 'cl-1' }))
  const el = render(register({ attrs: { carry: '1', q1: 'Now' }, sessionId: s, source: 'cl-2' }))
  const button = cleanButton(el)
  assert.ok(button, 'carried chips offer a cleanup')
  assert.equal(button.props.children, 'Clean Old Proposals ↓')
  assert.equal(button.props.type, 'button')
})

test('clean: absent when nothing is carried', () => {
  const el = render(
    register({ attrs: { carry: '1', multi: '0', q1: 'Only mine', q2: 'Also mine' }, sessionId: 'clean-none-yet', source: 'cl-3' })
  )
  assert.equal(cleanButton(el), null, 'no carried chips, no cleanup')
  assert.equal(footerRow(el), null, 'and no footer row to hold one')
})

test('clean: one click drops every carried chip and keeps this reply own', () => {
  const s = 'clean-drop'
  render(register({ attrs: { carry: '1', q1: 'Old A', q2: 'Old B', q3: 'Old C' }, sessionId: s, source: 'cd-1' }))
  const before = render(register({ attrs: { carry: '1', q1: 'Fresh' }, sessionId: s, source: 'cd-2' }))
  assert.deepEqual(staleLabels(before), ['Old A', 'Old B', 'Old C'])

  cleanButton(before).props.onClick()
  const after = render(register({ attrs: { carry: '1', q1: 'Fresh' }, sessionId: s, source: 'cd-2' }))
  assert.deepEqual(staleLabels(after), [], 'every carried chip is gone')
  assert.equal(cleanButton(after), null, 'and the cleanup goes with them')
  assert.deepEqual(freshChips(after).map(label), ['Fresh'], 'this reply keeps its own option')

  /* What this block proposed is still unanswered, so the next reply carries it. */
  const next = render(register({ attrs: { carry: '1' }, sessionId: s, source: 'cd-3' }))
  assert.deepEqual(staleLabels(next), ['Fresh'], 'cleaning the old does not answer the new')
})

test('clean: another chat keeps its carried chips', () => {
  render(register({ attrs: { carry: '1', q1: 'Mine to keep' }, sessionId: 'clean-other-a', source: 'co-1' }))
  const mine = render(register({ attrs: { carry: '1', q1: 'Clear me' }, sessionId: 'clean-other-b', source: 'co-2' }))
  render(register({ attrs: { carry: '1', q1: 'Second in b' }, sessionId: 'clean-other-b', source: 'co-3' }))
  render(register({ attrs: { carry: '1', q1: 'Another in b' }, sessionId: 'clean-other-b', source: 'co-4' }))
  const block = render(register({ attrs: { carry: '1' }, sessionId: 'clean-other-b', source: 'co-5' }))
  cleanButton(block).props.onClick()

  const otherChat = render(register({ attrs: { carry: '1' }, sessionId: 'clean-other-a', source: 'co-9' }))
  assert.deepEqual(staleLabels(otherChat), ['Mine to keep'], 'a different chat is untouched')
})

/* ---- alternate options --------------------------------------------------- */
const ALT = { multi: '1', alt: '1,3', q1: 'Force-push it', q2: 'Add a note', q3: 'Leave as it is' }

test('alt: picking one member clears the other', () => {
  const el = render(register({ attrs: ALT, sessionId: 'alt-1', source: 'alt-a' }))
  chips(el)[0].props.onClick()
  const second = render(register({ attrs: ALT, sessionId: 'alt-1', source: 'alt-a' }))
  assert.match(chips(second)[0].props.className, /fu-chosen/)
  chips(second)[2].props.onClick()
  const third = render(register({ attrs: ALT, sessionId: 'alt-1', source: 'alt-a' }))
  assert.doesNotMatch(chips(third)[0].props.className, /fu-chosen/, 'the opposite chip let go')
  assert.match(chips(third)[2].props.className, /fu-chosen/)
})

test('alt: the chip outside the group keeps its pick', () => {
  const el = render(register({ attrs: ALT, sessionId: 'alt-2', source: 'alt-b' }))
  chips(el)[0].props.onClick()
  const second = render(register({ attrs: ALT, sessionId: 'alt-2', source: 'alt-b' }))
  chips(second)[1].props.onClick()
  chips(second)[2].props.onClick()
  const third = render(register({ attrs: ALT, sessionId: 'alt-2', source: 'alt-b' }))
  assert.doesNotMatch(chips(third)[0].props.className, /fu-chosen/, 'the opposed chip dropped')
  assert.match(chips(third)[1].props.className, /fu-chosen/, 'an unrelated chip stays picked')
  assert.match(chips(third)[2].props.className, /fu-chosen/)
})

test('alt: one chip opposed to two others clears whichever was picked', () => {
  const attrs = { multi: '1', alt: '1,3|2,3', q1: 'Ship it', q2: 'Document it', q3: 'Leave as it is' }
  render(register({ attrs, sessionId: 'alt-3', source: 'alt-c' }))
  let el = render(register({ attrs, sessionId: 'alt-3', source: 'alt-c' }))
  chips(el)[1].props.onClick()
  el = render(register({ attrs, sessionId: 'alt-3', source: 'alt-c' }))
  chips(el)[2].props.onClick()
  el = render(register({ attrs, sessionId: 'alt-3', source: 'alt-c' }))
  assert.doesNotMatch(chips(el)[1].props.className, /fu-chosen/)
  assert.match(chips(el)[2].props.className, /fu-chosen/)
  assert.equal(chips(el)[2].props.style.opacity, 1)
})

test('alt: the chip a pick rules out is greyed but still clickable', () => {
  const el = render(register({ attrs: ALT, sessionId: 'alt-4', source: 'alt-d' }))
  chips(el)[2].props.onClick()
  const after = render(register({ attrs: ALT, sessionId: 'alt-4', source: 'alt-d' }))
  assert.equal(chips(after)[0].props.style.opacity, 0.72, 'the excluded chip reads as unavailable')
  assert.equal(chips(after)[1].props.style.opacity, 1, 'the unrelated chip does not')
  chips(after)[0].props.onClick()
  const swapped = render(register({ attrs: ALT, sessionId: 'alt-4', source: 'alt-d' }))
  assert.match(chips(swapped)[0].props.className, /fu-chosen/, 'clicking it swaps the pick')
  assert.doesNotMatch(chips(swapped)[2].props.className, /fu-chosen/)
})

test('alt: only the surviving pick is sent', () => {
  resetHost()
  submits.length = 0
  const attrs = { multi: '1', alt: '1,3', q1: 'Force-push it', q2: 'Add a note', q3: 'Leave as it is' }
  let el = render(register({ attrs, sessionId: 'alt-5', source: 'alt-e' }))
  chips(el)[0].props.onClick()
  el = render(register({ attrs, sessionId: 'alt-5', source: 'alt-e' }))
  chips(el)[2].props.onClick()
  el = render(register({ attrs, sessionId: 'alt-5', source: 'alt-e' }))
  send(el).props.onClick()
  assert.deepEqual(submits, [['alt-5', 'Leave as it is']], 'one route, one line')
})

test('alt: a group of one, or a number out of range, is ignored', () => {
  const attrs = { multi: '1', alt: '1|7,8', q1: 'A', q2: 'B' }
  const el = render(register({ attrs, sessionId: 'alt-6', source: 'alt-f' }))
  chips(el)[0].props.onClick()
  const after = render(register({ attrs, sessionId: 'alt-6', source: 'alt-f' }))
  chips(after)[1].props.onClick()
  const both = render(register({ attrs, sessionId: 'alt-6', source: 'alt-f' }))
  assert.match(chips(both)[0].props.className, /fu-chosen/)
  assert.match(chips(both)[1].props.className, /fu-chosen/, 'nothing was grouped')
})

/* ---- 1.0.14 backfill: entries stored before the flag existed --------------- */
function seedLegacy(sessionId, blockKey, labels) {
  const all = store.get('carried') || {}
  all[sessionId] = {
    v: 2,
    next: 2,
    blocks: { [blockKey]: 1 },
    entries: labels.map((label, i) => ({ id: blockKey + '#' + i, key: blockKey, i, label, n: 1, gone: false })),
  }
  store.set('carried', all)
}

test('carry: an entry stored before the flag is kept ahead of a confirmed unmarked one', () => {
  const s = 'legacy-keep'
  const labels = []
  for (let i = 1; i <= 30; i += 1) labels.push('Old ' + i)
  seedLegacy(s, s + '::legacy-src', labels)
  const fresh = { carry: '1', q1: 'New A', q2: 'New B', q3: 'New C' }
  const el = render(register({ attrs: fresh, sessionId: s, source: 'legacy-new' }))
  const rows = staleRows(el).map((row) => label(staleButton(row)))
  assert.equal(rows.length, 30)
  assert.ok(rows.includes('Old 1'), 'an unknown verdict is not the first thing to go')
  assert.ok(!rows.includes('New A'), 'the new unmarked options are retired first')
})

test('carry: a block that renders again gives its old entries their verdict back', () => {
  const s = 'legacy-upgrade'
  const key = s + '::same-src'
  const labels = []
  for (let i = 1; i <= 30; i += 1) labels.push('Old ' + i)
  seedLegacy(s, key, labels)
  const attrs = { carry: '1', rec: '1' }
  labels.forEach((label, i) => {
    attrs['q' + (i + 1)] = label
  })
  render(register({ attrs, sessionId: s, source: 'same-src' }))
  const stored = store.get('carried')[s].entries
  assert.equal(stored[0].rec, true, 'the verdict from the live directive is written back')
  assert.equal(stored[1].rec, false, 'and the neighbours are cleared, not left unknown')
  const el = render(
    register({ attrs: { carry: '1', q1: 'A', q2: 'B', q3: 'C', q4: 'D', q5: 'E' }, sessionId: s, source: 'other' })
  )
  const rows = staleRows(el).map((row) => label(staleButton(row)))
  assert.ok(rows.includes('Old 1'), 'the recommendation recovered from the transcript survives')
  assert.ok(!rows.includes('Old 2'), 'its unmarked neighbours go first')
  assert.ok(!rows.includes('Old 6'))
})

/* ---- subtitles ----------------------------------------------------------- */
test('subtitle: a d attribute draws a dim second line under the label', () => {
  const attrs = { multi: '1', q1: 'Push it', d1: 'Rewrites origin, discarding their commit', q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-1', source: 'sub-a' }))
  const first = subtitle(chips(el)[0])
  assert.ok(first, 'the first chip carries a subtitle')
  assert.equal(first.children, 'Rewrites origin, discarding their commit')
  assert.equal(subtitle(chips(el)[1]), undefined, 'an option that needs none has none')
  assert.equal(label(chips(el)[0]), 'Push it', 'the label is unchanged')
})

test('subtitle: dimmer and smaller than the label, clipped at two lines', () => {
  const attrs = { q1: 'Push it', d1: 'Rewrites origin' , q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-2', source: 'sub-b' }))
  const mark = subtitle(chips(el)[0])
  assert.equal(String(mark.style.opacity), '0.72', 'dim')
  assert.ok(parseFloat(mark.style.fontSize) < 1, 'smaller than the chip text')
  assert.equal(String(mark.style.WebkitLineClamp), '2')
  assert.equal(mark.style.overflow, 'hidden')
  assert.equal(mark.style.display, '-webkit-box', 'clamping needs the box display')
})

test('subtitle: the full text stays reachable in the chip tooltip', () => {
  const attrs = { q1: 'Push it', d1: 'Rewrites origin', q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-3', source: 'sub-c' }))
  assert.equal(chips(el)[0].props.title, 'Push it\nRewrites origin')
  assert.equal(chips(el)[1].props.title, 'Tag it', 'no subtitle, no second tooltip line')
})

test('subtitle: whitespace collapses so a wrapped model reply cannot add a line', () => {
  const attrs = { q1: 'Push it', d1: '  Rewrites   origin,\nleaving    nothing  ', q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-4', source: 'sub-d' }))
  assert.equal(subtitle(chips(el)[0]).children, 'Rewrites origin, leaving nothing')
})

test('subtitle: an over-long line is cut once, at a word, and says so', () => {
  const attrs = { q1: 'Push it', d1: 'x'.repeat(400), q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-5', source: 'sub-e' }))
  const text = subtitle(chips(el)[0]).children
  assert.equal(text.length, 161, '160 characters plus the ellipsis')
  assert.ok(text.endsWith('…'))
})

test('subtitle: a described chip still sends its label alone', () => {
  resetHost()
  submits.length = 0
  const attrs = { multi: '0', q1: 'Push it', d1: 'Rewrites origin', q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-6', source: 'sub-f' }))
  chips(el)[0].props.onClick()
  assert.deepEqual(submits, [['sub-6', 'Push it']], 'the message is the label, never the subtitle')
})

test('subtitle: the second line starts where the label starts, not under the tick', () => {
  const attrs = { multi: '1', q1: 'Push it', d1: 'Rewrites origin', q2: 'Tag it' }
  const el = render(register({ attrs, sessionId: 'sub-7', source: 'sub-g' }))
  const chip = chips(el)[0]
  const body = chip.props.children[0]
  const mark = subtitle(chip)
  assert.equal(String(body.props.style.display), 'grid', 'a grid, so the columns cannot drift')
  assert.equal(String(body.props.style.gridTemplateColumns), 'max-content minmax(0, 1fr)')
  assert.equal(String(mark.style.gridColumn), '2', 'the subtitle shares the label column')
  assert.equal(body.props.children.length, 3, 'tick, label, subtitle')
  assert.equal(body.props.children[0].props.children, '✓', 'the glyph carries no trailing space')
  assert.equal(String(body.props.style.columnGap), '6px', 'the tick gap is a container gap')
  assert.equal(label(chip), 'Push it', 'the label text is still just the label')
})

/* ---- risky options ------------------------------------------------------- */
function marksOf(chip) {
  return (chip.props.children || []).filter(
    (k) => k && k.props && (k.props.className === 'fu-risky' || k.props.className === 'fu-recommended' || k.props.className === 'fu-tag')
  )
}

function markTexts(chip) {
  /* The recommended tag renders without a className; identify it by its text. */
  const spans = (chip.props.children || []).filter(
    (k) => k && k.props && typeof k.props.children === 'string' && k.props.style && k.props.style.textTransform === 'uppercase'
  )
  return new Map(spans.map((k) => [k.props.className || 'tag', k.props.children]))
}

test('risky: the marked chip carries the pill', () => {
  const attrs = { multi: '1', risky: '2', q1: 'Tag it', q2: 'Force-push the branch' }
  const el = render(register({ attrs, sessionId: 'risk-1', source: 'risk-a' }))
  assert.equal(markTexts(chips(el)[1]).get('fu-risky'), 'Risky', 'the risky chip is marked')
  assert.equal(markTexts(chips(el)[0]).get('fu-risky'), undefined, 'the safe one is not')
})

test('risky: the pill reads as a caution, not the accent', () => {
  const attrs = { multi: '1', risky: '1', q1: 'Delete the tag', q2: 'Add a note' }
  const el = render(register({ attrs, sessionId: 'risk-2', source: 'risk-b' }))
  const pill = marksOf(chips(el)[0]).find((k) => k.props.className === 'fu-risky')
  assert.ok(pill, 'pill rendered')
  assert.match(String(pill.props.style.color), /warning/, 'amber, never the accent')
  assert.match(pill.props.title, /damage|break/)
})

test('risky: a chip can be both recommended and risky', () => {
  const attrs = { multi: '1', risky: '1', rec: '1', q1: 'Force-push it', q2: 'Leave as it is' }
  const el = render(register({ attrs, sessionId: 'risk-3', source: 'risk-c' }))
  const marks = markTexts(chips(el)[0])
  assert.equal(marks.get('fu-risky'), 'Risky')
  assert.equal(marks.get('tag'), 'Recommended')
})

test('risky: the mark does not stop a click', () => {
  resetHost()
  submits.length = 0
  const attrs = { multi: '0', risky: '1', q1: 'Force-push it', q2: 'Leave as it is' }
  const el = render(register({ attrs, sessionId: 'risk-4', source: 'risk-d' }))
  chips(el)[0].props.onClick()
  assert.deepEqual(submits, [['risk-4', 'Force-push it']], 'a marked chip still sends')
})

test('risky: no attribute, no pill', () => {
  const el = render(register({ attrs: { multi: '1', q1: 'A', q2: 'B' }, sessionId: 'risk-5', source: 'risk-e' }))
  assert.equal(markTexts(chips(el)[0]).get('fu-risky'), undefined)
  assert.equal(markTexts(chips(el)[1]).get('fu-risky'), undefined)
})

test('root plugin.js is byte-identical to desktop/plugin.js', () => {
  const root = readFileSync(resolve(here, '..', 'plugin.js'), 'utf8')
  const desktop = readFileSync(pluginSource, 'utf8')
  assert.equal(root === desktop, true, 'run: cp desktop/plugin.js plugin.js')
})

/* ---- answer mode: the reply fields learned from followup-chips 1.2.0 ------ */
function answerNodes(el) {
  const block = el.props.children[0]
  assert.equal(block && block.props.className, 'fu-answers', 'answer mode draws a form, not chips')
  return block.props.children
}

function answerSend(nodes) {
  const wrap = nodes.find((n) => n && n.type === 'div' && n.props.style && n.props.style.gridColumn === '2')
  assert.ok(wrap, 'the send button sits in the input column')
  return Array.isArray(wrap.props.children) ? wrap.props.children[0] : wrap.props.children
}

function answerSteer(nodes) {
  const wrap = nodes.find((n) => n && n.type === 'div' && n.props.style && n.props.style.gridColumn === '2')
  const second = wrap && wrap.props.children && wrap.props.children[1]
  assert.ok(second, 'Steer sits beside Send in the input column')
  return second
}

test('answer=true sends labelled item: answer lines as one turn', () => {
  submits.length = 0
  const attrs = { answer: '1', q1: 'Deploy at 16:00?', q2: 'Tag v1.3.0?' }
  let el = render(register({ attrs, sessionId: 'a1', source: 'src-a1' }))
  let nodes = answerNodes(el)
  const fields = nodes.filter((n) => n && n.type === 'Input')
  assert.equal(fields.length, 2)
  assert.equal(fields[0].props.placeholder, 'Deploy at 16:00?')
  assert.equal(answerSend(nodes).props.disabled, true, 'nothing picked yet')
  fields[0].props.onChange({ target: { value: 'yes, at 16:00' } })
  el = render(register({ attrs, sessionId: 'a1', source: 'src-a1' }))
  nodes = answerNodes(el)
  const button = answerSend(nodes)
  assert.equal(button.props.disabled, false)
  assert.equal(label(button), 'Send 1', 'typing auto-picks the row')
  button.props.onClick()
  assert.deepEqual(submits, [['a1', '1. Deploy at 16:00?: yes, at 16:00']])
})

test('a checked answer row with no text sends its numbered question', () => {
  submits.length = 0
  const attrs = { answer: '1', q1: 'Deploy?', q2: 'Tag?' }
  let el = render(register({ attrs, sessionId: 'a2', source: 'src-a2' }))
  answerNodes(el).filter((n) => n && n.type === 'Checkbox')[1].props.onCheckedChange()
  el = render(register({ attrs, sessionId: 'a2', source: 'src-a2' }))
  answerSend(answerNodes(el)).props.onClick()
  assert.deepEqual(submits, [['a2', '2. Tag?']])
})

test('kind=answer is accepted and plain chips ignore the answer attr', () => {
  const attrs = { kind: 'answer', q1: 'One?', q2: 'Two?' }
  assert.equal(answerNodes(render(register({ attrs, sessionId: 'a3', source: 'src-a3' }))).length > 0, true)
  const plain = render(register({ attrs: { q1: 'One?', q2: 'Two?' }, sessionId: 'a4', source: 'src-a4' }))
  assert.equal(chips(plain).length, 2, 'a plain block still draws chips')
})

test('answers persist, and a corrupt stored value cannot load a form', () => {
  const attrs = { answer: '1', q1: 'One?', q2: 'Two?' }
  let el = render(register({ attrs, sessionId: 'a5', source: 'src-a5' }))
  answerNodes(el).filter((n) => n && n.type === 'Input')[0].props.onChange({ target: { value: 'first' } })
  el = render(register({ attrs, sessionId: 'a5', source: 'src-a5' }))
  assert.equal(answerNodes(el).filter((n) => n && n.type === 'Input')[0].props.value, 'first')
  const saved = store.get('choices')
  const key = Object.keys(saved).find((k) => k.indexOf('src-a5') !== -1)
  assert.equal(saved[key].texts[0], 'first')
  saved[key].texts = [null, 7]
  store.set('choices', saved)
  /* A restart re-hydrates; corrupt values must load as blanks, not as text. */
  plugin.register({
    storage: {
      get: (key, fallback) => (store.has(key) ? structuredClone(store.get(key)) : fallback),
      set: (key, value) => store.set(key, structuredClone(value)),
    },
    register: () => {},
  })
  el = render(register({ attrs, sessionId: 'a5', source: 'src-a5' }))
  const fields = answerNodes(el).filter((n) => n && n.type === 'Input')
  assert.equal(fields[0].props.value, '', 'a bad stored entry loads as blank')
  assert.equal(fields[1].props.value, '')
})

test('the answer form caps its width so it cannot grow to the window edge', () => {
  const el = render(register({ attrs: { answer: '1', q1: 'One?', q2: 'Two?' }, sessionId: 'a6', source: 'src-a6' }))
  const form = el.props.children[0]
  assert.equal(form.props.style.maxWidth, '520px')
  assert.equal(form.props.style.gridTemplateColumns, 'auto minmax(0, 1fr)')
})

for (const [name, fn] of cases) {
  try {
    await fn()
    results.push(['ok', name])
  } catch (error) {
    results.push(['fail', name, error.message])
  }
}
rmSync(dir, { recursive: true, force: true })
const failed = results.filter((r) => r[0] === 'fail')
for (const [state, name, detail] of results) {
  console.log((state === 'ok' ? 'ok   ' : 'FAIL ') + name + (detail ? '\n       ' + detail : ''))
}
console.log('\n' + (results.length - failed.length) + '/' + results.length + ' passed')
process.exit(failed.length ? 1 : 0)
