// Trash-button tests. Lifts the TRASH_HELPERS block straight out of
// desktop/plugin.js so the assertions run the shipped decision instead of a
// retyped copy. Run: node tests_trash.mjs
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(join(here, 'desktop', 'plugin.js'), 'utf8')
const startMark = '// TRASH_HELPERS_START'
const endMark = '// TRASH_HELPERS_END'
const start = src.indexOf(startMark)
const end = src.indexOf(endMark)
if (start < 0 || end < 0 || end < start) {
  console.error(`FATAL trash helper markers not found (start=${start}, end=${end})`)
  process.exit(1)
}
const block = src.slice(start, end)
// The Function body is a slice of this repo's own desktop/plugin.js, not
// untrusted input, so evaluating it exercises the shipped helper.
const { trashTarget } = new Function(`${block}\nreturn { trashTarget }`)()

let pass = 0
let fail = 0
function eq(actual, expected, label) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) { pass++; return }
  fail++
  console.error(`FAIL ${label}\n  expected ${e}\n  actual   ${a}`)
}

// ── one key deletes the provider ───────────────────────────────────
eq(trashTarget({ pool: ['only'], pool_index: 0 }),
  { kind: 'provider', pool: ['only'], pool_index: 0, removed: [] },
  'single key deletes the provider')
eq(trashTarget({ pool: [] }), { kind: 'provider', pool: [], pool_index: 0, removed: [] },
  'empty pool deletes the provider')
eq(trashTarget({ pool: ['', '  '] }), { kind: 'provider', pool: [], pool_index: 0, removed: [] },
  'blank slots are not keys')
eq(trashTarget({}), { kind: 'provider', pool: [], pool_index: 0, removed: [] },
  'no pool deletes the provider')
eq(trashTarget(undefined), { kind: 'provider', pool: [], pool_index: 0, removed: [] },
  'missing config deletes the provider')

// ── two or more keys delete the first key ──────────────────────────
eq(trashTarget({ pool: ['k1', 'k2', 'k3'], pool_index: 0 }),
  { kind: 'key', pool: ['k2', 'k3'], pool_index: 0, removed: ['k1'] },
  'three keys, first active: keeps 2 and 3, active stays 0')
eq(trashTarget({ pool: ['k1', 'k2', 'k3'], pool_index: 1 }),
  { kind: 'key', pool: ['k2', 'k3'], pool_index: 0, removed: ['k1'] },
  'three keys, second active: active shifts up to 0')
eq(trashTarget({ pool: ['k1', 'k2', 'k3'], pool_index: 2 }),
  { kind: 'key', pool: ['k2', 'k3'], pool_index: 1, removed: ['k1'] },
  'three keys, third active: active shifts up to 1')
eq(trashTarget({ pool: ['a', 'b'] }),
  { kind: 'key', pool: ['b'], pool_index: 0, removed: ['a'] },
  'two keys leave one and delete the first')
eq(trashTarget({ pool: ['k1', 'k2'], pool_index: 1 }),
  { kind: 'key', pool: ['k2'], pool_index: 0, removed: ['k1'] },
  'two keys with the survivor active')

// ── hostile input ──────────────────────────────────────────────────
eq(trashTarget({ pool: ['', ' a ', null, 'b', '  '], pool_index: '1' }),
  { kind: 'key', pool: ['b'], pool_index: 0, removed: ['a'] },
  'blank slots are not keys, and the removed value is the trimmed first key')
eq(trashTarget({ pool: ['k1', 'k2', 'k3'], pool_index: 9 }),
  { kind: 'key', pool: ['k2', 'k3'], pool_index: 1, removed: ['k1'] },
  'out-of-range active index is clamped, not trusted')
eq(trashTarget({ pool: ['k1', 'k2', 'k3'], pool_index: -4 }),
  { kind: 'key', pool: ['k2', 'k3'], pool_index: 0, removed: ['k1'] },
  'negative active index falls back to the first key')
eq(trashTarget({ pool: ['k1', 42, 'k3'], pool_index: 1 }),
  { kind: 'key', pool: ['42', 'k3'], pool_index: 0, removed: ['k1'] },
  'non-string keys are compared as strings')

// ── the stored config is not mutated ───────────────────────────────
const conf = { pool: ['k1', 'k2', 'k3'], pool_index: 2, enabled: true }
trashTarget(conf)
eq(conf, { pool: ['k1', 'k2', 'k3'], pool_index: 2, enabled: true },
  'helper leaves the provider config untouched')

console.log(fail ? `trash: ${fail} FAILED, ${pass} passed` : `trash: ${pass} checks PASS`)
process.exit(fail ? 1 : 0)
