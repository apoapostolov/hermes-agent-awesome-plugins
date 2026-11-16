/**
 * HLS playback test in the real runtime.
 *
 * Chromium cannot open an HLS playlist without a demuxer, so "does HLS work"
 * can only be answered by an actual browser with Media Source Extensions. This
 * test loads the shipped `desktop/plugin.js` (stubbed only at the SDK boundary)
 * inside Electron, the runtime the plugin ships into, points `attachHls` at a
 * real BNR stream, and requires the audio clock to advance.
 *
 *   node tests/hls.electron.test.mjs
 *
 * Skips (exit 0) when Electron is not installed next to the desktop app.
 */
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'

const appDir = process.env.HERMES_DESKTOP_APP
  || 'C:/Users/theap/AppData/Local/hermes/hermes-agent/apps/desktop'
const electron = path.join(appDir, 'node_modules', 'electron', 'dist', 'electron.exe')
if (!existsSync(electron)) {
  console.log(`SKIP  Electron not found at ${electron}`)
  process.exit(0)
}

const STREAM = process.env.RADIO_PLUS_HLS_URL
  || 'https://lb-hls.cdn.bg/2032/fls/HrBotev.stream/playlist.m3u8'

const dir = mkdtempSync(path.join(tmpdir(), 'radio-plus-hls-'))

writeFileSync(path.join(dir, 'sdk.mjs'), `
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
`)
writeFileSync(path.join(dir, 'react.mjs'), 'export const useEffect = () => {}\nexport const useRef = () => ({ current: null })\nexport const useState = value => [value, () => {}]\n')
writeFileSync(path.join(dir, 'jsx.mjs'), 'export const jsx = () => null\nexport const jsxs = () => null\nexport const Fragment = null\n')

const source = readFileSync(path.resolve(import.meta.dirname, '..', 'desktop', 'plugin.js'), 'utf8')
  .replace("from '@hermes/plugin-sdk'", "from './sdk.mjs'")
  .replace("from 'react'", "from './react.mjs'")
  .replace("from 'react/jsx-runtime'", "from './jsx.mjs'")
  .concat('\nexport { attachHls, isHlsUrl, HLS }\n')
writeFileSync(path.join(dir, 'plugin.stub.mjs'), source)

writeFileSync(path.join(dir, 'index.html'), `<!doctype html>
<html>
  <body>
    <audio id="a"></audio>
    <script type="module">
      import { attachHls, isHlsUrl, HLS } from './plugin.stub.mjs'
      window.__probe = () => new Promise(resolve => {
        const log = []
        const audio = document.getElementById('a')
        const src = new URLSearchParams(location.search).get('src')
        const finish = () => resolve(JSON.stringify({
          src, version: HLS && HLS.version, supported: HLS && HLS.isSupported(),
          isHls: isHlsUrl(src),
          readyState: audio.readyState, currentTime: Number(audio.currentTime.toFixed(2)),
          paused: audio.paused, error: audio.error && audio.error.code,
          buffered: audio.buffered.length ? [Number(audio.buffered.start(0).toFixed(1)), Number(audio.buffered.end(0).toFixed(1))] : [],
          log: log.slice(0, 10)
        }))
        audio.muted = true
        const instance = attachHls(audio, { url: src }, reason => log.push('fatal: ' + reason))
        if (!instance) { log.push('attachHls returned null'); return finish() }
        audio.play().then(() => log.push('play:ok')).catch(error => log.push('play:' + error.name))
        setTimeout(finish, 14000)
      })
    </script>
  </body>
</html>
`)

writeFileSync(path.join(dir, 'main.js'), `const { app, BrowserWindow } = require('electron')
const fs = require('node:fs')
const path = require('node:path')
const { pathToFileURL } = require('node:url')

app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required')
app.commandLine.appendSwitch('no-sandbox')
app.disableHardwareAcceleration()

app.whenReady().then(async () => {
  try {
    const win = new BrowserWindow({ show: false, width: 480, height: 320 })
    const src = process.argv[process.argv.length - 1]
    await win.loadURL(pathToFileURL(path.join(__dirname, 'index.html')).href + '?src=' + encodeURIComponent(src))
    const result = await win.webContents.executeJavaScript('window.__probe()')
    fs.writeFileSync(path.join(__dirname, 'result.json'), result, 'utf8')
    app.exit(0)
  } catch (error) {
    fs.writeFileSync(path.join(__dirname, 'error.txt'), String((error && error.stack) || error), 'utf8')
    app.exit(1)
  }
})
`)

const runner = path.join(dir, 'run.cjs')
writeFileSync(runner, `const { spawn } = require('node:child_process')
const child = spawn(${JSON.stringify(electron)}, ['main.js', ${JSON.stringify(STREAM)}], {
  cwd: __dirname, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true
})
child.stdout.on('data', chunk => process.stdout.write(chunk))
child.stderr.on('data', chunk => process.stdout.write(chunk))
child.on('exit', code => process.exit(code || 0))
`)

const code = await new Promise(resolve => {
  const child = spawn(process.execPath, [runner], { cwd: dir, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true })
  child.stdout.on('data', chunk => process.stdout.write(chunk))
  child.stderr.on('data', chunk => process.stdout.write(chunk))
  child.on('exit', resolve)
})

const errorFile = path.join(dir, 'error.txt')
if (existsSync(errorFile)) {
  console.log(`FAIL  electron reported an error\n    ${readFileSync(errorFile, 'utf8').split('\n').slice(0, 6).join('\n    ')}`)
  process.exit(1)
}
const resultFile = path.join(dir, 'result.json')
if (!existsSync(resultFile)) {
  console.log(`FAIL  no result written (electron exit ${code})`)
  process.exit(1)
}

const result = JSON.parse(readFileSync(resultFile, 'utf8'))
console.log(JSON.stringify(result, null, 1))

const failures = []
if (!result.supported) failures.push('hls.js reports no Media Source support')
if (!result.isHls) failures.push('isHlsUrl did not recognise the playlist')
if (result.error) failures.push(`media error ${result.error}`)
if (!(result.currentTime > 2)) failures.push(`audio clock did not advance (currentTime ${result.currentTime})`)
if (result.log.some(entry => entry.startsWith('fatal:'))) failures.push(`fatal: ${result.log.find(e => e.startsWith('fatal:'))}`)

if (failures.length) {
  console.log(`FAIL  ${failures.join('; ')}`)
  process.exit(1)
}
console.log(`PASS  HLS audio advanced to ${result.currentTime}s (hls.js ${result.version})`)
