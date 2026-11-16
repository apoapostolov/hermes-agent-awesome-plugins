/**
 * Renderer tests for Radio Plus.
 *
 * `desktop/plugin.js` imports `@hermes/plugin-sdk`, `react` and
 * `react/jsx-runtime`, so it cannot be imported by Node directly. This harness
 * builds a temporary copy of the file with those specifiers pointed at local
 * stubs, adds an export line for the internals under test, and exercises the
 * real code: URL rules, the editable station list, and the source fetchers
 * (Radio Browser live, Shoutcast against a canned route response).
 *
 *   node tests/desktop.test.mjs
 */
import assert from 'node:assert/strict'
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const root = path.resolve(import.meta.dirname, '..')
const dir = mkdtempSync(path.join(tmpdir(), 'radio-plus-test-'))

const SDK_STUB = `
export const atom = value => { let current = value; return { get: () => current, set: next => { current = next } } }
export const Button = () => null
export const createBudgetedLoop = () => ({ wake() {}, dispose() {} })
export const GlyphSpinner = () => null
export const icons = new Proxy({}, { get: () => () => null })
export const Popover = () => null
export const PopoverContent = () => null
export const PopoverTrigger = () => null
export const randomUuid = () => globalThis.crypto.randomUUID()
export const RowButton = () => null
export const SearchField = () => null
export const STATUSBAR_AREAS = { right: 'right' }
export const Tip = () => null
export const usePluginI18n = () => key => key
export const useQuery = () => ({ data: undefined, isFetching: false, isError: false })
export const useValue = value => value.get()
`

writeFileSync(path.join(dir, 'sdk.mjs'), SDK_STUB)
writeFileSync(path.join(dir, 'react.mjs'), 'export const useEffect = () => {}\nexport const useRef = () => ({ current: null })\nexport const useState = value => [value, () => {}]\n')
writeFileSync(path.join(dir, 'jsx.mjs'), 'export const jsx = () => null\nexport const jsxs = () => null\nexport const Fragment = null\n')

const source = readFileSync(path.join(root, 'desktop', 'plugin.js'), 'utf8')
  .replace("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replace("from 'react'", "from './react.mjs'")
  .replace("from 'react/jsx-runtime'", "from './jsx.mjs'")
  .concat(`
export {
  createPlayer, popularStations, sameStation, searchStations, shoutcastStations,
  streamUrl, uniqueStations, validStation, SEED_STATIONS, SOURCE_LABELS,
  transliterate, fold, searchTerms, mediaFailure
}
`)
writeFileSync(path.join(dir, 'plugin.mjs'), source)

// Minimal DOM so createPlayer can register its paste listener and play() can
// build an <audio> element without a real document.
class FakeAudio {
  constructor() { this.dataset = {}; this.hidden = false; this.preload = 'none'; this.volume = 1; this.paused = true }
  addEventListener() {}
  removeAttribute() {}
  load() {}
  remove() {}
  pause() {}
  play() { return Promise.reject(new Error('no audio device in the harness')) }
}
globalThis.Audio = FakeAudio
globalThis.document = { addEventListener() {}, removeEventListener() {}, body: { append() {} } }

const plugin = await import(pathToFileURL(path.join(dir, 'plugin.mjs')).href)

function makeCtx(storage = {}) {
  const writes = []
  return {
    writes,
    storage: {
      get: (key, fallback) => (key in storage ? storage[key] : fallback),
      set: (key, value) => { storage[key] = value; writes.push(key) }
    },
    onDispose() {}
  }
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

const SEEDED = plugin.SEED_STATIONS

await test('streamUrl accepts http and https, rejects everything else', () => {
  assert.equal(plugin.streamUrl('http://162.252.171.80:8002/stream'), 'http://162.252.171.80:8002/stream')
  assert.equal(plugin.streamUrl('https://stream.radioparadise.com/aac-128'), 'https://stream.radioparadise.com/aac-128')
  assert.equal(plugin.streamUrl('ftp://example.test/x'), null)
  assert.equal(plugin.streamUrl('file://../../victim'), null)
  assert.equal(plugin.streamUrl('http://user:pass@example.test/x'), null)
  assert.equal(plugin.streamUrl('not a url'), null)
  assert.equal(plugin.streamUrl(null), null)
})

await test('validStation needs an id, a name and a stream URL', () => {
  assert.equal(plugin.validStation({ id: 'a', name: 'A', url: 'http://example.test/s' }), true)
  assert.equal(plugin.validStation({ id: 'a', name: 'A', url: 'ftp://example.test/s' }), false)
  assert.equal(plugin.validStation({ id: 1, name: 'A', url: 'http://example.test/s' }), false)
  assert.equal(plugin.validStation(null), false)
})

await test('first run seeds the station list from SEED_STATIONS', () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  assert.equal(player.stations.get().length, SEEDED.length)
  assert.equal(player.station.get().name, SEEDED[0].name)
  assert.equal(ctx.storage.get('local.stations', null), null, 'seeding must not write until an edit')
})

await test('a stored list wins over the seed, and the last station may be gone', () => {
  const custom = { id: 'custom-1', name: 'My Tune', url: 'http://example.test/live', provider: 'Custom station', description: 'example.test' }
  const gone = { id: 'removed-preset', name: 'Deleted', url: 'https://example.test/gone' }
  const ctx = makeCtx({ 'local.stations': [custom], 'local.station': gone })
  const player = plugin.createPlayer(ctx)
  assert.deepEqual(player.stations.get().map(item => item.id), ['custom-1'])
  assert.equal(player.station.get().name, 'My Tune', 'a deleted last station falls back to the list head')
})

await test('stored entries that fail validation are dropped', () => {
  const ctx = makeCtx({ 'local.stations': [SEEDED[0], { id: 'bad', name: 'Bad', url: 'not-a-url' }] })
  const player = plugin.createPlayer(ctx)
  assert.equal(player.stations.get().length, 1)
})

await test('updateStation rewrites the name and the address together', () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  const target = player.stations.get()[0]
  player.favorite(target)
  assert.equal(player.updateStation(target, { name: '  Focus   Music  ', url: 'https://example.test/new.mp3' }), true)
  assert.equal(player.stations.get()[0].name, 'Focus Music')
  assert.equal(player.stations.get()[0].url, 'https://example.test/new.mp3')
  assert.equal(player.favorites.get()[0].url, 'https://example.test/new.mp3', 'a pin follows the edit')
  assert.equal(player.station.get().name, 'Focus Music')
  assert.equal(ctx.storage.get('local.station').name, 'Focus Music')

  assert.equal(player.updateStation(player.stations.get()[0], { name: 'Keep', url: 'not-a-url' }), false)
  assert.equal(player.stations.get()[0].url, 'https://example.test/new.mp3', 'an invalid address changes nothing')
  assert.equal(player.updateStation(player.stations.get()[0], { name: '   ', url: 'https://example.test/x' }), false)
})


await test('removeStation drops the station, its pin, and moves playback on', () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  const target = player.stations.get()[1]
  player.favorite(target)
  assert.equal(player.favorites.get().length, 1)
  player.removeStation(target)
  assert.ok(!player.stations.get().some(item => item.id === target.id))
  assert.equal(player.favorites.get().length, 0)
  assert.equal(ctx.storage.get('local.favorites').length, 0)
})

await test('removing the current station selects the next one instead of stopping', async () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  const target = player.stations.get()[0]
  player.removeStation(target)
  await new Promise(resolve => setTimeout(resolve, 30))
  assert.notEqual(player.station.get().id, target.id)
  assert.equal(player.station.get().id, player.stations.get()[0].id)
})

await test('removing every station leaves the player stopped, not crashed', async () => {
  const ctx = makeCtx({ 'local.stations': [{ id: 'only', name: 'Only', url: 'http://example.test/one' }] })
  const player = plugin.createPlayer(ctx)
  player.removeStation(player.stations.get()[0])
  await new Promise(resolve => setTimeout(resolve, 30))
  assert.equal(player.stations.get().length, 0)
  assert.equal(player.status.get(), 'paused')
})

await test('addStation stores a custom stream and rejects bad or duplicate URLs', () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  const added = player.addStation({ name: ' Shoutcast Tune ', url: 'http://example.test:8000/;' })
  assert.equal(added.added, true)
  assert.match(added.station.id, /^custom-/)
  assert.equal(added.station.name, 'Shoutcast Tune')
  assert.equal(player.stations.get().length, SEEDED.length + 1)
  assert.equal(ctx.storage.get('local.stations').length, SEEDED.length + 1)

  const duplicate = player.addStation({ name: 'Again', url: 'http://example.test:8000/;' })
  assert.equal(duplicate.added, false)
  assert.equal(duplicate.station.id, added.station.id)

  const invalid = player.addStation({ name: 'Bad', url: 'mailto:someone@example.test' })
  assert.equal(invalid.added, false)
  assert.equal(invalid.station, null)
})

await test('a nameless custom station falls back to its hostname', () => {
  const ctx = makeCtx()
  const player = plugin.createPlayer(ctx)
  const added = player.addStation({ name: '', url: 'http://radio.example.test:9000/stream' })
  assert.equal(added.station.name, 'radio.example.test')
})

await test('shoutcastStations maps the plugin route and drops unusable rows', async () => {
  const ctx = {
    ...makeCtx(),
    rest: async pathName => {
      assert.match(pathName, /^\/shoutcast\/(search\?q=jazz|top)/)
      return {
        stations: [
          { id: 'sc-1', name: 'Smooth Jazz UK', url: 'http://162.252.171.80:8002/stream', description: 'Smooth Jazz · 128 kbps', nowPlaying: 'Rod Lucas', homepage: 'https://bestsmoothjazz.com' },
          { id: 'sc-2', name: 'No Stream', url: null },
          { id: 3, name: 'Bad Id', url: 'http://example.test/x' },
          { id: 'sc-4', name: 'Duplicate', url: 'http://162.252.171.80:8002/stream' }
        ]
      }
    }
  }
  const { stations } = await plugin.shoutcastStations(ctx, 'jazz')
  assert.equal(stations.length, 1)
  assert.equal(stations[0].provider, 'Shoutcast')
  assert.equal(stations[0].nowPlaying, 'Rod Lucas')
  assert.equal(stations[0].homepage, 'https://bestsmoothjazz.com/')
})

await test('shoutcastStations asks for the top list when there is no query', async () => {
  const paths = []
  const ctx = { ...makeCtx(), rest: async pathName => { paths.push(pathName); return { stations: [] } } }
  await plugin.shoutcastStations(ctx, '')
  assert.deepEqual(paths, ['/shoutcast/top?limit=30'])
})

await test('shoutcastStations reports a missing backend instead of pretending it worked', async () => {
  await assert.rejects(() => plugin.shoutcastStations(makeCtx(), 'jazz'), /not loaded/)
})

await test('Radio Browser search returns unique, playable stations', async () => {
  const controller = new AbortController()
  const { stations, hls } = await plugin.searchStations('jazz', controller.signal)
  assert.ok(stations.length > 0, 'no results from Radio Browser')
  const ids = new Set(stations.map(item => item.id))
  const urls = new Set(stations.map(item => item.url))
  assert.equal(ids.size, stations.length, 'duplicate station ids')
  assert.equal(urls.size, stations.length, 'duplicate stream urls')
  for (const station of stations) {
    assert.match(station.url, /^https?:\/\//)
    assert.equal(station.provider, 'Radio Browser')
  }
  assert.equal(typeof hls, 'number')
})

await test('a Cyrillic query reaches the Latin spelling the directories index', async () => {
  assert.equal(plugin.transliterate('Хоризонт'), 'horizont')
  assert.equal(plugin.transliterate('Христо Ботев'), 'hristo botev')
  assert.deepEqual(plugin.searchTerms('Хоризонт'), ['Хоризонт', 'horizont'])
  assert.deepEqual(plugin.searchTerms('Horizont'), ['Horizont'])
  assert.equal(plugin.fold('Хоризонт'), plugin.fold('Horizont'))

  const controller = new AbortController()
  const { stations } = await plugin.searchStations('Хоризонт', controller.signal)
  assert.ok(stations.length > 0, 'the Cyrillic query found nothing')
  assert.ok(
    stations.some(item => item.name.toLowerCase().includes('horizont')),
    `no Horizont result: ${stations.map(item => item.name).slice(0, 5).join(' | ')}`
  )
})

await test('the popular list is non-empty and playable', async () => {
  const controller = new AbortController()
  const { stations } = await plugin.popularStations(controller.signal)
  assert.ok(stations.length > 10)
  for (const station of stations) assert.match(station.url, /^https?:\/\//)
})

await test('mediaFailure names the browser media error and the host', () => {
  const station = { url: 'http://79.98.108.170:8002' }
  assert.match(plugin.mediaFailure({ error: { code: 4 } }, station), /unsupported stream format \(79\.98\.108\.170\)/)
  assert.match(plugin.mediaFailure({ error: { code: 2 } }, station), /network error/)
  assert.match(plugin.mediaFailure(null, station), /the stream did not connect/)
})


await test('source labels cover the three picker tabs', () => {
  assert.deepEqual(Object.keys(plugin.SOURCE_LABELS), ['all', 'popular', 'shoutcast'])
})

const failed = results.filter(([status]) => status === 'FAIL')
for (const [status, name] of results) console.log(`${status}  ${name}`)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
