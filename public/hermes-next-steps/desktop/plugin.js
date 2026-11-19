// hermes-next-steps: clickable next-step question chips inside the transcript.
// The agent ends a reply with a paragraph alone on its own line:
//   ::nextsteps{q1="..." q2="..." q3="..."}
// Each qN renders as a chip; click sends it as the next user turn.
// Add multi="1" to let several chips be picked and sent as one turn:
//   ::nextsteps{multi="1" q1="..." q2="..." q3="..."}
// Add rec="1,3" (1-based q numbers) to mark the options a ranker put first:
// those chips carry a Recommended tag and start out picked.
import { TRANSCRIPT_DIRECTIVE_AREA, Checkbox, Input, host } from '@hermes/plugin-sdk'
import { useState, useEffect } from 'react'
import { jsx } from 'react/jsx-runtime'

/* Per-session chip state: which chip was chosen, and whether the agent is still
   answering that session (the running flag clears on message.complete). Backed by
   ctx.storage so choices survive window reloads.
   `chosen` is the single-select index (null when nothing was sent); `picked` is
   the multi-select list of indexes; `sent` records that a block's picks were
   submitted as one turn. */
const groups = new Map()
const GROUP_PRUNE_THRESHOLD = 64
function pruneGroups() {
  if (groups.size <= GROUP_PRUNE_THRESHOLD) return
  groups.forEach(function (g, key) {
    if (!g.running && (!g.listeners || g.listeners.size === 0)) groups.delete(key)
  })
}

let storage = null /* bound in register */
/* Only the most recent choice may report the running state; every older block keeps its
   ✓ but rests. */
let activeKey = null

function setActive(key) {
  activeKey = key
  groups.forEach(function (g, k) {
    if (k !== key && g.running) g.running = false
  })
}

function persistChoice(key, g) {
  if (!storage) return
  try {
    const all = storage.get('choices', {}) || {}
    all[key] = { chosen: g.chosen, picked: g.picked, texts: g.texts, sent: g.sent, touched: g.touched }
    storage.set('choices', all)
  } catch (e) {
    /* persistence is best-effort */
  }
}

function hydrate() {
  if (!storage) return
  try {
    const all = storage.get('choices', null)
    if (all && typeof all === 'object') {
      Object.keys(all).forEach(function (key) {
        const v = all[key]
        if (v && typeof v === 'object') {
          const g = group(key)
          /* A stored entry means this block has been used (or was seeded), so the
             recommended defaults must never run over it again. */
          g.touched = true
          if (v.chosen != null) g.chosen = v.chosen
          if (Array.isArray(v.picked)) {
            g.picked = v.picked.filter(function (n) {
              return typeof n === 'number' && n >= 0
            })
          }
          /* Stored text is untrusted: cap both the array and each string. */
          if (Array.isArray(v.texts)) {
            g.texts = v.texts.slice(0, 64).map(function (t) {
              return typeof t === 'string' ? normalizeAnswer(t) : ''
            })
          }
          if (v.sent === true) g.sent = true
        }
      })
    }
  } catch (e) {
    /* start fresh on corrupt state */
  }
}

function group(key) {
  pruneGroups()
  let g = groups.get(key)
  if (!g) {
    g = { chosen: null, picked: [], texts: [], sent: false, touched: false, running: false, listeners: new Set() }
    groups.set(key, g)
  }
  return g
}

function emit(key) {
  const g = groups.get(key)
  if (g) g.listeners.forEach(function (fn) { fn() })
}

function subscribe(key, fn) {
  const g = group(key)
  g.listeners.add(fn)
  return function () {
    g.listeners.delete(fn)
  }
}

function snapshot(key) {
  const g = groups.get(key)
  return g ? g.chosen : null
}

/* Carried proposals: options an earlier reply offered and nobody answered.
   Per session in ctx.storage as
   { v: 2, next, blocks: { blockKey: n }, entries: [{ id, key, i, label, n, gone }] }
   `n` numbers the replies: every carry block takes the next number the first time
   it mounts, so "2 responses ago" is arithmetic rather than a guess, and it
   survives a reload because the numbers are stored.
   `gone` is a tombstone rather than a delete, because every block re-registers its
   own chips when it mounts and a reload would otherwise resurrect a chip the user
   dismissed. */
const CARRY_STORAGE = 'carried'
const CARRY_VERSION = 2
const CARRY_LIMIT = 30
const carryStates = new Map()
function pruneCarryStates() {
  if (carryStates.size <= 16) return
  carryStates.forEach(function (state, sid) {
    const ls = carryListeners.get(sid)
    if (!ls || ls.size === 0) {
      carryStates.delete(sid)
      carryListeners.delete(sid)
    }
  })
}
const carryListeners = new Map()

function carryListenersFor(sessionId) {
  let set = carryListeners.get(sessionId)
  if (!set) {
    set = new Set()
    carryListeners.set(sessionId, set)
  }
  return set
}

function subscribeCarry(sessionId, fn) {
  const set = carryListenersFor(sessionId)
  set.add(fn)
  return function () {
    set.delete(fn)
  }
}

function emitCarry(sessionId) {
  carryListenersFor(sessionId).forEach(function (fn) {
    fn()
  })
}

function emptyCarryState() {
  return { v: CARRY_VERSION, next: 1, blocks: {}, entries: [] }
}

/* Cap the log so a long session cannot grow storage without bound.

   Order of sacrifice, and it is not first-in-first-out: tombstones go first, then the
   oldest proposal nobody recommended, and only when the queue is nothing but
   recommendations does an old recommendation go. What survives is therefore the newest
   work plus everything the classifier thought worth doing, because a suggestion about to
   be answered is worth more than one the user scrolled past four replies ago. The reply
   numbers stay in `blocks`, so a trimmed reply still counts in "responses ago". */
function trimCarry(state) {
  if (state.entries.length <= CARRY_LIMIT) return state
  const out = state.entries.slice()
  while (out.length > CARRY_LIMIT) {
    let idx = -1
    for (let i = 0; i < out.length; i += 1) {
      if (out[i].gone) {
        idx = i
        break
      }
    }
    if (idx === -1) {
      /* Entries are appended in time order, so the first one in the lowest tier is the
         oldest of that tier. A proposal stored before the flag existed is unknown, not
         unmarked: it is kept ahead of one the classifier cleared, because an upgrade must
         not retire something that may have been recommended. */
      idx = out.findIndex(function (e) {
        return e.rec === false
      })
      if (idx === -1) {
        idx = out.findIndex(function (e) {
          return e.rec == null
        })
      }
    }
    out.splice(idx === -1 ? 0 : idx, 1)
  }
  state.entries = out
  return state
}


/* 1.0.4 stored a bare array with no reply numbers. Give each block the number of
   the first entry that came from it, in log order, so an upgrade keeps its queue
   and starts counting from there. */
function migrateCarry(raw) {
  const state = emptyCarryState()
  if (Array.isArray(raw)) {
    raw.forEach(function (entry) {
      if (!entry || typeof entry.id !== 'string' || typeof entry.label !== 'string') return
      let n = state.blocks[entry.key]
      if (n == null) {
        n = state.next
        state.next += 1
        state.blocks[entry.key] = n
      }
      state.entries.push({
        id: entry.id,
        key: entry.key,
        i: entry.i,
        label: entry.label,
        n: n,
        gone: entry.gone === true,
      })
    })
    return trimCarry(state)
  }
  if (raw && typeof raw === 'object') {
    if (raw.blocks && typeof raw.blocks === 'object') state.blocks = Object.assign({}, raw.blocks)
    if (typeof raw.next === 'number' && raw.next > 0) state.next = raw.next
    if (Array.isArray(raw.entries)) {
      state.entries = raw.entries.filter(function (e) {
        return e && typeof e.id === 'string' && typeof e.label === 'string'
      })
    }
    return state
  }
  return state
}

/* 1.0.7 and earlier wrote every chat without a session id into one bucket named
   'current'. That name can no longer be produced, so drop it once rather than
   leave another chat's proposals waiting to be shown. */
function dropSharedBucket() {
  if (!storage) return
  try {
    const all = storage.get(CARRY_STORAGE, null)
    if (all && typeof all === 'object' && all.current) {
      delete all.current
      storage.set(CARRY_STORAGE, all)
    }
  } catch (e) {
    /* best-effort */
  }
}

function carryState(sessionId) {
  pruneCarryStates()
  if (carryStates.has(sessionId)) return carryStates.get(sessionId)
  let state = emptyCarryState()
  if (storage) {
    try {
      const all = storage.get(CARRY_STORAGE, null)
      const raw = all && typeof all === 'object' ? all[sessionId] : null
      state = migrateCarry(raw)
    } catch (e) {
      state = emptyCarryState()
    }
  }
  carryStates.set(sessionId, state)
  return state
}

function persistCarry(sessionId, state) {
  carryStates.set(sessionId, state)
  if (storage) {
    try {
      const all = storage.get(CARRY_STORAGE, {}) || {}
      all[sessionId] = state
      storage.set(CARRY_STORAGE, all)
    } catch (e) {
      /* persistence is best-effort */
    }
  }
  emitCarry(sessionId)
}

/* This block's reply number: assigned on first sight, kept on every later mount,
   so the same reply keeps the same number across reloads. */
function carrySequence(sessionId, blockKey) {
  const state = carryState(sessionId)
  let n = state.blocks[blockKey]
  if (n == null) {
    n = state.next
    state.next += 1
    state.blocks[blockKey] = n
    persistCarry(sessionId, state)
  }
  return n
}

function registerProposals(sessionId, blockKey, labels, n, recommended) {
  const state = carryState(sessionId)
  const entries = state.entries.slice()
  let changed = false
  const marked = Array.isArray(recommended) ? recommended : []
  /* A block that renders again brings its verdict with it, which is how an entry stored
     before 1.0.14 gets its flag back: the directive is still in the transcript, so the
     answer is recoverable rather than guessed. */
  entries.forEach(function (e) {
    if (e.key !== blockKey || e.rec === true) return
    if (marked.indexOf(e.i) !== -1) {
      e.rec = true
      changed = true
    } else if (e.rec == null) {
      e.rec = false
      changed = true
    }
  })
  labels.forEach(function (label, i) {
    const id = blockKey + '#' + i
    const seen = entries.some(function (e) {
      return e.id === id
    })
    if (!seen) {
      entries.push({
        id: id,
        key: blockKey,
        i: i,
        label: label,
        n: n,
        gone: false,
        rec: marked.indexOf(i) !== -1,
      })
      changed = true
    }
  })
  if (changed) {
    state.entries = entries
    persistCarry(sessionId, trimCarry(state))
  }
}

/* An answered block is not a proposal any more: the next reply must not list it. */
function retireBlock(sessionId, blockKey) {
  const state = carryState(sessionId)
  let changed = false
  state.entries = state.entries.map(function (e) {
    if (e.key === blockKey && !e.gone) {
      changed = true
      return Object.assign({}, e, { gone: true })
    }
    return e
  })
  if (changed) persistCarry(sessionId, state)
}

function retireEntry(sessionId, id) {
  const state = carryState(sessionId)
  let changed = false
  state.entries = state.entries.map(function (e) {
    if (e.id === id && !e.gone) {
      changed = true
      return Object.assign({}, e, { gone: true })
    }
    return e
  })
  if (changed) persistCarry(sessionId, state)
}

/* Clean Old Proposals: drop every proposal carried in from earlier replies, in
   one click. Entries are tombstoned rather than removed, the same way a single
   dismissal works, so a block still holding an older snapshot cannot bring them
   back. The block's own proposals keep their place in the queue: this clears what
   earlier replies left unanswered, not the options on screen. */
function clearCarried(sessionId, keepKey) {
  const state = carryState(sessionId)
  let changed = false
  state.entries = state.entries.map(function (e) {
    if (e.gone || e.key === keepKey) return e
    changed = true
    return Object.assign({}, e, { gone: true })
  })
  if (changed) persistCarry(sessionId, state)
  return changed
}

/* What this block draws as carried: everything still unanswered that it did not
   offer itself, oldest first, each with the number of the reply that offered it. */
function staleFor(sessionId, blockKey) {
  const state = carryState(sessionId)
  /* The youngest reply's proposals sit on top and the oldest sink to the bottom, so the
     row reads as a queue that empties downward as you work. Chips from the same reply keep
     the order they were offered in. */
  return state.entries
    .filter(function (e) {
      return !e.gone && e.key !== blockKey
    })
    .sort(function (a, b) {
      return (b.n || 0) - (a.n || 0) || (a.i || 0) - (b.i || 0)
    })
}

function pickedOf(key) {
  const g = groups.get(key)
  return g ? g.picked : []
}

function answersOf(key) {
  const g = groups.get(key)
  return g ? g.texts : []
}

function sentOf(key) {
  const g = groups.get(key)
  return g ? g.sent : false
}

function running(key) {
  const g = groups.get(key)
  return g ? g.running : false
}

/* Tri-state: true = pick several, false = one click sends, null = the caller decides.
   `multi="0"` (or false/no/off) opts a block out of picking. */
function isMulti(value) {
  if (value === true) return true
  if (value === false) return false
  if (value == null) return null
  const text = String(value).trim()
  if (/^(0|false|no|off)$/i.test(text)) return false
  if (/^(1|true|yes|on)$/i.test(text)) return true
  return null
}

/* `carry="1"` (stamped by the agent half when Carry Over Old Proposals is on)
   makes the block also draw earlier replies' unanswered chips, marked Stale. */
/* Every boolean the agent half stamps: carry="1", steer="1", accent="0". */
function isOn(value) {
  if (value === true) return true
  if (value == null) return false
  return /^(1|true|yes|on)$/i.test(String(value).trim())
}

/* accent="0" drops the recommended tint. Absent means on: the agent half only
   stamps the attribute when the owner turned the setting off, because renderer
   code cannot read plugin settings. */
function accentOn(value) {
  if (value == null) return true
  if (value === false) return false
  return !/^(0|false|no|off)$/i.test(String(value).trim())
}

/* answer=true: the block is a small form, one row per question. The text is
   capped so a stored value or a pasted paragraph cannot turn a row into a page. */
const ANSWER_MAX_CHARS = 600

function normalizeAnswer(value) {
  const flat = String(value == null ? '' : value).replace(/\s+/g, ' ').trim()
  return flat.length > ANSWER_MAX_CHARS ? flat.slice(0, ANSWER_MAX_CHARS) : flat
}

/* "1. <question>: <answer>", one line per checked row. A checked row with no text
   still sends its number and question, the way upstream's answer mode does. */
function composeAnswers(qs, picked, texts) {
  const lines = []
  for (let i = 0; i < qs.length; i += 1) {
    if (picked.indexOf(i) === -1) continue
    const answer = texts[i] || ''
    lines.push((i + 1) + '. ' + qs[i] + (answer ? ': ' + answer : ''))
  }
  return lines.join('\n')
}

/* rec="1,3" → [0, 2]. 1-based so it lines up with the qN an agent writes; junk,
   zero and out-of-range numbers are dropped instead of trusted. */
/* alt="1,3|2,4": groups of 1-based chip numbers that exclude each other. The model
   decides the pairs; the agent half adds the one rule a model often misses (an option
   meaning "leave it as is" is opposed to every action). Groups come back 0-based,
   matching the chip indexes the rest of this file uses. */
function parseAlt(value, count) {
  if (value == null) return []
  const raw = typeof value === 'string' ? value.split('|') : value
  if (!Array.isArray(raw)) return []
  const groups = []
  raw.forEach(function (item) {
    const members = typeof item === 'string' ? item.split(',') : item
    if (!Array.isArray(members)) return
    const kept = []
    members.forEach(function (member) {
      const n = parseInt(String(member).trim(), 10)
      if (!isNaN(n) && n >= 1 && n <= count && kept.indexOf(n - 1) === -1) kept.push(n - 1)
    })
    kept.sort(function (a, b) {
      return a - b
    })
    if (kept.length < 2) return
    const same = groups.some(function (g) {
      return g.length === kept.length && g.every(function (n, i) { return n === kept[i] })
    })
    if (!same) groups.push(kept)
  })
  return groups
}

/* The chips this one cannot be sent with: every other member of every group it is in. */
function alternatesOf(groups, idx) {
  const out = []
  groups.forEach(function (group) {
    if (group.indexOf(idx) === -1) return
    group.forEach(function (n) {
      if (n !== idx && out.indexOf(n) === -1) out.push(n)
    })
  })
  return out
}

function parseRec(value, count) {
  if (value == null) return []
  const raw = Array.isArray(value) ? value : String(value).split(/[\s,;]+/)
  const out = []
  raw.forEach(function (item) {
    if (!/^\d+$/.test(String(item).trim())) return
    const idx = parseInt(String(item).trim(), 10) - 1
    if (idx >= 0 && idx < count && out.indexOf(idx) === -1) out.push(idx)
  })
  return out.sort(function (a, b) {
    return a - b
  })
}

/* The risk pill reads as a caution, not a suggestion: amber, never the accent, so a
   step that could break something cannot be mistaken for a recommended one. */
const RISK_TONE = 'var(--ui-warning, #b45309)'

/* The second line: dimmer than the label, a shade smaller, and hard-clamped at two
   wrapped lines so a chatty subtitle cannot turn a chip into a paragraph. */
const SUB_MARK = {
  display: '-webkit-box',
  WebkitBoxOrient: 'vertical',
  WebkitLineClamp: '2',
  overflow: 'hidden',
  marginTop: '1px',
  fontSize: '0.82em',
  lineHeight: '1.3',
  color: 'var(--ui-text-secondary, var(--muted-foreground, #666))',
  opacity: 0.72,
  whiteSpace: 'normal',
  overflowWrap: 'anywhere',
}

const REC_MARK = {
  fontSize: '0.85em',
  fontWeight: 600,
  letterSpacing: '0.03em',
  textTransform: 'uppercase',
  padding: '1px 7px',
  borderRadius: '999px',
  whiteSpace: 'nowrap',
  lineHeight: 1.35,
}

/* An unanswered option from an earlier reply. The pill sends it; the badge says
   how many replies back it was offered; the X drops it without sending anything.
   Two jobs, two separate targets, so nothing sends by accident: the X stops
   propagation, and the X is a sibling of the pill rather than a child. */
function StaleChip(props) {
  const label = props.label
  const back = props.back == null ? 1 : props.back
  const onSend = props.onSend
  const onDismiss = props.onDismiss
  const [hover, setHover] = useState(false)
  const primary = 'var(--dt-primary, var(--accent, var(--foreground)))'
  const stroke = hover ? 45 : 0
  const age = back + (back === 1 ? ' response ago' : ' responses ago')
  return jsx(
    'div',
    {
      className: 'fu-stale-row',
      style: { position: 'relative', display: 'flex', minWidth: 0 },
      children: [
        jsx(
          'div',
          {
            key: 'send',
            className: 'fu-chip fu-stale',
            role: 'button',
            tabIndex: 0,
            title: label,
            'aria-label': 'Send carried proposal: ' + label,
            onClick: function () {
              onSend()
            },
            onKeyDown: function (event) {
              const key = event && (event.key || event.code)
              if (key === 'Enter' || key === ' ' || key === 'Space') {
                if (event.preventDefault) event.preventDefault()
                onSend()
              }
            },
            onMouseEnter: function () {
              setHover(true)
            },
            onMouseLeave: function () {
              setHover(false)
            },
            style: {
              cursor: 'pointer',
              flex: '1 1 auto',
              width: '100%',
              minWidth: 0,
              display: 'inline-flex',
              alignItems: 'center',
              gap: '8px',
              boxSizing: 'border-box',
              border: stroke
                ? '1px dashed color-mix(in srgb, ' + primary + ' ' + stroke + '%, transparent)'
                : '1px dashed color-mix(in srgb, var(--ui-stroke-secondary, var(--border)) 85%, transparent)',
              borderRadius: '12px',
              background: 'transparent',
              color: 'var(--ui-text-secondary, var(--foreground))',
              /* Right padding holds the age badge and the X overlay, so neither
                 takes width from the pill and every pill stays one width. */
              padding: '5px 38px 5px 12px',
              fontSize: '0.9em',
              textAlign: 'left',
              maxWidth: '100%',
              lineHeight: 1.35,
              transition: 'border-color 160ms ease, color 160ms ease',
            },
            children: [
              jsx('span', {
                key: 'label',
                style: { display: 'inline-flex', alignItems: 'baseline', minWidth: 0 },
                children: [
                  /* Same reserved tick slot as a live pill, so a carried row lines
                     up with the fresh chips above it instead of starting further left. */
                  jsx('span', {
                    key: 'tick',
                    'aria-hidden': 'true',
                    style: { visibility: 'hidden' },
                    children: '✓ ',
                  }),
                  jsx('span', { key: 'q', children: label }),
                ],
              }),
              jsx(
                'span',
                {
                  key: 'age',
                  className: 'fu-age',
                  title: 'Offered ' + age + '.',
                  style: {
                    marginLeft: 'auto',
                    flex: '0 0 auto',
                    fontSize: '0.68em',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    padding: '1px 5px',
                    borderRadius: '999px',
                    border: '1px solid color-mix(in srgb, var(--ui-stroke-secondary, var(--border)) 80%, transparent)',
                    background: 'transparent',
                    color: 'var(--ui-text-secondary, var(--foreground))',
                    whiteSpace: 'nowrap',
                    lineHeight: 1.35,
                    transition: 'color 160ms ease, border-color 160ms ease',
                  },
                  children: age,
                },
                'age'
              ),
            ],
          },
          'send'
        ),
        jsx(
          'button',
          {
            key: 'dismiss',
            type: 'button',
            className: 'fu-chip-x',
            title: 'Drop this carried proposal',
            'aria-label': 'Drop carried proposal: ' + label,
            onClick: function () {
              onDismiss()
            },
            style: {
              position: 'absolute',
              right: '9px',
              top: '50%',
              transform: 'translateY(-50%)',
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: '18px',
              height: '18px',
              cursor: 'pointer',
              border: 'none',
              borderRadius: '999px',
              background: 'transparent',
              color: 'var(--ui-text-secondary, var(--foreground))',
              fontSize: '0.85em',
              lineHeight: 1,
              padding: 0,
              transition: 'color 160ms ease, background 160ms ease',
            },
            children: '✕',
          },
          'dismiss'
        ),
      ],
    },
    'stale'
  )
}

/* The tick is always laid out, only hidden when unmarked: reserving it keeps the pill
   width still when a pick adds the glyph. The space between the glyph and the label is a
   gap on the container, not a trailing space in the glyph, so its width is the same in
   every chip and the columns of the subtitle grid stay honest. */
const TICK_GAP = '6px'

function labelParts(q, marked) {
  return [
    jsx('span', {
      key: 'tick',
      'aria-hidden': 'true',
      style: { visibility: marked ? 'visible' : 'hidden' },
      children: '✓',
    }),
    jsx('span', { key: 'q', children: q }),
  ]
}

function Chip(props) {
  const q = props.q
  const idx = props.idx
  const sessionKey = props.sessionKey
  const multi = props.multi
  const active = props.active
  const onSend = props.onSend
  const onToggle = props.onToggle
  const chosen = useGroupState(sessionKey)
  const picked = usePickedState(sessionKey)
  const isChosen = !multi && chosen === idx
  const isPicked = multi && picked.indexOf(idx) !== -1
  const isRunning = isChosen && runningState(sessionKey)
  const [hover, setHover] = useState(false)
  const primary = 'var(--dt-primary, var(--accent, var(--foreground)))'
  const marked = isChosen || isPicked
  /* A recommended option keeps the accent even when it is not picked, so the
     suggested steps read as one group. accent="0" (from the plugin setting) drops
     that tint and leaves the Recommended tag alone. */
  const accented = props.accent !== false && props.recommended === true
  /* In multi-select nothing is sent on a chip, so an unanswered block keeps
     every chip at full strength; single-select dims the ones you passed over. */
  const dimmed = multi
    ? !active || props.excluded === true
    : chosen != null && !isChosen
  const className =
    'fu-chip' + (marked ? ' fu-chosen' : '') + (isRunning ? ' fu-running' : '') + (accented ? ' fu-recommended' : '')
  /* Three tints, strongest last: hover hints, a recommendation is accented, a
     pick is the loudest. One scale so the three states never fight. */
  const stroke = marked ? 75 : accented ? 70 : hover ? 55 : 0
  const tint = marked ? 14 : accented ? 11 : hover ? 7 : 0
  return jsx(
    'button',
    {
      type: 'button',
      className: className,
      'aria-pressed': multi ? isPicked : undefined,
      onClick: function () {
        if (multi) onToggle(idx)
        else onSend(q, idx)
      },
      onMouseEnter: function () {
        setHover(true)
      },
      onMouseLeave: function () {
        setHover(false)
      },
      title: props.subtitle ? q + '\n' + props.subtitle : q,
      style: {
        cursor: 'pointer',
        display: 'inline-flex',
        alignItems: props.subtitle ? 'flex-start' : 'center',
        gap: '8px',
        boxSizing: 'border-box',
        border: stroke
          ? '1px solid color-mix(in srgb, ' + primary + ' ' + stroke + '%, transparent)'
          : '1px solid var(--ui-stroke-secondary, var(--border))',
        borderRadius: '12px',
        background: tint ? 'color-mix(in srgb, ' + primary + ' ' + tint + '%, transparent)' : 'transparent',
        color: stroke ? primary : 'var(--ui-text-secondary, var(--foreground))',
        opacity: dimmed ? 0.72 : 1,
        padding: '5px 12px',
        fontSize: '0.9em',
        textAlign: 'left',
        /* No width: the row is a one-column grid sized to its widest chip, so every
           chip stretches to that width instead of each sizing to its own text. */
        maxWidth: '100%',
        lineHeight: 1.35,
        transition: 'border-color 160ms ease, background 160ms ease, color 160ms ease, opacity 160ms ease',
      },
      children: [
        props.subtitle
          ? jsx('span', {
              key: 'label',
              /* Two columns, so the second line starts exactly where the label does: the
                 tick owns the first column and both the label and its clarification sit in
                 the second. Padding or a fixed tick width drifted, because the subtitle is
                 smaller and its em resolves against its own font size. */
              style: {
                display: 'grid',
                gridTemplateColumns: 'max-content minmax(0, 1fr)',
                alignItems: 'baseline',
                columnGap: TICK_GAP,
                minWidth: 0,
                flex: '1 1 auto',
              },
              children: labelParts(q, marked).concat([
                jsx('span', {
                  key: 'sub',
                  className: 'fu-sub',
                  style: Object.assign({}, SUB_MARK, { gridColumn: '2' }),
                  children: props.subtitle,
                }),
              ]),
            })
          : jsx('span', {
              key: 'label',
              style: { display: 'inline-flex', alignItems: 'baseline', columnGap: TICK_GAP },
              children: labelParts(q, marked),
            }),
        props.risky
          ? jsx('span', {
              key: 'risk',
              className: 'fu-risky',
              title: 'This step can damage something, break something that works, or leave a mess to clean up',
              style: Object.assign({}, REC_MARK, {
                marginLeft: '6px',
                color: RISK_TONE,
                background: 'color-mix(in srgb, ' + RISK_TONE + ' 12%, transparent)',
                border: '1px solid color-mix(in srgb, ' + RISK_TONE + ' 35%, transparent)',
              }),
              children: 'Risky',
            })
          : null,
        props.recommended
          ? jsx('span', {
              key: 'rec',
              style: Object.assign({}, REC_MARK, {
                marginLeft: 'auto',
              }, accented
                ? {
                    /* Darkened against the foreground so the small uppercase text
                       clears 4.5:1 on its own 10% fill (the raw accent measured
                       4.35:1). */
                    color: 'color-mix(in srgb, ' + primary + ' 76%, var(--foreground, #111) 24%)',
                    background: 'color-mix(in srgb, ' + primary + ' 10%, transparent)',
                  }
                : {
                    /* accent="0" means no accent anywhere on a recommendation. The tag
                       goes neutral too, otherwise turning the setting off would be
                       invisible on a pre-picked chip, where the pick tint dominates. */
                    color: 'var(--ui-text-secondary, var(--foreground))',
                    background: 'color-mix(in srgb, var(--ui-stroke-secondary, var(--border)) 55%, transparent)',
                  }),
              children: 'Recommended',
            })
          : null,
      ],
    },
    'chip' + idx
  )
}

/* The only submit path in multi-select. It holds the running flag while the agent
   answers, so the block still shows which turn is in flight. */
function Send(props) {
  const sessionKey = props.sessionKey
  const count = props.count
  const sent = props.sent
  const onSend = props.onSend
  const isRunning = sent && runningState(sessionKey)
  const [hover, setHover] = useState(false)
  const primary = 'var(--dt-primary, var(--accent, var(--foreground)))'
  const disabled = count === 0 || sent
  const live = hover && !disabled
  return jsx(
    'button',
    {
      type: 'button',
      className: 'fu-chip fu-send' + (isRunning ? ' fu-running' : ''),
      disabled: disabled,
      onClick: function () {
        if (!disabled) onSend()
      },
      onMouseEnter: function () {
        setHover(true)
      },
      onMouseLeave: function () {
        setHover(false)
      },
      title: sent ? 'Sent' : count === 0 ? 'Pick one or more' : 'Send the picked steps as one message',
      style: {
        cursor: disabled ? 'default' : 'pointer',
        /* Its own width: the row's common width belongs to the pills. */
        justifySelf: 'start',
        border: '1px solid color-mix(in srgb, ' + primary + ' ' + (disabled ? '28%' : '55%') + ', transparent)',
        borderRadius: '12px',
        background: disabled
          ? 'transparent'
          : live
            ? 'color-mix(in srgb, ' + primary + ' 16%, transparent)'
            : 'color-mix(in srgb, ' + primary + ' 9%, transparent)',
        color: disabled ? 'var(--ui-text-secondary, var(--foreground))' : primary,
        opacity: disabled ? 0.55 : 1,
        padding: '5px 14px',
        marginTop: '2px',
        fontSize: '0.9em',
        fontWeight: 500,
        lineHeight: 1.35,
        transition: 'border-color 160ms ease, background 160ms ease, color 160ms ease, opacity 160ms ease',
      },
      children: [
        sent ? '✓ Sent' : count === 0 ? 'Send' : 'Send ' + count,
      ],
    },
    'send'
  )
}

/* Re-render hook: subscribes the component to its session's chip state. */
function useGroupState(key) {
  const [, force] = useState(0)
  useEffect(
    function () {
      return subscribe(key, function () {
        force(function (n) {
          return n + 1
        })
      })
    },
    [key]
  )
  return snapshot(key)
}

function usePickedState(key) {
  useGroupState(key)
  return pickedOf(key)
}

function runningState(key) {
  return running(key)
}

/* A reply field per question, using the app's own controls: the SDKCheckbox and
   Input carry the app's focus, theme and keyboard behaviour. The send button sits
   in the input column (`gridColumn: '2'`), not out at the window edge. */
function AnswerRows(props) {
  const qs = props.qs
  const picked = props.picked
  const texts = props.texts
  const sent = props.sent
  const children = []
  qs.forEach(function (q, i) {
    children.push(
      jsx(
        Checkbox,
        {
          key: 'box' + i,
          checked: picked.indexOf(i) !== -1,
          disabled: sent,
          onCheckedChange: function () { props.onToggle(i) },
          'aria-label': 'Answer ' + (i + 1) + ': ' + q,
        },
        'box' + i
      )
    )
    children.push(
      jsx(
        Input,
        {
          key: 'field' + i,
          value: texts[i] || '',
          disabled: sent,
          placeholder: q,
          onChange: function (event) {
            props.onChange(i, event && event.target ? event.target.value : '')
          },
          'aria-label': q,
        },
        'field' + i
      )
    )
  })
  children.push(
    jsx(
      'div',
      {
        key: 'send',
        style: { gridColumn: '2' },
        children: jsx(Send, {
          sessionKey: props.sessionKey,
          count: picked.length,
          sent: sent,
          onSend: props.onSend,
        }),
      },
      'send'
    )
  )
  return jsx(
    'div',
    {
      className: 'fu-answers',
      style: {
        display: 'grid',
        gridTemplateColumns: 'auto minmax(0, 1fr)',
        gap: '8px',
        maxWidth: '520px',
        margin: '6px 0 2px 0',
      },
      children: children,
    },
    'answers'
  )
}

function Chips(props) {
  const attrs = (props && props.attrs) || {}
  const sessionId = props && props.sessionId
  /* Unique per directive block: session + the raw directive source text. Each
     nextsteps block starts blank; a chosen state never leaks into the next one. */
  const source = (props && props.source) || ''
  const groupKey = (sessionId || 'current') + '::' + source
  /* Any count: q1..qN in numeric order, no hard limit. */
  const qs = Object.keys(attrs)
    .filter(function (k) {
      return /^q\d+$/.test(k)
    })
    .sort(function (a, b) {
      return parseInt(a.slice(1), 10) - parseInt(b.slice(1), 10)
    })
    .map(function (k) {
      return attrs[k]
    })
    .filter(function (q) {
      return typeof q === 'string' && q.length > 0
    })
  /* answer="1" (also the upstream spelling kind="answer") draws a reply field
     per option. It replaces pickable chips: a form and a chip row sharing one
     footer would send two different shapes of turn from the same block. */
  const answerOn = isOn(attrs.answer) || attrs.kind === 'answer'
  /* Two or more chips are pickable unless the directive says otherwise. A block
     that defaulted to one-click-sends made picking two next steps send two turns
     and queue them; multi="0" is the opt-out for genuinely exclusive options. */
  const multi = !answerOn && isMulti(attrs.multi) !== false && qs.length > 1
  /* carry="1", stamped by the agent half when Carry Over Old Proposals is on:
     the next reply buries the earlier chips, so this block also draws every
     proposal still unanswered from the replies above it. */
  /* The session this block belongs to, and never a shared one. `sid` is stamped
     into the directive by the agent half, which knows the chat id for certain;
     the render prop is the fallback. Without either, carrying is switched off for
     this block: a missing key used to mean one bucket called 'current', and every
     chat wrote its proposals into it, so a chip offered in one chat showed up in
     another. No queue is better than someone else's queue. */
  const carrySession =
    (typeof attrs.sid === 'string' && attrs.sid ? attrs.sid : '') ||
    (typeof sessionId === 'string' && sessionId ? sessionId : '')
  const carryOn = isOn(attrs.carry) && carrySession !== '' && !answerOn
  /* steer="1": the setting asks for a chip's text to reach the live turn instead
     of queueing behind it. */
  const steerOn = isOn(attrs.steer)
  /* This reply's number in the session, so a carried chip can say how many
     replies ago it was offered. */
  const ourN = carryOn ? carrySequence(carrySession, groupKey) : 0
  const [, bumpCarry] = useState(0)
  useEffect(
    function () {
      if (!carryOn) return undefined
      return subscribeCarry(carrySession, function () {
        bumpCarry(function (n) {
          return n + 1
        })
      })
    },
    [carryOn, carrySession]
  )
  const rec = parseRec(attrs.rec, qs.length)
  /* Alternate groups: picking one member clears the others, so a decision with
     two routes in it can never be sent as both. */
  const alt = parseAlt(attrs.alt, qs.length)
  /* d1="…", d3="…": a dim second line under a label whose verb hides what it touches.
     Absent for the options that need no explanation, which is most of them. */
function parseSubtitles(attrs, count) {
  const out = new Array(count)
  for (let i = 0; i < count; i += 1) {
    const raw = attrs['d' + (i + 1)]
    out[i] = typeof raw === 'string' ? normalizeSubtitle(raw) : ''
  }
  return out
}

/* One line of plain text: newlines and runs of spaces collapse, so a model that wraps
   its own prose cannot give the chip an accidental third line. */
function normalizeSubtitle(text) {
  const flat = String(text || '').replace(/\s+/g, ' ').trim()
  return flat.length > 160 ? flat.slice(0, 160).replace(/\s+\S*$/, '') + '…' : flat
}
  const risky = parseRec(attrs.risky, qs.length)
  const subs = parseSubtitles(attrs, qs.length)

  const qsKey = qs.join('\n')
  /* Register what this reply proposes, once, so later replies can carry it. */
  useEffect(
    function () {
      if (carryOn && qs.length > 0) registerProposals(carrySession, groupKey, qs, ourN, rec)
    },
    [carryOn, carrySession, groupKey, qsKey, ourN]
  )

  const accent = accentOn(attrs.accent)
  /* Recommended options start picked, exactly once. A stored entry or any later
     tick counts as touched, so a user who unticks them is never overruled by the
     defaults coming back on the next render. */
  const g = group(groupKey)
  if (multi && rec.length && !g.touched && !g.sent) {
    g.picked = rec.slice()
    g.touched = true
    persistChoice(groupKey, g)
  }

  const picked = usePickedState(groupKey)
  const stale = carryOn ? staleFor(carrySession, groupKey) : []
  /* A reply that proposes nothing still has a block when carry is on, because
     that is the only slot the stale chips can draw in. Nothing at all means no
     chips and nothing to carry, and then no block is drawn. */
  if (qs.length === 0 && stale.length === 0) return null
  const sent = sentOf(groupKey)
  const texts = answerOn ? answersOf(groupKey) : []
  const active = multi ? !sent : snapshot(groupKey) == null

  /* Send the text the way the moment calls for.

     On an idle chat, submit starts a turn. While the chat is working, submit is
     NOT the queue: it follows the composer's busy route, which steers or
     interrupts the running turn, and a chip that silently changes the answer in
     progress, or lands as a request with no turn behind it, is worse than a late
     one. So a busy chat gets a real admission into the durable gateway FIFO
     (`prompt.submit`, which always admits with mode `queue`): the click becomes
     the next turn and runs when the current one ends.

     With steer="1" the live turn is asked first (`session.steer`, the same call
     the composer's steer makes). Its wire contract reads `rejected` as "not
     corrected, queue it as the next prompt", and every other refusal or error
     means the same thing, so the queue admission is the floor: a click is never
     left as text that triggers nothing. */
  function deliver(text, done) {
    var submit = host && host.composer && host.composer.submit
    function ordinary() {
      var ok = typeof submit === 'function' ? submit(sessionId != null ? sessionId : null, text) : false
      if (ok) done()
      else if (host && host.notify) host.notify({ kind: 'warning', message: 'Open that chat to continue' })
    }
    var request = host && host.request
    var sid = sessionId != null && sessionId !== '' ? sessionId : null
    if (sid === null) {
      ordinary()
      return
    }
    var busy = false
    try {
      var busyAtom = host && host.state && host.state.busyBySession
      busy = Boolean(busyAtom && typeof busyAtom.get === 'function' && busyAtom.get()[sid])
    } catch (e) {
      busy = false
    }
    if (!busy) {
      ordinary()
      return
    }
    var settled = false
    function finish(ok) {
      if (settled) return
      settled = true
      if (ok) done()
      else ordinary()
    }
    function queue() {
      if (typeof request !== 'function') {
        finish(false)
        return
      }
      var id = 'hermes-next-steps-' + Date.now().toString(36) + '-' + Math.random().toString(16).slice(2, 8)
      try {
        Promise.resolve(request('prompt.submit', { session_id: sid, text: text, submission_id: id }))
          .then(function (res) {
            var failed = res && (res.ok === false || res.status === 'error' || res.status === 'rejected')
            finish(!failed)
          })
          .catch(function () {
            finish(false)
          })
      } catch (e) {
        finish(false)
      }
    }
    if (!steerOn) {
      queue()
      return
    }
    try {
      Promise.resolve(request('session.steer', { session_id: sid, text: text }))
        .then(function (res) {
          if (res && res.status === 'queued' && res.delivered !== false) finish(true)
          else queue()
        })
        .catch(function () {
          queue()
        })
    } catch (e) {
      queue()
    }
  }

  function send(q, idx) {
    deliver(q, function () {
      const g = group(groupKey)
      g.chosen = idx
      g.running = true
      setActive(groupKey)
      persistChoice(groupKey, g)
      /* Answered: this block's options stop being carried proposals. */
      retireBlock(carrySession, groupKey)
      emit(groupKey)
      groups.forEach(function (_, k) {
        if (k !== groupKey) emit(k)
      })
    })
  }

  /* One turn carries either the picked chips or the typed answers, in q order.
     Both shapes share the delivery path, so the busy/steer rules cannot drift. */
  function sendTurn(text) {
    if (!text) return
    deliver(text, function () {
      const g = group(groupKey)
      g.sent = true
      g.running = true
      setActive(groupKey)
      persistChoice(groupKey, g)
      retireBlock(carrySession, groupKey)
      emit(groupKey)
      groups.forEach(function (_, k) {
        if (k !== groupKey) emit(k)
      })
    })
  }

  function sendPicked() {
    sendTurn(
      qs
        .filter(function (q, i) {
          return picked.indexOf(i) !== -1
        })
        .join('\n')
    )
  }

  function sendAnswers() {
    sendTurn(composeAnswers(qs, picked, texts))
  }

  function pick(idx) {
    const g = group(groupKey)
    if (g.sent || g.picked.indexOf(idx) !== -1) return
    const conflict = alternatesOf(alt, idx)
    g.picked = g.picked
      .filter(function (n) { return conflict.indexOf(n) === -1 })
      .concat([idx])
      .sort(function (a, b) { return a - b })
    persistChoice(groupKey, g)
    emit(groupKey)
  }

  function setAnswer(idx, value) {
    const g = group(groupKey)
    if (g.sent) return
    g.texts[idx] = normalizeAnswer(value)
    persistChoice(groupKey, g)
    /* Typing is already an answer to that point, so select its row; otherwise the
       user has to tick a box they just filled in. */
    if (g.texts[idx]) pick(idx)
    emit(groupKey)
  }

  function toggle(idx) {
    const g = group(groupKey)
    if (g.sent) return
    if (g.picked.indexOf(idx) === -1) {
      /* Picking is exclusive inside a group: one route, one time, one way out. */
      const conflict = alternatesOf(alt, idx)
      const kept = g.picked.filter(function (n) {
        return conflict.indexOf(n) === -1
      })
      g.picked = kept.concat([idx]).sort(function (a, b) { return a - b })
    } else {
      g.picked = g.picked.filter(function (n) { return n !== idx })
    }
    persistChoice(groupKey, g)
    emit(groupKey)
  }

  /* A stale chip sends exactly itself: it belongs to an earlier reply, so it is
     never part of this block's multi-select count. */
  function sendStale(id, label) {
    deliver(label, function () {
      retireEntry(carrySession, id)
      setActive(groupKey)
    })
  }

  function dismissStale(id) {
    retireEntry(carrySession, id)
  }

  let rows
  if (answerOn) {
    rows = [
      jsx(AnswerRows, {
        qs: qs,
        picked: picked,
        texts: texts,
        sent: sent,
        sessionKey: groupKey,
        onToggle: toggle,
        onChange: setAnswer,
        onSend: sendAnswers,
      }),
    ]
  } else {
    rows = qs.map(function (q, i) {
    return jsx(Chip, {
      key: String(i) + ':' + q,
      q: q,
      idx: i,
      multi: multi,
      active: active,
      recommended: rec.indexOf(i) !== -1,
      risky: risky.indexOf(i) !== -1,
      subtitle: subs[i] || '',
      /* Greyed because a chip it is opposed to is already picked. */
      excluded: multi && alternatesOf(alt, i).some(function (n) {
        return picked.indexOf(n) !== -1
      }),
      accent: accent,
      sessionKey: groupKey,
      onSend: send,
      onToggle: toggle,
    })
    })
  }

  /* Older replies first, in the order they were offered: the newest reply shows
     its own proposals, then everything still unanswered above it. Each carried
     chip knows how many replies back it came from. */
  stale.forEach(function (entry) {
    const back = Math.max(1, ourN - (typeof entry.n === 'number' ? entry.n : ourN - 1))
    rows.push(
      jsx(StaleChip, {
        key: 'stale:' + entry.id,
        label: entry.label,
        back: back,
        onSend: function () {
          sendStale(entry.id, entry.label)
        },
        onDismiss: function () {
          dismissStale(entry.id)
        },
      })
    )
  })

  /* The send button closes the block, after every row it would send: a carried
     chip sits between this reply's own options and the button that answers them,
     so the action never appears above entries it does not send.

     When something is carried, the same row also ends with the cleanup: it sits at
     the far right, past the send button, because it clears what earlier replies
     left behind rather than anything this block would send. */
  const footer = []
  if (multi) {
    footer.push(
      jsx(Send, {
        key: 'send',
        sessionKey: groupKey,
        count: picked.length,
        sent: sent,
        onSend: sendPicked,
      })
    )
  }
  if (stale.length > 0) {
    footer.push(
      jsx('button', {
        key: 'clean',
        type: 'button',
        className: 'fu-clean',
        /* A quiet action, not a chip: it clears rows rather than proposing one. */
        style: {
          marginLeft: 'auto',
          flexShrink: 0,
          background: 'transparent',
          border: 'none',
          padding: '2px 2px 2px 8px',
          font: 'inherit',
          fontSize: '11px',
          lineHeight: '1.5',
          color: 'var(--ui-text-secondary, var(--muted-foreground, #666))',
          cursor: 'pointer',
          textDecoration: 'underline dotted',
        },
        title: 'Remove the proposals carried in from earlier replies',
        'aria-label': 'Clean old next steps',
        onClick: function () {
          if (clearCarried(carrySession, groupKey)) emit(groupKey)
        },
        /* The arrow points at the chips it clears: they are the rows above this one. */
        children: 'Clean Old Proposals ↓',
      })
    )
  }
  if (footer.length > 0) {
    rows.push(
      jsx('div', {
        key: 'footer',
        className: 'fu-footer',
        style: { display: 'flex', alignItems: 'center', gap: '8px', minWidth: '0' },
        children: footer,
      })
    )
  }

  return jsx('div', {
    style: {
      /* One implicit column sized to the widest chip: every chip stretches to it,
         so all pills share a width and the narrowest option is not a stub. The
         single column also means a very long option is capped by the row, and its
         text wraps inside the pill rather than pushing the row wide. */
      display: 'grid',
      gridTemplateColumns: 'minmax(0, max-content)',
      gap: '6px',
      margin: '6px 0 2px 0',
    },
    children: rows,
  })
}

const plugin = {
  id: 'hermes-next-steps',
  name: 'Next Steps',
  description: 'Clickable next-step question chips after assistant replies',
  register: function register(ctx) {
    storage = (ctx && ctx.storage) || null
    hydrate()
    dropSharedBucket()
    const area =
      typeof TRANSCRIPT_DIRECTIVE_AREA === 'string' && TRANSCRIPT_DIRECTIVE_AREA
        ? TRANSCRIPT_DIRECTIVE_AREA
        : 'transcript.directives'
    if (typeof ctx.onEvent === 'function') {
      /* Settle every block of the session: keys are `<sessionId>::<source>`. */
      const settle = function (sid) {
        if (!sid) return
        const prefix = sid + '::'
        groups.forEach(function (g, key) {
          if (key.indexOf(prefix) === 0 && g.running) {
            g.running = false
            if (activeKey === key) activeKey = null
            emit(key)
          }
        })
      }
      ctx.onEvent('message.complete', settle)
      /* A fresh user/assistant exchange also settles any stuck running state. */
      ctx.onEvent('message.start', settle)
    }
    ctx.register({
      id: 'nextsteps',
      area: area,
      data: {
        name: 'nextsteps',
        render: function render(args) {
          return jsx(Chips, {
            attrs: args && args.attrs,
            sessionId: args && args.sessionId,
            source: args && args.source,
          })
        },
      },
    })
  },
}

export default plugin
