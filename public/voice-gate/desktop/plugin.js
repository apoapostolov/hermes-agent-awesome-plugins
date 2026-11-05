import * as sdk from '@hermes/plugin-sdk'
import { createElement as h, useEffect, useMemo, useRef, useState } from 'react'

const { Button, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Switch, Textarea, host, useValue } = sdk

export const EXCEPTIONS_EXAMPLE = 'signposting: README.md, *.generated.md\nbold_lead_bullets: CHANGELOG.md\nmarketing_adjectives: release-notes.txt'
const VALE_URL = 'https://github.com/vale-cli/vale#install'
const hint = { color: 'var(--ui-text-tertiary)', fontSize: 12, lineHeight: 1.5, margin: 0 }
const grid = { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 260px), 1fr))', gap: 16 }
const CHOICE_LABELS = { warn: 'Ask once', improve: 'Review and revise', skip: 'Off', off: 'Off', advisory: 'Include Vale findings', auto: 'Choose automatically', docs: 'Documentation', 'technical-blog': 'Technical article', blog: 'Article or essay', casual: 'Conversation', linkedin: 'Social post', 'investor-email': 'Investor email', fiction: 'Fiction' }
const FORMATTING = new Set(['em_dashes', 'bold_pseudo_headings', 'bold_lead_bullets', 'hashtag_stuffing', 'title_case_headings', 'decorative_headers', 'label_periods', 'unnecessary_hyphenation'])
const DELIVERY = new Set(['assistant_residue', 'template_residue', 'tool_fingerprints', 'citation_residue', 'reasoning_residue', 'closing_offers'])
const WORDS = new Set(['buzzwords', 'marketing_adjectives', 'banned_words', 'significance_inflation', 'copula_avoidance', 'hedges', 'filler', 'transitions', 'trailing_qualifiers', 'vague_authority', 'real_actual', 'moral_category', 'tier1a', 'tier1b', 'tier2', 'tier3', 'tier3_phrases', 'load_bearing_metaphor', 'significance_adverbs'])
export const SETTINGS_TIMEOUT_MS = 120_000
const pendingLoads = new Map()

export async function settingsRequest(route, params) {
  let timer
  try {
    return await Promise.race([
      host.requestProfile(route, 'plugins.manage', { ...params, profile: route.targetProfile }, SETTINGS_TIMEOUT_MS, { spawnPriority: 'foreground' }),
      new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('Hermes took too long to respond. Try again when the backend is ready.')), SETTINGS_TIMEOUT_MS) })
    ])
  } finally {
    clearTimeout(timer)
  }
}

function loadSettings(route) {
  const key = JSON.stringify([route.connectionId, route.profile, route.targetProfile])
  if (!pendingLoads.has(key)) {
    const request = settingsRequest(route, { action: 'list' }).finally(() => {
      if (pendingLoads.get(key) === request) pendingLoads.delete(key)
    })
    pendingLoads.set(key, request)
  }
  return pendingLoads.get(key)
}

function textValue(field) {
  if (field.type === 'enum') return String(field.value ?? field.default ?? field.choices?.[0] ?? '')
  return field.type === 'boolean' ? String((field.value ?? field.default) === true) : String(field.value ?? '')
}

export function changedValues(fields, draft) {
  const values = {}
  for (const field of fields) {
    const raw = draft[field.key] ?? ''
    if (raw === textValue(field)) continue
    if (field.type === 'boolean') values[field.key] = raw === 'true'
    else if (field.type === 'number') {
      if (raw.trim() === '' || !Number.isFinite(Number(raw))) throw new Error(`${field.label}: enter a number.`)
      values[field.key] = Number(raw)
    } else {
      if (field.type === 'enum' && !field.choices?.includes(raw)) throw new Error(`${field.label}: select one of the available values.`)
      values[field.key] = raw
    }
  }
  return values
}

function Setting({ field, draft, setDraft, disabled, prefix }) {
  const id = `${prefix}-${field.key}`
  const props = {
    id, disabled, 'aria-describedby': `${id}-hint`,
    value: draft[field.key] ?? '',
    onChange: event => {
      const value = event.currentTarget.value
      setDraft(current => ({ ...current, [field.key]: value }))
    }
  }
  let control
  if (field.key === 'exceptions') {
    control = h(Textarea, { ...props, rows: 5, placeholder: EXCEPTIONS_EXAMPLE,
      style: { width: '100%', boxSizing: 'border-box', resize: 'vertical', lineHeight: '20px', minHeight: 114 }, spellCheck: false })
  } else if (field.type === 'boolean') {
    control = h(Switch, { id, disabled, 'aria-describedby': `${id}-hint`, 'aria-label': field.label,
      checked: props.value === 'true', onCheckedChange: checked => setDraft(current => ({ ...current, [field.key]: String(checked) })) })
  } else if (field.type === 'enum') {
    control = h(Select, { disabled, value: props.value, onValueChange: value => setDraft(current => ({ ...current, [field.key]: value })) },
      h(SelectTrigger, { id, 'aria-describedby': `${id}-hint`, 'aria-label': field.label }, h(SelectValue)),
      h(SelectContent, null, ...(field.choices ?? []).map(value => h(SelectItem, { key: value, value }, CHOICE_LABELS[value] ?? value))))
  } else {
    control = h(Input, { ...props, type: field.type === 'number' ? 'number' : 'text' })
  }
  return h('div', { style: { display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 } },
    h('label', { htmlFor: id, style: { fontSize: 12, fontWeight: 500 } }, field.label), control,
    h('p', { id: `${id}-hint`, style: hint }, field.description))
}

function SettingsBody({ ctx, route }) {
  const [fields, setFields] = useState(null)
  const [draft, setDraft] = useState({})
  const [pluginKey, setPluginKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const alive = useRef(true)
  const request = params => settingsRequest(route, params)
  const adopt = row => {
    if (!row?.key || !row.settings_schema?.length) throw new Error('Voice Gate is not available in this profile. Enable it in Capabilities, then reopen this page.')
    setPluginKey(row.key)
    setFields(row.settings_schema)
    setDraft(Object.fromEntries(row.settings_schema.map(field => [field.key, textValue(field)])))
  }
  useEffect(() => {
    alive.current = true
    let current = true
    setError('')
    loadSettings(route).then(result => {
      if (current) adopt((result.plugins ?? []).find(row => row.key === 'voice-gate' || row.name === 'Voice Gate'))
    }).catch(error => { if (current) setError(String(error.message ?? error)) })
    return () => { current = false; alive.current = false }
  }, [route, loadAttempt])

  const save = async event => {
    event.preventDefault()
    setError('')
    setSaved(false)
    try {
      const values = changedValues(fields, draft)
      setBusy(true)
      const result = await request({ action: 'settings', key: pluginKey, values })
      if (!alive.current) return
      if (!result.ok) throw new Error('Changes were not saved. Your edits are still here; try saving again.')
      if (result.plugin) adopt(result.plugin)
      else setFields(current => current.map(field => Object.hasOwn(values, field.key) ? { ...field, value: values[field.key] } : field))
      setSaved(true)
    } catch (error) {
      if (alive.current) setError(String(error.message ?? error))
    } finally {
      if (alive.current) setBusy(false)
    }
  }
  if (!fields) return h('div', { style: { display: 'grid', justifyItems: 'start', gap: 12 } },
    error ? h('p', { role: 'alert', style: hint }, `Could not load Voice Gate settings. ${error}`)
      : h('p', { role: 'status', style: hint }, 'Loading Voice Gate settings… Hermes may take a minute to read installed plugins.'),
    error ? h(Button, { type: 'button', variant: 'outline', size: 'sm', onClick: () => setLoadAttempt(value => value + 1) }, 'Try again') : null)
  const props = { draft, setDraft: update => { setSaved(false); setDraft(update) }, disabled: busy, prefix: `voice-gate-${route.profile}` }
  const controls = items => items.map(field => h(Setting, { ...props, key: field.key, field }))
  const section = (title, items, intro) => items.length ? h('section', { 'aria-label': title, style: { display: 'grid', gap: 12 } },
    h('h3', { style: { margin: 0, fontSize: 13, fontWeight: 500 } }, title), intro,
    h('div', { style: grid }, ...controls(items))) : null
  const disclosure = (title, ...children) => h('details', { style: { borderTop: '1px solid var(--ui-border)', paddingTop: 16 } },
    h('summary', { style: { cursor: 'pointer', fontSize: 13, fontWeight: 500 } }, title),
    h('div', { style: { display: 'grid', gap: 20, paddingTop: 16 } }, ...children))
  const dirty = fields.some(field => (draft[field.key] ?? '') !== textValue(field))
  const checks = fields.filter(field => field.key.startsWith('tell_'))
  const inGroup = names => checks.filter(field => names.has(field.key.slice(5)))
  return h('form', { onSubmit: save, style: { display: 'grid', gap: 24, width: '100%' } },
    h('p', { style: hint }, `Settings for ${route.profile === 'default' ? 'Hermes' : route.profile}.`),
    section('When to review', fields.filter(field => !/^(apply_|tell_|vale_)/.test(field.key) && field.key !== 'exceptions')),
    disclosure('Vale checks', section('Vale checks', fields.filter(field => field.key.startsWith('vale_')),
      h('p', { style: hint },
        h('span', { style: { display: 'block' } }, 'Vale checks your writing against a set of style rules, entirely on your computer.'),
        h('span', { style: { display: 'block' } }, 'To install it, follow the ',
          h('a', { href: VALE_URL, style: { color: 'var(--ui-accent)', textDecoration: 'underline' }, onClick: event => {
            event.preventDefault()
            void ctx.os.openExternal(VALE_URL).then(ok => { if (!ok && alive.current) setError(`Open ${VALE_URL} in your browser for installation instructions.`) })
          } }, 'Vale installation guide on GitHub'), '. Leave the executable path blank to use an installed copy.')))),
    h('section', { 'aria-label': 'Exceptions', style: { display: 'grid', gap: 8, width: '100%' } },
      ...controls(fields.filter(field => field.key === 'exceptions'))),
    disclosure('Bots', section('Bots', fields.filter(field => field.key.startsWith('apply_')))),
    disclosure('Advanced rules',
      h('p', { style: hint }, 'The built-in checks are on by default. Open a group to adjust individual rules. A match may be deliberate; read the passage before changing it.'),
      disclosure('Words and claims', section('Words and claims', inGroup(WORDS))),
      disclosure('Sentence and paragraph patterns', section('Sentence and paragraph patterns', checks.filter(field => !WORDS.has(field.key.slice(5)) && !FORMATTING.has(field.key.slice(5)) && !DELIVERY.has(field.key.slice(5))))),
      disclosure('Formatting', section('Formatting', inGroup(FORMATTING))),
      disclosure('Leftover draft and assistant text', section('Leftover draft and assistant text', inGroup(DELIVERY)))),
    error ? h('p', { role: 'alert', style: { ...hint, color: 'var(--ui-red)' } }, error) : null,
    h('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 } },
      saved ? h('span', { role: 'status', style: hint }, 'Changes saved.') : null,
      h(Button, { type: 'submit', size: 'sm', variant: 'outline', disabled: busy || !dirty }, busy ? 'Saving changes…' : 'Save changes')))
}

function SettingsPage({ ctx }) {
  const profile = useValue(host.state.profile) || 'default'
  const connectionId = useValue(host.state.connectionId)
  const route = useMemo(() => ({ profile, targetProfile: profile, connectionId }), [profile, connectionId])
  if (!connectionId) return h('p', { role: 'status', style: hint }, 'Connect Hermes to load Voice Gate settings.')
  return h(SettingsBody, { key: `${connectionId}:${profile}`, ctx, route })
}

export default {
  id: 'voice-gate', name: 'Voice Gate', description: 'Writing rules, Vale checks, and file exceptions.',
  register(ctx) {
    if (typeof ctx.registerSettingsPage !== 'function' || !host?.requestProfile || !host.state?.profile || !host.state?.connectionId || ![Button, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Switch, Textarea, useValue].every(Boolean)) return
    ctx.registerSettingsPage({ id: 'settings', title: 'Voice Gate', icon: 'edit', render: () => h(SettingsPage, { ctx }) })
  }
}
