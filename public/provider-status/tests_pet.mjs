// Pet bubble tests. Lifts the PET_HELPERS block straight out of desktop/plugin.js
// so the test always exercises the shipped code, then drives it with stub pets
// and settings. Run: node tests_pet.mjs
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(join(here, 'desktop', 'plugin.js'), 'utf8')
const startMark = '// PET_HELPERS_START'
const endMark = '// PET_HELPERS_END'
const start = src.indexOf(startMark)
const end = src.indexOf(endMark)
if (start < 0 || end < 0 || end < start) {
  console.error(`FATAL pet helper markers not found (start=${start}, end=${end})`)
  process.exit(1)
}
// The Function body is a slice of this repo's own desktop/plugin.js between the
// PET_HELPERS markers, not untrusted input, so evaluating it exercises the
// shipped helpers rather than a hand-copied duplicate that can drift.
const block = src.slice(start, end)
const H = new Function(
  `${block}\nreturn { PET_DEFAULTS, PET_SOURCES, PET_METRICS, PET_SAME_TEXT_MS, petNormalize, ` +
  `petFromRest, petAllowed, petPayload, petPick, petPush }`,
)()

let pass = 0
let fail = 0
function eq(actual, expected, label) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a === e) { pass++; return }
  fail++
  console.error(`FAIL ${label}\n  expected ${e}\n  actual   ${a}`)
}
function ok(cond, label) {
  if (cond) { pass++; return }
  fail++
  console.error(`FAIL ${label}`)
}
const cfg = (over) => H.petNormalize(over)
const payload = (id, name, status, over) => H.petPayload(id, name, status, cfg(over))

// ── defaults ───────────────────────────────────────────────────────
eq(H.PET_DEFAULTS.source, 'active', 'default source is active')
eq(H.PET_DEFAULTS.metric, 'auto', 'default metric is auto')
ok(H.PET_DEFAULTS.show_quota === true, 'pet bubble on by default')
ok(H.PET_DEFAULTS.show_provider_name === true, 'provider name on by default')
ok(H.PET_DEFAULTS.show_percent_sign === true, 'percent sign on by default')
ok(H.PET_DEFAULTS.show_unit_word === true, 'unit word on by default')
ok(H.PET_DEFAULTS.show_errors === true, 'errors shown by default')
ok(H.PET_DEFAULTS.fallback_to_worst === true, 'fall back to worst by default')

// ── message per provider kind ──────────────────────────────────────
eq(payload('grok', 'Grok', { ok: true, percent: 61 }),
  { text: 'Grok 39% left', tone: 'info' }, 'exhaust shows remaining')
eq(payload('glm', 'GLM', { ok: true, percent: 42 }),
  { text: 'GLM 42% used', tone: 'info' }, 'increase window shows used')
eq(payload('deepseek', 'DeepSeek', { ok: true, balance: 12.4 }),
  { text: 'DeepSeek $12.40 left', tone: 'info' }, 'credit provider shows dollars')
eq(payload('tavily', 'Tavily', { ok: true, percent: 12.5 }),
  { text: 'Tavily 88% left', tone: 'info' }, 'tavily keeps one decimal')
eq(payload('grok', 'Grok', { ok: false, needs_auth: true }),
  { text: 'Grok auth?', tone: 'error' }, 'auth error is named')
eq(payload('grok', 'Grok', { ok: false, no_plan: true }),
  { text: 'Grok no plan', tone: 'error' }, 'missing plan is named')
eq(payload('grok', 'Grok', null), null, 'no status means no bubble')

// ── tone thresholds ────────────────────────────────────────────────
eq(payload('grok', 'Grok', { ok: true, percent: 80 }).tone, 'wait', '20% left warns')
eq(payload('grok', 'Grok', { ok: true, percent: 90 }).tone, 'error', '10% left errors')
eq(payload('grok', 'Grok', { ok: true, percent: 79 }).tone, 'info', '21% left is calm')
eq(payload('glm', 'GLM', { ok: true, percent: 80 }).tone, 'wait', '80% used warns (mirrored)')
eq(payload('glm', 'GLM', { ok: true, percent: 30 }).tone, 'info', '30% used is calm')
eq(payload('grok', 'Grok', { ok: true, percent: 85 }, { warn_remaining: 30 }).tone,
  'wait', 'warn threshold is configurable')
eq(payload('deepseek', 'DeepSeek', { ok: true, balance: 4.99 }).tone, 'wait', '$4.99 warns')
eq(payload('deepseek', 'DeepSeek', { ok: true, balance: 5 }).tone, 'info', '$5.00 is calm')
eq(payload('deepseek', 'DeepSeek', { ok: true, balance: 0.5 }).tone, 'error', '$0.50 errors')
eq(payload('deepseek', 'DeepSeek', { ok: true, balance: 7 }, { warn_balance: 10 }).tone,
  'wait', 'warn balance is configurable')

// ── message toggles ────────────────────────────────────────────────
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { show_provider_name: false }),
  { text: '39% left', tone: 'info' }, 'provider name can be dropped')
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { show_percent_sign: false }),
  { text: 'Grok 39 left', tone: 'info' }, 'percent sign can be dropped')
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { show_unit_word: false }),
  { text: 'Grok 39%', tone: 'info' }, 'unit word can be dropped')
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { show_quota: false }), null,
  'master toggle silences the bubble')
eq(payload('grok', 'Grok', { ok: false }, { show_errors: false }), null,
  'errors can be hidden')

// ── metric override ────────────────────────────────────────────────
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { metric: 'used' }),
  { text: 'Grok 61% used', tone: 'info' }, 'metric=used shows the used number')
eq(payload('glm', 'GLM', { ok: true, percent: 42 }, { metric: 'remaining' }),
  { text: 'GLM 58% left', tone: 'info' }, 'metric=remaining shows what is left')
eq(payload('grok', 'Grok', { ok: true, balance: 3 }, { metric: 'balance' }).text,
  'Grok $3.00 left', 'metric=balance uses dollars when present')
eq(payload('grok', 'Grok', { ok: true, percent: 61 }, { metric: 'balance' }).text,
  'Grok 39% left', 'metric=balance falls back when there is no balance')

// ── provider allowlist ─────────────────────────────────────────────
ok(!H.petAllowed('glm', cfg({ providers: 'grok, codex' })), 'allowlist excludes glm')
ok(H.petAllowed('grok', cfg({ providers: 'grok, codex' })), 'allowlist includes grok')
ok(H.petAllowed('glm', cfg({ providers: '' })), 'empty allowlist includes everything')
eq(payload('glm', 'GLM', { ok: true, percent: 42 }, { providers: 'grok' }), null,
  'allowlisted-out provider gets no bubble')

// ── provider choice (current vs worst) ─────────────────────────────
const entries = [
  ['grok', { name: 'Grok', ok: true, percent: 39 }],        // 61% left, calm
  ['glm', { name: 'GLM', ok: true, percent: 95 }],          // 5% left, error
]
eq(H.petPick(entries, 'grok', cfg({})), ['grok', entries[0][1]],
  'default picks the active provider even when another is worse')
eq(H.petPick(entries, 'grok', cfg({ source: 'worst' })), ['glm', entries[1][1]],
  'source=worst picks the lowest quota')
eq(H.petPick(entries, 'grok', cfg({ source: 'worst', providers: 'grok' })),
  ['grok', entries[0][1]], 'worst respects the allowlist')
eq(H.petPick(entries, null, cfg({})), ['glm', entries[1][1]],
  'no active provider falls back to worst')
const noQuota = [['grok', { name: 'Grok', ok: true }]]
eq(H.petPick(noQuota, 'grok', cfg({ fallback_to_worst: false })), [null, null],
  'no fallback leaves the bubble empty')
eq(H.petPick(entries, 'codex', cfg({})), ['glm', entries[1][1]],
  'active provider with no data falls back to worst')
eq(H.petPick([], null, cfg({})), [null, null], 'no enabled providers means no bubble')
eq(H.petPick(entries, 'grok', cfg({ show_quota: false })), [null, null],
  'master toggle also disables picking')

// ── settings mapping from the backend ──────────────────────────────
eq(H.petFromRest(null), H.PET_DEFAULTS, 'unreachable endpoint yields defaults')
eq(H.petFromRest({
  pet_show_quota: false, pet_source: 'worst', pet_metric: 'used',
  pet_show_provider_name: false, pet_show_percent_sign: false, pet_show_unit_word: false,
  pet_show_errors: false, pet_fallback_to_worst: false, pet_providers: 'grok',
  pet_warn_remaining: 30, pet_error_remaining: 15, pet_warn_balance: 10,
  pet_error_balance: 2, pet_ttl_seconds: 20,
}), {
  show_quota: false,
  source: 'worst',
  fallback_to_worst: false,
  metric: 'used',
  show_provider_name: false,
  show_percent_sign: false,
  show_unit_word: false,
  show_errors: false,
  providers: 'grok',
  warn_remaining: 30,
  error_remaining: 15,
  warn_balance: 10,
  error_balance: 2,
  ttl_seconds: 20,
}, 'every backend key maps onto the helper config')
eq(Object.keys(H.petFromRest({
  pet_show_quota: false, pet_source: 'worst', pet_metric: 'used',
  pet_show_provider_name: false, pet_show_percent_sign: false, pet_show_unit_word: false,
  pet_show_errors: false, pet_fallback_to_worst: false, pet_providers: 'grok',
  pet_warn_remaining: 30, pet_error_remaining: 15, pet_warn_balance: 10,
  pet_error_balance: 2, pet_ttl_seconds: 20,
})).sort(), Object.keys(H.PET_DEFAULTS).sort(),
  'config carries exactly the shipped keys (no extra, none missing)')
eq(H.petFromRest({ pet_metric: 'nonsense', pet_source: 'nonsense' }).metric, 'auto',
  'unknown metric falls back')
eq(H.petFromRest({ pet_metric: 'nonsense' }).source, 'active', 'unknown source falls back')
eq(H.petFromRest({ pet_warn_remaining: 'thirty' }).warn_remaining, 20,
  'unparseable number falls back')
eq(H.petFromRest({ pet_ttl_seconds: 999 }).ttl_seconds, 60, 'ttl clamps high')
eq(H.petFromRest({ pet_ttl_seconds: 0 }).ttl_seconds, 8, 'zero ttl falls back')
eq(H.petFromRest({ pet_providers: 42 }).providers, '', 'non-string allowlist falls back')

// ── push behaviour against a stub pet ──────────────────────────────
function stubPet(hidden = false, withSay = true) {
  const pet = { says: [], clears: 0, hidden }
  if (hidden) pet.visible = { get: () => false }
  if (withSay) {
    pet.say = (text, opts) => pet.says.push({ text, ...opts })
    pet.clear = (id) => { pet.clears += 1; pet.clearedId = id }
  }
  return pet
}
const st = () => ({ last: '', at: 0 })
const grokStatus = { name: 'Grok', ok: true, percent: 61 }

const pet = stubPet()
H.petPush(pet, st(), 'grok', 'Grok', grokStatus, cfg({}), 1000)
eq(pet.says.length, 1, 'first push says the bubble')
eq(pet.says[0].text, 'Grok 39% left', 'first push text')
eq(pet.says[0].tone, 'info', 'first push tone')
eq(pet.says[0].id, 'quota', 'first push id')
eq(pet.says[0].ttlMs, 8000, 'first push ttl')

const state = st()
const pet2 = stubPet()
H.petPush(pet2, state, 'grok', 'Grok', grokStatus, cfg({}), 1000)
H.petPush(pet2, state, 'grok', 'Grok', grokStatus, cfg({}), 1100)
eq(pet2.says.length, 1, 'identical text inside the window is skipped')
H.petPush(pet2, state, 'grok', 'Grok', grokStatus, cfg({}), 2300)
eq(pet2.says.length, 2, 'identical text after the window says again')

const pet3 = stubPet()
const state3 = st()
H.petPush(pet3, state3, 'grok', 'Grok', grokStatus, cfg({}), 1000)
H.petPush(pet3, state3, 'grok', 'Grok', { name: 'Grok', ok: true, percent: 85 }, cfg({}), 1100)
eq(pet3.says.length, 2, 'a changed value is not skipped')
eq(pet3.says[1].tone, 'wait', 'the changed value carries its new tone')

const pet4 = stubPet()
const state4 = st()
H.petPush(pet4, state4, 'grok', 'Grok', grokStatus, cfg({ ttl_seconds: 20 }), 1000)
eq(pet4.says[0].ttlMs, 20000, 'ttl comes from settings')
H.petPush(pet4, state4, null, null, null, cfg({ ttl_seconds: 20 }), 1100)
eq(pet4.clears, 1, 'losing the value clears the bubble')
eq(pet4.clearedId, 'quota', 'clear targets the quota id')
const pet5 = stubPet()
H.petPush(pet5, st(), null, null, null, cfg({}), 1000)
eq(pet5.clears, 0, 'nothing to clear when nothing was said')

const pet6 = stubPet(true)
H.petPush(pet6, st(), 'grok', 'Grok', grokStatus, cfg({}), 1000)
eq(pet6.says.length, 0, 'a hidden pet stays silent')
const pet7 = stubPet(false, false)
H.petPush(pet7, st(), 'grok', 'Grok', grokStatus, cfg({}), 1000)
eq(pet7.says.length, 0, 'a host without say() does not throw')
H.petPush(null, st(), 'grok', 'Grok', grokStatus, cfg({}), 1000)
ok(true, 'a missing pet door does not throw')

// ── known-missing control: prove an absence check can fail ─────────
const ctrlSrc = readFileSync(join(here, 'desktop', 'plugin.js'), 'utf8')
ok(!ctrlSrc.includes('function pickPetProvider('), 'control: old picker is gone from plugin.js')

console.log(`\n${pass} passed, ${fail} failed`)
process.exit(fail ? 1 : 0)
