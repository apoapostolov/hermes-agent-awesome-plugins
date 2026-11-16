/**
 * Settings page tests for Radio Plus.
 *
 * One switch, "start the last station on launch", off by default. This renders
 * the real page with the real React and jsdom from the installed app and reads
 * the stored key back, so it covers the contract the settings surface uses: a
 * ToggleRow row whose onChange persists, and a reader the launch path shares.
 *
 *   node tests/settings.test.mjs
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
const dir = mkdtempSync(path.join(tmpdir(), 'radio-plus-settings-'))

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

// The English strings the plugin ships, so the row is checked for copy a reader
// would actually see rather than for a translation key.
const COPY = {
  autoplayLabel: 'Start the last station on launch',
  autoplayDescription: 'Plays the station you listened to last as soon as Hermes opens, so the status bar is live without a click. Off by default; with it off nothing plays until you press play, and a station that cannot be reached reports the reason in the panel instead of retrying.'
}

// ToggleRow's real contract: label is the row title and the Switch's aria-label,
// description is the whole explanation, onChange hands back a boolean.
writeFileSync(path.join(dir, 'sdk.mjs'), `
import React from ${JSON.stringify(fileUrl(reactEntry))}
const COPY = ${JSON.stringify(COPY)}

export const atom = value => { let current = value; return { get: () => current, set: next => { current = next } } }
export const Button = ({ children, ...props }) => React.createElement('button', { type: 'button', ...props }, children)
export const RowButton = ({ children, ...props }) => React.createElement('button', { type: 'button', ...props }, children)
export const createBudgetedLoop = () => ({ wake() {}, dispose() {} })
export const GlyphSpinner = () => React.createElement('span', null)
export const icons = new Proxy({}, { get: () => props => React.createElement('svg', props) })
export const Popover = ({ children }) => children
export const PopoverContent = ({ children }) => children
export const PopoverTrigger = ({ children }) => children
export const randomUuid = () => globalThis.crypto.randomUUID()
export const SearchField = ({ value, onChange, placeholder }) =>
  React.createElement('input', { value, placeholder, onChange: event => onChange(event.target.value) })
export const STATUSBAR_AREAS = { right: 'right' }
export const Tip = ({ children }) => children
export const usePluginI18n = () => key => COPY[key] ?? key
export const useQuery = () => ({ data: undefined, isFetching: false, isError: false })
export const useValue = value => value.get()
export const ToggleRow = ({ checked, description, id, label, onChange }) =>
  React.createElement('div', { 'data-row': id },
    React.createElement('span', { className: 'row-label' }, label),
    React.createElement('span', { className: 'row-description' }, description),
    React.createElement('input', {
      type: 'checkbox',
      role: 'switch',
      'aria-label': label,
      checked,
      onChange: event => onChange(event.target.checked)
    }))
`)

const source = readFileSync(path.resolve(import.meta.dirname, '..', 'desktop', 'plugin.js'), 'utf8')
  .replaceAll("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replaceAll("from 'react'", "from './react.mjs'")
  .replaceAll("from 'react/jsx-runtime'", "from './jsx.mjs'")
writeFileSync(path.join(dir, 'plugin.mjs'), source)

const plugin = await import(pathToFileURL(path.join(dir, 'plugin.mjs')).href)
const React = await import(fileUrl(reactEntry))
const { createRoot } = await import(fileUrl(reactDomClient))
const { act } = React

const results = []
const test = async (name, run) => {
  try {
    await run()
    results.push({ name, ok: true })
    console.log(`PASS  ${name}`)
  } catch (error) {
    results.push({ name, ok: false, error })
    console.log(`FAIL  ${name}\n      ${error.message}`)
  }
}

const storage = {}
const reader = { get: (key, fallback) => (key in storage ? storage[key] : fallback) }
const makeCtx = () => {
  const ctx = {
    storage: {
      get: (key, fallback) => (key in storage ? storage[key] : fallback),
      set: (key, value) => { storage[key] = value }
    },
    i18n: { register() {} },
    onDispose() {},
    register() {},
    pages: [],
    registerSettingsPage(page) { ctx.pages.push(page) }
  }
  return ctx
}

await test('the page registers with a title, an icon and an order', async () => {
  const ctx = makeCtx()
  plugin.default.register(ctx)
  assert.equal(ctx.pages.length, 1, 'exactly one settings page')
  const [page] = ctx.pages
  assert.equal(page.id, 'radio-plus')
  assert.equal(page.title, 'Radio Plus')
  assert.equal(typeof page.render, 'function')
  assert.equal(typeof page.icon, 'string')
  assert.ok(Number.isFinite(page.order))
})

await test('an old build without registerSettingsPage still loads the plugin', async () => {
  const ctx = makeCtx()
  delete ctx.registerSettingsPage
  plugin.default.register(ctx)
  assert.equal(ctx.pages.length, 0)
})

await test('the switch is off before anyone touches it', async () => {
  delete storage['local.autoplay']
  assert.equal(plugin.autoplayOnLaunch(reader), false)
  assert.equal(plugin.shouldAutoplay(reader, { id: 'a', name: 'A', url: 'https://example.test/a' }), false)
})

const ctx = makeCtx()
plugin.default.register(ctx)
const page = ctx.pages[0]
let root = createRoot(document.getElementById('root'))
const paint = async () => {
  await act(async () => {
    root.render(page.render())
  })
}
await paint()

const control = () => document.querySelector('[role="switch"]')

await test('the row explains what the switch does, in one description', async () => {
  const label = document.querySelector('.row-label').textContent
  const description = document.querySelector('.row-description').textContent
  assert.match(label, /start the last station on launch/i)
  assert.match(description, /off by default/i, 'the description states the default')
  assert.ok(description.length > 80, 'the description carries the whole explanation')
  assert.equal(document.querySelectorAll('.row-description').length, 1, 'no second line of copy')
})

await test('the row renders unchecked', async () => {
  assert.equal(control().checked, false, 'off by default in the DOM')
  assert.equal(control().getAttribute('aria-label'), COPY.autoplayLabel)
})

// Flip it the way a user does: one real click on the switch.
const flip = async () => {
  await act(async () => {
    control().click()
  })
}

// The page reads storage when it mounts, so reopening it means remounting.
const remount = async () => {
  await act(async () => {
    root.unmount()
  })
  root = createRoot(document.getElementById('root'))
  await paint()
}

await test('flipping it stores the choice and repaints checked', async () => {
  await flip()
  assert.equal(storage['local.autoplay'], true, 'the flip is persisted')
  assert.equal(control().checked, true, 'the row repaints checked')
})

await test('the stored choice is what the launch path reads', async () => {
  assert.equal(plugin.autoplayOnLaunch(reader), true)
  assert.equal(plugin.shouldAutoplay(reader, { id: 'a', name: 'A', url: 'https://example.test/a' }), true)
  assert.equal(plugin.shouldAutoplay(reader, null), false, 'nothing played yet means nothing to start')
  storage['local.autoplay'] = false
  assert.equal(plugin.shouldAutoplay(reader, { id: 'a', name: 'A', url: 'https://example.test/a' }), false)
})

await test('turning it back off is stored as false', async () => {
  storage['local.autoplay'] = true
  await remount()
  assert.equal(control().checked, true, 'the remounted page reads the stored value')
  await flip()
  assert.equal(storage['local.autoplay'], false)
  assert.equal(control().checked, false)
})

await test('a stored true reopens the page switched on', async () => {
  storage['local.autoplay'] = true
  await remount()
  assert.equal(control().checked, true)
  storage['local.autoplay'] = false
})

const failed = results.filter(entry => !entry.ok)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
// The plugin opens a BroadcastChannel and arms a launch timer, so the loop stays
// alive; exit explicitly rather than waiting on handles the test does not own.
process.exit(failed.length ? 1 : 0)
