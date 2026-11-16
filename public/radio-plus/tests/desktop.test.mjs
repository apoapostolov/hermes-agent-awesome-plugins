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
  .replaceAll("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replaceAll("from 'react'", "from './react.mjs'")
  .replace("from 'react/jsx-runtime'", "from './jsx.mjs'")
  .concat(`
export {
  createPlayer, popularStations, sameStation, searchStations, shoutcastStations, tuneinStations, nowPlaying,
  streamUrl, uniqueStations, validStation, SEED_STATIONS, SOURCE_LABELS,
  transliterate, fold, searchTerms, mediaFailure, isHlsUrl, rowsToStations, matchScore
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
  assert.deepEqual(paths, ['/shoutcast/top?limit=30&offset=0'])
})

await test('shoutcastStations asks for a page and says whether rows are left', async () => {
  const paths = []
  const ctx = {
    ...makeCtx(),
    rest: async pathName => {
      paths.push(pathName)
      return { stations: [{ id: 'sc-1', name: 'One', url: 'http://example.test/1' }], skipped: 0, count: 90, next: 30 }
    }
  }
  const first = await plugin.shoutcastStations(ctx, 'jazz')
  assert.match(paths[0], /offset=0/)
  assert.equal(first.hasMore, true, 'rows are left behind the first page')
  assert.equal(first.nextOffset, 30)
  await plugin.shoutcastStations(ctx, 'jazz', { offset: 30 })
  assert.match(paths[1], /offset=30/, 'the second call asks for the next slice')
})

await test('shoutcastStations stops asking once the directory is spent', async () => {
  const ctx = {
    ...makeCtx(),
    rest: async () => ({ stations: [{ id: 'sc-1', name: 'One', url: 'http://example.test/1' }], skipped: 0, count: 30, next: 30 })
  }
  const page = await plugin.shoutcastStations(ctx, 'jazz', { offset: 30 })
  assert.equal(page.hasMore, false, 'next reached the end of the list')
})

await test('tuneinStations maps the plugin route and drops unusable rows', async () => {
  const paths = []
  const ctx = {
    ...makeCtx(),
    rest: async pathName => {
      paths.push(pathName)
      return {
        stations: [
          { id: 'ti-s1', name: 'One Jazz', url: 'https://streaming.broadcast.radio/onejazz', description: '128 kbps · MP3', nowPlaying: 'Espen Eriksen Trio' },
          { id: 'ti-s2', name: 'No Stream', url: null },
          { id: 7, name: 'Bad Id', url: 'https://example.test/x' },
          { id: 'ti-s3', name: 'Duplicate', url: 'https://streaming.broadcast.radio/onejazz' }
        ],
        skipped: 2,
        count: 84,
        next: 30
      }
    }
  }
  const page = await plugin.tuneinStations(ctx, 'jazz')
  assert.equal(paths.length, 1, 'one term means one request')
  assert.match(paths[0], /^\/tunein\/search\?q=jazz&limit=30&offset=0$/)
  assert.equal(page.stations.length, 1, 'a row without a stream or with a bad id is dropped')
  assert.equal(page.stations[0].provider, 'TuneIn')
  assert.equal(page.stations[0].nowPlaying, 'Espen Eriksen Trio')
  assert.equal(page.skipped, 2, 'the route says how many rows it could not resolve')
  assert.equal(page.hasMore, true, 'eighty-four rows are more than one page')
  assert.equal(page.nextOffset, 30)
})

await test('tuneinStations asks for the next slice by offset', async () => {
  const paths = []
  const ctx = {
    ...makeCtx(),
    rest: async pathName => {
      paths.push(pathName)
      return { stations: [{ id: 'ti-s1', name: 'One', url: 'https://example.test/1' }], skipped: 0, count: 84, next: 60 }
    }
  }
  const page = await plugin.tuneinStations(ctx, 'jazz', { offset: 30 })
  assert.match(paths[0], /offset=30/)
  assert.equal(page.nextOffset, 60)
  assert.equal(page.hasMore, true)
})

await test('tuneinStations stops at the end of the list', async () => {
  const ctx = {
    ...makeCtx(),
    rest: async () => ({ stations: [{ id: 'ti-s1', name: 'One', url: 'https://example.test/1' }], skipped: 0, count: 84, next: 84 })
  }
  const page = await plugin.tuneinStations(ctx, 'jazz', { offset: 60 })
  assert.equal(page.hasMore, false, 'next reached the end of the list')
})

await test('tuneinStations searches a genre tag and drops a country tag', async () => {
  const paths = []
  const ctx = { ...makeCtx(), rest: async pathName => { paths.push(pathName); return { stations: [] } } }
  const none = await plugin.tuneinStations(ctx, 'country:bg')
  assert.deepEqual(paths, [], 'a country-only query is not sent as the literal tag')
  assert.equal(none.stations.length, 0)
  await plugin.tuneinStations(ctx, 'genre:jazz')
  assert.match(paths[0], /q=jazz&/, 'the genre is the text TuneIn searches for')
})

await test('a directory tab shows its own rows, not the station carried over from All', () => {
  const playing = { id: 'chillsynth', name: 'Chillsynth', url: 'https://stream.nightride.fm/chillsynth.mp3' }
  const results = [
    { id: 'ti-s1', name: 'One Jazz', url: 'https://stream.test/one' },
    { id: 'ti-s2', name: 'Two Jazz', url: 'https://stream.test/two' }
  ]
  const tab = plugin.listRows(results, { browseStation: playing, current: playing, ownList: false })
  assert.deepEqual(tab.map(item => item.id), ['ti-s1', 'ti-s2'], 'the TuneIn tab lists what TuneIn answered')
  const all = plugin.listRows(results, { browseStation: playing, current: playing, ownList: true })
  assert.deepEqual(all.map(item => item.id), ['chillsynth', 'ti-s1', 'ti-s2'], 'All keeps the playing station above its results')
})

await test('a tab that already lists the playing station does not repeat it', () => {
  const playing = { id: 'ti-s1', name: 'One Jazz', url: 'https://stream.test/one' }
  const results = [playing, { id: 'ti-s2', name: 'Two Jazz', url: 'https://stream.test/two' }]
  for (const ownList of [true, false]) {
    const rows = plugin.listRows(results, { browseStation: playing, current: playing, ownList })
    assert.deepEqual(rows.map(item => item.id), ['ti-s1', 'ti-s2'], `no duplicate with ownList=${ownList}`)
  }
})

await test('an empty directory answer stays empty instead of showing a carried row', () => {
  const playing = { id: 'chillsynth', name: 'Chillsynth', url: 'https://stream.nightride.fm/chillsynth.mp3' }
  assert.deepEqual(plugin.listRows([], { browseStation: playing, current: playing, ownList: false }), [])
  assert.deepEqual(plugin.listRows([], { browseStation: playing, current: playing, ownList: true }).map(item => item.id), ['chillsynth'])
})

await test('missingDefaults names only the shipped stations you deleted', () => {
  const seeds = plugin.SEED_STATIONS
  assert.equal(seeds.length, 7, 'the shipped list is the seven starter stations')
  const current = [
    { ...seeds[0], name: 'Renamed by hand' },
    { id: 'mine', name: 'Mine', url: 'https://example.test/mine' }
  ]
  const missing = plugin.missingDefaults(current)
  assert.deepEqual(missing.map(item => item.id), seeds.slice(1).map(item => item.id))
  assert.ok(!missing.some(item => item.id === seeds[0].id), 'a renamed shipped station is still present')
  assert.ok(!missing.some(item => item.id === 'mine'), 'your own station is never a candidate')
  assert.deepEqual(plugin.missingDefaults(seeds), [], 'nothing is missing from the full list')
})

await test('nowPlaying asks the route for the title of one address', async () => {
  const paths = []
  const ctx = {
    ...makeCtx(),
    rest: async pathName => {
      paths.push(pathName)
      return { ok: true, title: 'Sakunera - After Eight', station: 'Nightride' }
    }
  }
  const result = await plugin.nowPlaying(ctx, 'https://stream.nightride.fm/nightride.mp3')
  assert.match(paths[0], /^\/now-playing\?url=https%3A%2F%2Fstream\.nightride\.fm%2Fnightride\.mp3$/)
  assert.equal(result.title, 'Sakunera - After Eight')
})

await test('nowPlaying answers empty when the plugin route is missing', async () => {
  const ctx = { ...makeCtx() }
  delete ctx.rest
  const result = await plugin.nowPlaying(ctx, 'https://stream.example/live.mp3')
  assert.equal(result.ok, false, 'a build without the route must not throw into the panel')
})

await test('a track credit splits the artist out of the announced title', () => {
  const credit = plugin.trackCredit({ title: 'Aphex Twin - Xtal' })
  assert.equal(credit.artist, 'Aphex Twin')
  assert.equal(credit.title, 'Xtal')
  const plain = plugin.trackCredit({ title: 'Morning News' })
  assert.equal(plain.artist, '', 'a show name is not split into an artist')
})

await test('the popular list pages with an offset', async () => {
  const controller = new AbortController()
  const first = await plugin.popularStations(controller.signal, { limit: 20 })
  const second = await plugin.popularStations(controller.signal, { limit: 20, offset: 20 })
  assert.ok(first.stations.length > 0 && second.stations.length > 0, 'both pages came back')
  assert.equal(first.hasMore, true, 'a full page means more behind it')
  assert.equal(first.nextOffset, 20)
  const firstIds = new Set(first.stations.map(item => item.id))
  const overlap = second.stations.filter(item => firstIds.has(item.id))
  assert.equal(overlap.length, 0, `page two repeated ${overlap.length} stations`)
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

await test('isHlsUrl recognises a playlist address and nothing else', () => {
  assert.equal(plugin.isHlsUrl('https://lb-hls.cdn.bg/2032/fls/HrBotev.stream/playlist.m3u8'), true)
  assert.equal(plugin.isHlsUrl('https://host/live.m3u8?token=1'), true)
  assert.equal(plugin.isHlsUrl('http://host/stream.mp3'), false)
  assert.equal(plugin.isHlsUrl('http://host/m3u8'), false)
  assert.equal(plugin.isHlsUrl(undefined), false)
})

await test('an HLS row is hidden and counted in this edition', () => {
  const rows = [
    { stationuuid: 'a', name: 'BNR - Hristo Botev', url_resolved: 'https://lb-hls.cdn.bg/2032/fls/HrBotev.stream/playlist.m3u8', hls: true, tags: 'public radio' },
    { stationuuid: 'b', name: 'BNR Horizont', url_resolved: 'https://play.global.audio/testb.aac', hls: false, tags: 'news' }
  ]
  const { stations, hls } = plugin.rowsToStations(rows)
  assert.equal(stations.length, 1, 'the listed edition cannot play an HLS playlist')
  assert.equal(hls, 1, 'the hidden HLS row must still be counted for the panel note')
})

await test('the named station outranks foreign lookalikes', async () => {
  const controller = new AbortController()
  const { stations } = await plugin.searchStations('Хоризонт', controller.signal)
  const top = stations.slice(0, 3).map(item => item.name)
  assert.ok(/horizont|хоризонт/i.test(top[0]), `a lookalike led: ${top.join(' | ')}`)
  assert.ok(top.some(name => /bnr/i.test(name)), `no BNR row in the top three: ${top.join(' | ')}`)
})

await test('a whole-word match beats a longer word that merely starts with it', () => {
  const terms = ['Horizont']
  const exact = plugin.matchScore({ name: 'BNR Horizont' }, terms)
  const lookalike = plugin.matchScore({ name: 'Horizonte 107.9 FM' }, terms)
  const inner = plugin.matchScore({ name: 'Jovem Pan FM - Belo Horizonte' }, terms)
  assert.ok(exact > lookalike, `exact ${exact} should beat lookalike ${lookalike}`)
  assert.ok(lookalike >= inner, `lookalike ${lookalike} vs inner ${inner}`)
  assert.equal(plugin.matchScore({ name: 'Smooth Jazz' }, ['Horizont']), 0)
})

await test('country: and genre: are parsed out of the search text', () => {
  assert.deepEqual(plugin.parseQuery('country:bg'), { name: '', country: 'bg', genre: '' })
  assert.deepEqual(plugin.parseQuery('genre:jazz'), { name: '', country: '', genre: 'jazz' })
  assert.deepEqual(plugin.parseQuery('jazz country:bg'), { name: 'jazz', country: 'bg', genre: '' })
  assert.deepEqual(plugin.parseQuery('COUNTRY:BG'), { name: '', country: 'BG', genre: '' })
  assert.deepEqual(plugin.parseQuery('genre:"smooth jazz"'), { name: '', country: '', genre: 'smooth jazz' })
  assert.deepEqual(plugin.parseQuery('Хоризонт'), { name: 'Хоризонт', country: '', genre: '' })
  assert.deepEqual(plugin.parseQuery('   '), { name: '', country: '', genre: '' })
})

await test('a tag becomes the parameter the directory expects', () => {
  const params = query => Object.fromEntries(plugin.searchParams(plugin.parseQuery(query)))
  assert.equal(params('country:bg').countrycode, 'BG', 'a two-letter country is a code')
  assert.equal(params('country:uk').countrycode, 'GB', 'uk is the United Kingdom, whose code is GB')
  assert.equal(params('country:UK').countrycode, 'GB', 'the alias ignores case')
  assert.equal(params('country:usa').countrycode, 'US', 'a short name maps to its code')
  assert.equal(params('country:bulgaria').country, 'bulgaria', 'a longer country is a name')
  assert.equal(params('genre:jazz').tag, 'jazz')
  assert.equal(params('genre:jazz').name, undefined, 'a tag-only query sends no name')
  const both = params('jazz country:bg genre:smooth')
  assert.equal(both.name, 'jazz')
  assert.equal(both.countrycode, 'BG')
  assert.equal(both.tag, 'smooth')
})

await test('a country tag returns that country', async () => {
  const controller = new AbortController()
  const uk = await plugin.searchStations('country:uk', controller.signal)
  assert.ok(uk.stations.length > 0, 'no stations came back for country:uk')
  // The same country under its ISO code answers with the same rows.
  const gb = await plugin.searchStations('country:gb', controller.signal)
  const ids = new Set(gb.stations.map(item => item.id))
  assert.ok(uk.stations.some(item => ids.has(item.id)), 'uk and gb disagree about the United Kingdom')
})

await test('a genre tag returns that genre', async () => {
  const controller = new AbortController()
  const { stations } = await plugin.searchStations('genre:jazz', controller.signal)
  assert.ok(stations.length > 0, 'no stations came back for genre:jazz')
})

await test('a page is a limit and an offset, and the first page sends no offset', () => {
  const first = Object.fromEntries(plugin.searchParams({ name: 'jazz' }))
  assert.equal(first.limit, '40')
  assert.equal(first.offset, undefined, 'the first page asks for no offset')
  const second = Object.fromEntries(plugin.searchParams({ name: 'jazz', offset: 40 }))
  assert.equal(second.offset, '40')
  assert.equal(second.limit, '40')
})

await test('a full page reports more behind it, an exhausted page does not', async () => {
  const controller = new AbortController()
  const full = await plugin.searchStations('genre:jazz', controller.signal, { limit: 40 })
  assert.equal(full.hasMore, true, 'a full page means more rows exist')
  // Nothing matches, so the directory returned fewer rows than the limit.
  const none = await plugin.searchStations('zzzzqqqx', controller.signal, { limit: 40 })
  assert.equal(none.stations.length, 0)
  assert.equal(none.hasMore, false, 'a short page means the list is finished')
})

await test('the second page continues where the first stopped', async () => {
  const controller = new AbortController()
  const first = await plugin.searchStations('country:uk', controller.signal, { limit: 20 })
  const second = await plugin.searchStations('country:uk', controller.signal, { limit: 20, offset: 20 })
  assert.ok(first.stations.length > 0 && second.stations.length > 0, 'both pages came back')
  const firstIds = new Set(first.stations.map(item => item.id))
  const overlap = second.stations.filter(item => firstIds.has(item.id))
  assert.equal(overlap.length, 0, `page two repeated ${overlap.length} rows from page one`)
})

await test('source labels cover the four picker tabs', () => {
  assert.deepEqual(Object.keys(plugin.SOURCE_LABELS), ['all', 'popular', 'shoutcast', 'tunein'])
})

const failed = results.filter(([status]) => status === 'FAIL')
for (const [status, name] of results) console.log(`${status}  ${name}`)
console.log(`\n${results.length - failed.length}/${results.length} passed`)
process.exit(failed.length ? 1 : 0)
