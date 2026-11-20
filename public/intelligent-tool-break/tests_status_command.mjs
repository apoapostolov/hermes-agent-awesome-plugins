import assert from 'node:assert/strict'
import fs from 'node:fs'
import test from 'node:test'

// Replays the shipped helpers so the proof is about desktop/plugin.js, not a retyped copy.
const source = process.env.ITB_PLUGIN_JS
  ? fs.readFileSync(process.env.ITB_PLUGIN_JS, 'utf8')
  : fs.readFileSync(new URL('./desktop/plugin.js', import.meta.url), 'utf8')
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor

function fnSource(signature) {
  const at = source.indexOf(signature)
  assert.notEqual(at, -1, `missing ${signature}`)
  const end = source.indexOf('\n}', at)
  assert.notEqual(end, -1, `unterminated ${signature}`)
  return source.slice(at, end + 2)
}

const sessionIdSource = fnSource('function sessionId() {')
const runSlashSource = fnSource('async function runSlash(command, quiet) {')
const poll = source.match(/function BreakBar\(\)[\s\S]*?const raw = ([^\r\n]+)/)
assert.ok(poll, 'BreakBar status poll not found')

test('the strip routes slash.exec with the runtime id and sends no session filter', async () => {
  const requests = []
  const host = {
    state: { focusedSessionId: { get: () => 'desktop-runtime-id' } },
    request: async (method, params) => {
      requests.push({ method, params })
      return { output: '' }
    },
    notify: () => {},
  }
  const run = AsyncFunction(
    'host',
    `${sessionIdSource}\n${runSlashSource}\nconst sid = sessionId()\nconst raw = ${poll[1].trim()}\nreturn raw`
  )
  await run(host)

  assert.equal(requests.length, 1)
  assert.equal(requests[0].method, 'slash.exec')
  assert.equal(requests[0].params.session_id, 'desktop-runtime-id')
  assert.equal(requests[0].params.command, '/break-status')
})
