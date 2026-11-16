/**
 * Panel render tests for Radio Plus.
 *
 * The unit harness (desktop.test.mjs) covers state. This one covers what the
 * user sees: the source chips must carry a visible selected state, the add
 * button sits on the same row, and the row editor edits a name AND a URL.
 *
 * It renders the real `Stations` component with the real React and jsdom taken
 * from the installed Hermes desktop app, so the SDK surface is stubbed but the
 * component tree, hooks and click handling are not.
 *
 *   node tests/panel.test.mjs
 *
 * Set HERMES_DESKTOP_APP if the desktop app lives somewhere else; the test
 * reports SKIP when React cannot be found there.
 */
import assert from 'node:assert/strict'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const appDir = process.env.HERMES_DESKTOP_APP
  || 'C:/Users/theap/AppData/Local/hermes/hermes-agent/apps/desktop'
const modules = path.join(appDir, 'node_modules')
const reactEntry = path.join(modules, 'react', 'index.js')
const reactDomClient = path.join(modules, 'react-dom', 'client.js')
const reactJsx = path.join(modules, 'react', 'jsx-runtime.js')
const jsdomEntry = path.join(modules, 'jsdom', 'lib', 'api.js')

for (const entry of [reactEntry, reactDomClient, reactJsx, jsdomEntry]) {
  if (!existsSync(entry)) {
    console.log(`SKIP  React or jsdom not found under ${modules}`)
    process.exit(0)
  }
}

const fileUrl = value => pathToFileURL(value).href
const dir = mkdtempSync(path.join(tmpdir(), 'radio-plus-panel-'))

// jsdom must own the globals before react-dom/client is imported.
const { JSDOM } = await import(fileUrl(jsdomEntry))
const dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>', { url: 'http://localhost/' })
globalThis.window = dom.window
globalThis.document = dom.window.document
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true })
globalThis.HTMLElement = dom.window.HTMLElement
globalThis.Element = dom.window.Element
globalThis.Node = dom.window.Node
globalThis.Event = dom.window.Event
globalThis.MouseEvent = dom.window.MouseEvent
globalThis.KeyboardEvent = dom.window.KeyboardEvent
globalThis.IS_REACT_ACT_ENVIRONMENT = true

writeFileSync(path.join(dir, 'react.mjs'), `
export { useState, useEffect, useRef, useMemo, useCallback, useSyncExternalStore, act } from ${JSON.stringify(fileUrl(reactEntry))}
`)
writeFileSync(path.join(dir, 'jsx.mjs'), `
export { jsx, jsxs, Fragment } from ${JSON.stringify(fileUrl(reactJsx))}
`)

const POPULAR = [
  { id: 'pop-1', name: 'MANGORADIO', url: 'https://example.test/mango', provider: 'Radio Browser', description: 'pop' },
  { id: 'pop-2', name: 'Christmas FM', url: 'https://example.test/xmas', provider: 'Radio Browser', description: 'pop' }
]
const SHOUTCAST = [
  { id: 'sc-1', name: 'Smooth Jazz UK', url: 'http://example.test/sc1', provider: 'Shoutcast', description: 'Smooth Jazz' }
]

writeFileSync(path.join(dir, 'sdk.mjs'), `
import React from ${JSON.stringify(fileUrl(reactEntry))}

export const atom = value => { let current = value; return { get: () => current, set: next => { current = next } } }
export const Button = ({ children, asChild, variant, size, loading, ...props }) =>
  React.createElement('button', { type: 'button', ...props }, children)
export const RowButton = ({ children, ...props }) => React.createElement('button', { type: 'button', ...props }, children)
export const createBudgetedLoop = () => ({ wake() {}, dispose() {} })
export const GlyphSpinner = () => React.createElement('span', { 'data-spinner': 'true' })
export const icons = new Proxy({}, { get: () => props => React.createElement('svg', props) })
export const Popover = ({ children }) => children
export const PopoverContent = ({ children }) => children
export const PopoverTrigger = ({ children }) => children
export const randomUuid = () => globalThis.crypto.randomUUID()
export const SearchField = ({ value, onChange, placeholder }) =>
  React.createElement('input', { value, placeholder, onChange: event => onChange(event.target.value) })
export const STATUSBAR_AREAS = { right: 'right' }
export const Tip = ({ children }) => children
export const usePluginI18n = () => key => key
export const useValue = value => value.get()

// The query stub answers per source so a chip click changes the list.
export const useQuery = options => {
  const key = Array.isArray(options.queryKey) ? options.queryKey[1] : ''
  if (key === 'popular') return { data: { stations: ${JSON.stringify(POPULAR)}, hls: 0 }, isFetching: false, isError: false }
  if (key === 'shoutcast') return { data: { stations: ${JSON.stringify(SHOUTCAST)}, hls: 0, skipped: 2 }, isFetching: false, isError: false }
  return { data: { stations: [], hls: 0 }, isFetching: false, isError: false }
}
`)

const source = readFileSync(path.resolve(import.meta.dirname, '..', 'desktop', 'plugin.js'), 'utf8')
  .replaceAll("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replaceAll("from 'react'", "from './react.mjs'")
  .replace("from 'react/jsx-runtime'", "from './jsx.mjs'")
  .concat('\nexport { Stations, createPlayer, SEED_STATIONS }\n')
writeFileSync(path.join(dir, 'plugin.mjs'), source)

const plugin = await import(pathToFileURL(path.join(dir, 'plugin.mjs')).href)
const React = await import(fileUrl(reactEntry))
const { createRoot } = await import(fileUrl(reactDomClient))
const { act } = React

const storage = {}
const ctx = {
  storage: {
    get: (key, fallback) => (key in storage ? storage[key] : fallback),
    set: (key, value) => { storage[key] = value }
  },
  onDispose() {},
  os: { openExternal() {} },
  rest: async () => ({ ok: true, kind: 'audio' })
}
const player = plugin.createPlayer(ctx)

const root = createRoot(document.getElementById('root'))
await act(async () => {
  root.render(React.createElement(plugin.Stations, { player, ctx }))
})

const text = () => document.getElementById('root').textContent
const chips = () => [...document.querySelectorAll('.hermes-radio-plus-chip')]
const click = async element => {
  await act(async () => {
    element.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
  })
}

const results = []
async function test(name, fn) {
  try {
    await fn()
    results.push(['PASS', name])
  } catch (error) {
    results.push(['FAIL', `${name}\n    ${error.message.split('\n').join('\n    ')}`])
  }
}

await test('the source chips render with one selected', () => {
  const labels = chips().map(chip => chip.textContent)
  assert.deepEqual(labels, ['sourceAll', 'sourcePopular', 'sourceShoutcast', 'sourceTunein'])
  assert.equal(chips()[0].getAttribute('data-active'), 'true')
  assert.equal(chips()[1].getAttribute('data-active'), 'false')
  assert.equal(chips()[0].getAttribute('aria-pressed'), 'true')
})

await test('the add button shares the chip row and opens the add form', async () => {
  const row = document.querySelector('.hermes-radio-plus-sources')
  const addButton = row.querySelector('.hermes-radio-plus-addbtn')
  assert.ok(addButton, 'the add button is not in the source row')
  assert.ok(row.lastElementChild.contains(addButton), 'the add button is not right-aligned last in the row')
  assert.equal(addButton.getAttribute('aria-label'), 'add')

  await click(addButton)
  const form = document.querySelector('.hermes-radio-plus-add')
  assert.ok(form, 'clicking the add button did not open the form')
  assert.equal(form.querySelectorAll('input').length, 2)
  assert.equal(addButton.getAttribute('data-active'), 'true')

  await click(addButton)
  assert.equal(document.querySelector('.hermes-radio-plus-add'), null, 'a second click did not close the form')
})

await test('your stations are listed under All', () => {
  const names = [...document.querySelectorAll('.hermes-radio-plus-row-name')].map(node => node.textContent)
  assert.ok(names.includes(plugin.SEED_STATIONS[0].name), `seed station missing: ${names.join(' | ')}`)
})

await test('clicking Popular selects it and swaps the list', async () => {
  await click(chips()[1])
  assert.equal(chips()[1].getAttribute('data-active'), 'true')
  assert.equal(chips()[0].getAttribute('data-active'), 'false')
  assert.equal(chips()[1].getAttribute('aria-pressed'), 'true')

  const names = [...document.querySelectorAll('.hermes-radio-plus-row-name')].map(node => node.textContent)
  assert.ok(names.includes('MANGORADIO'), `popular stations missing: ${names.join(' | ')}`)
  assert.ok(!names.includes(plugin.SEED_STATIONS[1].name), 'your own stations should not pad the Popular tab')
})

await test('clicking Shoutcast selects it and shows its results and skips', async () => {
  await click(chips()[2])
  assert.equal(chips()[2].getAttribute('data-active'), 'true')
  const names = [...document.querySelectorAll('.hermes-radio-plus-row-name')].map(node => node.textContent)
  assert.ok(names.includes('Smooth Jazz UK'), `shoutcast results missing: ${names.join(' | ')}`)
  assert.match(text(), /2 skippedNote/)
})

await test('the row editor edits a name and an address', async () => {
  await click(chips()[0])
  const row = [...document.querySelectorAll('.hermes-radio-plus-row')]
    .find(node => node.textContent.includes(plugin.SEED_STATIONS[0].name))
  const edit = row.querySelectorAll('.hermes-radio-plus-row-edit')[0]
  assert.ok(edit, 'no edit control on a stored station')
  await click(edit)

  const inputs = [...row.querySelectorAll('.hermes-radio-plus-edit input')]
  assert.equal(inputs.length, 2, 'the editor must offer a name and a URL')
  assert.equal(inputs[0].value, plugin.SEED_STATIONS[0].name)
  assert.equal(inputs[1].value, plugin.SEED_STATIONS[0].url)
})

const failed = results.filter(([status]) => status === 'FAIL')
for (const [status, name] of results) console.log(`${status}  ${name}`)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
