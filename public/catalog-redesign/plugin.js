/**
 * Catalog Redesign — a wide, one-row-per-item catalog for skills and plugins.
 *
 * Layout: one row per item, three real columns (name, normalized short name in
 * the flexible middle column, tags). Everything else — hero image, description,
 * key, provider, version, stars, capsule metadata — lives in two places only:
 * a cursor-following hover card after a short dwell, and the detail panel that
 * slides in from the right on click. The panel is drawn on the sidebar surface
 * and carries its own icon rail; the rail expands into a labelled overlay sheet
 * on demand.
 *
 * Personal edition. Every control here sits on a public SDK surface: the page
 * registers its own route, sidebar row and palette entry and never touches the
 * core Capabilities row.
 */
import {
  Badge,
  Button,
  Codicon,
  EmptyState,
  Loader,
  PALETTE_AREA,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  ScrollArea,
  SearchField,
  SegmentedControl,
  Switch,
  Tip,
  ToggleRow,
  host
} from '@hermes/plugin-sdk'
import { Component, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { jsx } from 'react/jsx-runtime'

const ID = 'hermes-catalog-redesign'
// MCP has no SDK or JSON-RPC door for enabling a server, so the connector
// switch exists only where the plugin may write the config itself. The public
// edition drops it and points at the native page instead.
const CAN_TOGGLE_CONNECTORS = false
const ROUTE = '/catalog'
const SETTINGS_KEY = 'settings.v1'
const CACHE_MS = 5 * 60 * 1000
const PAGE_SIZE = 150
const HOVER_DELAY = 240
const KIND_IDS = ['plugins', 'skills', 'connectors', 'tools']

// Motion: one curve per intent. Open with a long, decelerating ease-out;
// close with a shorter accelerate so dismissal never feels sticky.
const EASE_OUT = 'cubic-bezier(0.22, 1, 0.36, 1)'
const EASE_SOFT = 'cubic-bezier(0.32, 0.72, 0, 1)'
const EASE_IN = 'cubic-bezier(0.4, 0, 1, 0.55)'
const PANEL_MS = 380
const CLOSE_MS = 220

const C = {
  text: 'var(--ui-text-primary)',
  text2: 'var(--ui-text-secondary)',
  text3: 'var(--ui-text-tertiary)',
  text4: 'var(--ui-text-quaternary)',
  stroke: 'var(--ui-stroke-tertiary)',
  stroke2: 'var(--ui-stroke-secondary)',
  surface: 'var(--ui-surface-background)',
  elevated: 'var(--ui-bg-elevated)',
  chip: 'var(--ui-bg-quaternary)',
  rowHover: 'var(--ui-row-hover-background)',
  rowOpen: 'var(--ui-row-open-background)',
  accent: 'var(--ui-accent)'
}

/** A panel must read as a surface, never as glass. Theme background tokens are
 *  allowed to carry alpha (the current theme sets the sidebar surface to
 *  `transparent`), so the themed tint is painted over an opaque neutral: the
 *  panel keeps the theme's colour and never shows the list through itself. */
const SOLID = {
  backgroundColor: 'var(--theme-neutral-card, var(--ui-bg-editor, #161618))',
  backgroundImage: 'linear-gradient(var(--ui-bg-editor), var(--ui-bg-editor))'
}

const MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'

// One column template for the header and every row: `auto` here would let each
// row size its tag column on its own content, and the columns would drift row
// by row. The tag column is fixed so chips share one right edge.

/* ------------------------------------------------------------------ state */

const FEED_URL = 'https://hermes-agent.nousresearch.com/docs/api/plugins.json'

let ctxRef = null
let restUnavailable = false
let closePanel = null
let settings = { alwaysShowInstalled: false, kindOrder: KIND_IDS }

// Renderer-side cache: the page unmounts on every navigation and the catalog
// is a megabyte-scale payload, so it survives a remount instead of refetching.
const cache = {
  catalog: null,
  catalogAt: 0,
  catalogError: null,
  installed: null,
  installedAt: 0,
  installedError: null,
  skills: null,
  skillsAt: 0,
  toolsets: null,
  toolsetsAt: 0,
  servers: null,
  serversAt: 0,
  mcpCatalog: null,
  mcpCatalogAt: 0,
  catalogTotal: 0,
  skillsCatalog: null,
  skillsCatalogAt: 0,
  skillsCatalogTotal: 0,
  archived: null,
  archivedAt: 0
}

/** Read a plugin-state atom without assuming the app's store library: `get`
 *  is always there, and `listen`/`subscribe` are used only when present. The
 *  SDK's `useValue` hook reads `store.get()` eagerly, so an atom that is not
 *  mounted yet takes the whole page down with it. */
function useAtomValue(atom) {
  const read = useCallback(() => {
    try {
      return atom && typeof atom.get === 'function' ? atom.get() : undefined
    } catch {
      return undefined
    }
  }, [atom])

  const [value, setValue] = useState(read)

  useEffect(() => {
    setValue(read())

    const off = atom?.listen?.(next => setValue(next)) ?? atom?.subscribe?.(next => setValue(next))

    return typeof off === 'function' ? off : undefined
  }, [atom, read])

  return value
}

const el = (type, props, ...kids) =>
  kids.length ? jsx(type, { ...props, children: kids.length === 1 ? kids[0] : kids }) : jsx(type, props)

const str = value => (typeof value === 'string' ? value : '')

/** The normalized short name: lowercase, punctuation collapsed, a leading
 *  `hermes-`/`hermes ` dropped, then clipped. It is an identity aid, not a
 *  second title, so it never wraps and never changes width per row. */
function shortName(value, limit = 30) {
  const slug = str(value)
    .toLowerCase()
    .replace(/^hermes[-_\s]+/, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')

  return slug.length > limit ? `${slug.slice(0, limit - 1)}…` : slug
}

function hashOf(value) {
  let hash = 0
  const text = str(value)

  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) % 360
  }

  return hash
}

function initialsOf(value) {
  const parts = str(value)
    .replace(/[-_]+/g, ' ')
    .split(/\s+/)
    .filter(Boolean)

  const letters = parts.slice(0, 2).map(part => part[0].toUpperCase()).join('')

  return letters || '?'
}

function starsOf(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    return ''
  }

  return value >= 1000 ? `${(value / 1000).toFixed(value >= 10000 ? 0 : 1)}k` : String(value)
}

function dateOf(value) {
  const time = Date.parse(str(value))

  if (!Number.isFinite(time)) {
    return ''
  }

  return new Date(time).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function prefersReducedMotion() {
  try {
    return typeof window !== 'undefined' && Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches)
  } catch {
    return false
  }
}

/** `ctx.setTimeout(fn, ms)` returns a disposer, not a timer id; wrapping it
 *  keeps every call site from confusing the two. Older hosts without the
 *  scoped timer fall back to a window timer that the caller still cancels. */
function later(fn, ms) {
  const cancel = ctxRef?.setTimeout?.(fn, ms)

  if (typeof cancel === 'function') {
    return cancel
  }

  const id = typeof window === 'undefined' ? 0 : window.setTimeout(fn, ms)

  return () => {
    if (id) {
      window.clearTimeout(id)
    }
  }
}

/** No door may leave the page spinning: every REST or gateway call settles
 *  with a value or an error inside its own budget. */
function withTimeout(promise, ms, what) {
  return new Promise((resolve, reject) => {
    const cancel = later(() => reject(new Error(`${what} did not answer within ${Math.round(ms / 1000)}s`)), ms)

    Promise.resolve(promise).then(
      value => {
        cancel()
        resolve(value)
      },
      error => {
        cancel()
        reject(error)
      }
    )
  })
}

/** Run a Web Animations tween; a shell without the API just jumps to the end. */
function tween(node, frames, options) {
  if (!node || typeof node.animate !== 'function' || prefersReducedMotion()) {
    return null
  }

  return node.animate(frames, { fill: 'both', ...options })
}

/* ------------------------------------------------------------------- data */

function savedSettings() {
  try {
    const raw = ctxRef?.storage?.get?.(SETTINGS_KEY)

    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      settings = {
        alwaysShowInstalled: false,
        kindOrder: normalizeOrder(raw.kindOrder)
      }
    }
  } catch {
    // Defaults are fine; a broken store must not blank the page.
  }

  return settings
}

function persistSettings(next) {
  settings = { ...settings, ...next }

  try {
    ctxRef?.storage?.set?.(SETTINGS_KEY, settings)
  } catch {
    // The toggle still applies for this session.
  }
}

const scopeParam = profile => (profile && profile !== 'default' ? { profile } : {})

const gatewayState = () => {
  try {
    return host.state?.gateway?.get?.() ?? null
  } catch {
    return null
  }
}

/** `host.request` throws `Hermes gateway unavailable` until the desktop socket
 *  is open, which is a startup race rather than a failure. Wait for it, unless
 *  the host exposes no gateway atom at all, in which case waiting would only
 *  add twenty seconds to every call. */
async function whenGatewayOpen(limitMs = GATEWAY_WAIT_MS) {
  if (gatewayState() === null) {
    return null
  }

  const started = Date.now()

  while (gatewayState() !== 'open' && Date.now() - started < limitMs) {
    await new Promise(resolve => {
      later(resolve, 200)
    })
  }

  const waited = Date.now() - started

  if (waited > 400) {
    console.info('[catalog] waited', waited, 'ms for the gateway socket')
  }

  return gatewayState()
}

/** One door for every gateway RPC: waits for the socket, passes the call's own
 *  budget to the socket instead of inheriting the 30s default, and retries once
 *  when the socket was still opening. */
async function ask(method, params, budget = RPC_MS, label = method) {
  const call = () => host.request(method, params, budget)

  await whenGatewayOpen()

  try {
    return await withTimeout(call(), budget + 10000, `The gateway (${label})`)
  } catch (err) {
    if (!/gateway unavailable/i.test(String(err?.message || err))) {
      throw err
    }

    await whenGatewayOpen()

    return await withTimeout(call(), budget + 10000, `The gateway (${label})`)
  }
}

/** Known ids only, no duplicates, and a kind a later version adds lands at the
 *  end instead of vanishing from the header. */
function normalizeOrder(raw) {
  const order = []

  if (Array.isArray(raw)) {
    for (const id of raw) {
      if (KIND_IDS.includes(id) && !order.includes(id)) {
        order.push(id)
      }
    }
  }

  for (const id of KIND_IDS) {
    if (!order.includes(id)) {
      order.push(id)
    }
  }

  return order
}

function orderedKinds(order = settings.kindOrder) {
  const byId = new Map(KINDS.map(entry => [entry.id, entry]))

  return normalizeOrder(order)
    .map(id => byId.get(id))
    .filter(Boolean)
}

const REST_MS = 100000
const FETCH_MS = 15000
const RPC_MS = 20000
// `plugins.manage list` walks the plugins directory and reads every manifest,
// so it is slower than any other door by an order of magnitude.
const PLUGINS_MS = 150000
const GATEWAY_WAIT_MS = 20000
// A scan this expensive is worth keeping longer than the other caches.
const INSTALLED_CACHE_MS = 15 * 60 * 1000
const INSTALLED_SNAPSHOT_KEY = 'installed.v1'

async function loadCatalogPage(kind, { page = 1, size = PAGE_SIZE, query = '', force = false } = {}) {
  if (typeof ctxRef?.rest !== 'function' || restUnavailable) {
    throw new Error('The plugin catalog service is not reachable')
  }

  const params = new URLSearchParams({ page: String(page), size: String(size) })
  const needle = String(query || '').trim()

  if (needle) {
    params.set('q', needle)
  }

  if (force) {
    params.set('refresh', '1')
  }

  const payload = await withTimeout(
    ctxRef.rest(`/catalog/${kind}?${params.toString()}`),
    REST_MS,
    'The plugin catalog service'
  )

  if (!payload || !Array.isArray(payload.rows)) {
    throw new Error(`The ${kind} catalog service returned no rows`)
  }

  const rows = payload.rows

  return {
    rows,
    total: typeof payload.total === 'number' ? payload.total : rows.length,
    page: typeof payload.page === 'number' ? payload.page : page,
    totalPages: typeof payload.totalPages === 'number' ? payload.totalPages : 1,
    error: payload.error || null,
    source: payload.source || 'network'
  }
}

/** Page one of the plugin catalog: the counts and the installed rows reuse it. */
async function loadCatalogPlugins(force = false) {
  if (!force && cache.catalog && Date.now() - cache.catalogAt < CACHE_MS) {
    return cache.catalog
  }

  const result = await loadCatalogPage('plugins', { page: 1, force })

  cache.catalog = result.rows
  cache.catalogAt = Date.now()
  cache.catalogTotal = result.total
  cache.catalogError = result.error

  return cache.catalog
}

/** Page one of the skills catalog, for the header count and the warm pass. */
async function loadCatalogSkillsOnce(force = false) {
  if (!force && cache.skillsCatalog && Date.now() - cache.skillsCatalogAt < CACHE_MS) {
    return cache.skillsCatalog
  }

  const result = await loadCatalogPage('skills', { page: 1, force })

  cache.skillsCatalog = result.rows
  cache.skillsCatalogAt = Date.now()
  cache.skillsCatalogTotal = result.total

  return cache.skillsCatalog
}

/** Skills the curator moved to ``skills/.archive``: a folder read, not a hub call. */
async function loadArchivedSkills(force = false) {
  if (!force && cache.archived && Date.now() - cache.archivedAt < CACHE_MS) {
    return cache.archived
  }

  const payload = await withTimeout(
    ctxRef.rest(`/skills/archive${force ? '?refresh=1' : ''}`),
    REST_MS,
    'The plugin catalog service'
  )
  const rows = Array.isArray(payload?.rows) ? payload.rows : []

  cache.archived = rows
  cache.archivedAt = Date.now()

  return rows
}

/**
 * `plugins.manage list` walks every plugin folder to describe it, which measures
 * about 75 seconds on a large install. `plugins.list` answers from the manager
 * already in memory with name, version and enabled state, so the page paints a
 * real list at once and the detail scan refines it in the background.
 */
async function loadInstalledPluginsQuick(profile) {
  if (cache.quickInstalled && Date.now() - cache.quickAt < CACHE_MS) {
    return cache.quickInstalled
  }

  const startedAt = Date.now()
  const result = await ask('plugins.list', {}, RPC_MS, 'plugins.list')
  const rows = Array.isArray(result?.plugins) ? result.plugins : []

  if (!rows.length) {
    throw new Error('plugins.list returned no entries')
  }

  cache.quickInstalled = rows
  cache.quickAt = Date.now()
  console.info('[catalog] fast list:', rows.length, 'plugins in', Date.now() - startedAt, 'ms')

  return rows
}

async function loadInstalledPlugins(profile, force = false) {
  if (!force && cache.installed && Date.now() - cache.installedAt < INSTALLED_CACHE_MS) {
    return cache.installed
  }

  // The socket has its own 30s default; a 70s manifest walk needs its own budget
  // on the request itself, or the socket times out before the gateway answers.
  const startedAt = Date.now()
  const result = await ask('plugins.manage', { action: 'list', ...scopeParam(profile) }, PLUGINS_MS, 'plugins.manage')
  const rows = Array.isArray(result?.plugins) ? result.plugins : []
  console.info('[catalog] detail scan:', rows.length, 'plugins in', Date.now() - startedAt, 'ms')

  cache.installed = rows
  cache.installedAt = Date.now()
  cache.installedError = null

  try {
    ctxRef?.storage?.set?.(INSTALLED_SNAPSHOT_KEY, { rows, at: cache.installedAt })
  } catch {
    // A full store just means the next window waits for the scan.
  }

  return rows
}

async function loadInstalledSkills(profile, force = false) {
  if (!force && cache.skills && Date.now() - cache.skillsAt < CACHE_MS) {
    return cache.skills
  }

  const rows = await withTimeout(
    host.skills.list(profile && profile !== 'default' ? profile : undefined),
    RPC_MS,
    'The gateway (skills.list)'
  )

  cache.skills = Array.isArray(rows) ? rows : []
  cache.skillsAt = Date.now()

  return cache.skills
}

/** Toolsets: what the agent can already do, and whether each one is on. */
async function loadToolsets(profile, force = false) {
  if (!force && cache.toolsets && Date.now() - cache.toolsetsAt < CACHE_MS) {
    return cache.toolsets
  }

  const rows = await withTimeout(
    host.toolsets.list(profile && profile !== 'default' ? profile : undefined),
    RPC_MS,
    'The gateway (toolsets.list)'
  )

  cache.toolsets = Array.isArray(rows) ? rows : []
  cache.toolsetsAt = Date.now()

  return cache.toolsets
}

/** Connectors are MCP servers: the profile's configured set, or the curated presets. */
async function loadServers(profile, force = false) {
  if (!force && cache.servers && Date.now() - cache.serversAt < CACHE_MS) {
    return cache.servers
  }

  const result = await withTimeout(
    host.request('mcp.servers.list', scopeParam(profile)),
    RPC_MS,
    'The gateway (mcp.servers.list)'
  )
  const rows = Array.isArray(result?.servers) ? result.servers : []

  cache.servers = rows
  cache.serversAt = Date.now()

  return rows
}

async function loadMcpCatalog(profile, force = false) {
  if (!force && cache.mcpCatalog && Date.now() - cache.mcpCatalogAt < CACHE_MS) {
    return cache.mcpCatalog
  }

  const result = await withTimeout(
    host.request('mcp.catalog', scopeParam(profile)),
    RPC_MS,
    'The gateway (mcp.catalog)'
  )
  const rows = Array.isArray(result?.servers) ? result.servers : []

  cache.mcpCatalog = rows
  cache.mcpCatalogAt = Date.now()

  return rows
}

/* --------------------------------------------------------------- prefetch */

// One job per door: two views asking for the same data share one request.
const warming = new Map()

function warmOnce(key, job) {
  if (warming.has(key)) {
    return warming.get(key)
  }

  const promise = Promise.resolve()
    .then(job)
    .catch(() => null)

  warming.set(key, promise)
  promise.then(() => warming.delete(key))

  return promise
}

/** Load what the next switch will need, after the visible paint. The other
 *  filter of the current kind goes first, then every other kind, so no tab a
 *  person clicks has to wait for its door. */
async function warm(profile, kind, filter, onLanded) {
  const pairs = {
    plugins: ['plugins-fast', () => loadInstalledPluginsQuick(profile)],
    icons: ['plugin-icons', () => loadPluginIcons()],
    'plugins-detail': ['plugins-installed', () => loadInstalledPlugins(profile)],
    catalog: ['catalog-plugins', () => loadCatalogPlugins()],
    'skills-installed': ['skills-installed', () => loadInstalledSkills(profile)],
    'skills-catalog': ['catalog-skills', () => loadCatalogSkillsOnce()],
    'skills-archive': ['skills-archive', () => loadArchivedSkills()],
    'connectors-installed': ['servers', () => loadServers(profile)],
    'connectors-catalog': ['mcp-catalog', () => loadMcpCatalog(profile)],
    tools: ['toolsets', () => loadToolsets(profile)]
  }
  const otherFilter = filter === 'catalog' ? (kind === 'plugins' ? 'catalog' : `${kind}-catalog`) : kind === 'plugins' ? 'catalog' : `${kind}-catalog`
  const first = pairs[otherFilter] || pairs[kind]

  // Each landed job reports back on its own, so a count appears as soon as its
  // door answers instead of waiting for the slowest one.
  const track = (key, job) => {
    const promise = warmOnce(key, job)

    if (typeof onLanded === 'function') {
      void promise.then(() => onLanded())
    }

    return promise
  }

  if (first) {
    track(first[0], first[1])
  }

  await new Promise(resolve => {
    later(resolve, 900)
  })

  for (const [key, job] of Object.values(pairs)) {
    if (!first || key !== first[0]) {
      track(key, job)
    }
  }
}

/** Artwork the plugin folders carry themselves, keyed by normalized name. A
 *  plugin outside the public catalog has no hero image to borrow, so its row
 *  would show initials; the backend hands back the file it already ships. */
async function loadPluginIcons() {
  if (cache.icons && Date.now() - cache.iconsAt < CACHE_MS) {
    return cache.icons
  }

  if (typeof ctxRef?.rest !== 'function') {
    return new Map()
  }

  const payload = await withTimeout(ctxRef.rest('/icons'), RPC_MS, 'The plugin icon service')
  const icons = new Map()

  for (const row of Array.isArray(payload?.rows) ? payload.rows : []) {
    const data = str(row?.data)

    if (!data) {
      continue
    }

    if (row.name) {
      icons.set(shortName(str(row.name)), data)
    }

    if (row.key) {
      icons.set(shortName(str(row.key)), data)
    }
  }

  cache.icons = icons
  cache.iconsAt = Date.now()

  return icons
}


/* ---------------------------------------------------------------- mapping */

function catalogItem(row) {
  const key = str(row.key) || shortName(row.name)

  return {
    uid: `cat:${key}`,
    kind: 'plugin',
    origin: 'catalog',
    key,
    name: str(row.name) || key,
    short: shortName(row.slug || row.name),
    description: str(row.description),
    category: str(row.category) || 'general',
    tier: str(row.tier) || 'community',
    provider: str(row.maintainer),
    version: str(row.version),
    hero: str(row.hero) || str(row.image),
    screenshots: Array.isArray(row.screenshots) ? row.screenshots : [],
    stars: typeof row.stars === 'number' ? row.stars : null,
    requiresHermes: str(row.requiresHermes),
    platforms: Array.isArray(row.platforms) ? row.platforms : [],
    tools: Array.isArray(row.tools) ? row.tools : [],
    hooks: Array.isArray(row.hooks) ? row.hooks : [],
    middleware: Array.isArray(row.middleware) ? row.middleware : [],
    requiresEnv: Array.isArray(row.requiresEnv) ? row.requiresEnv : [],
    installCommand: str(row.installCommand),
    docsUrl: str(row.docsUrl),
    repo: str(row.repo),
    sha: str(row.shaShort) || str(row.sha),
    updatedAt: str(row.updatedAt),
    featured: typeof row.featured === 'number' ? row.featured : null,
    installed: false,
    enabled: false
  }
}

function installedPluginItem(row) {
  const key = str(row.key) || str(row.name)
  const catalogKey = str(row.catalog_name) || str(row.name)

  return {
    uid: `ins:${key}`,
    kind: 'plugin',
    origin: 'installed',
    key,
    catalogKey: shortName(catalogKey),
    name: str(row.name) || key,
    short: shortName(catalogKey || key),
    description: str(row.description),
    category: '',
    tier: str(row.catalog_tier) || str(row.source) || 'local',
    provider: str(row.source),
    version: str(row.version),
    hero:
      str(row.hero) ||
      cache.icons?.get(shortName(str(row.name) || key)) ||
      cache.icons?.get(shortName(key)) ||
      '',
    screenshots: [],
    stars: null,
    requiresHermes: '',
    platforms: [],
    tools: Array.isArray(row.tools) ? row.tools : [],
    hooks: [],
    middleware: [],
    requiresEnv: [],
    installCommand: '',
    docsUrl: '',
    repo: str(row.catalog_repo) || '',
    sha: str(row.installed_sha),
    updatedAt: '',
    featured: null,
    installed: true,
    // `plugins.manage list` reports `status`, the fast `plugins.list` reports a
    // boolean; both are the same bit.
    enabled: row.status === undefined || row.status === null ? row.enabled !== false : str(row.status) === 'enabled',
    installDir: str(row.install_dir),
    hasDesktopHalf: Boolean(row.has_desktop_half),
    updateAvailable: Boolean(row.update_available),
    pinnedSha: str(row.pinned_sha),
    portable: Boolean(row.portable),
    servers: Array.isArray(row.servers) ? row.servers : [],
    settingsSchema: Array.isArray(row.settings_schema) ? row.settings_schema : []
  }
}

function skillItem(row) {
  const name = str(row.name)

  return {
    uid: `skill:${name}`,
    kind: 'skill',
    origin: 'installed',
    key: name,
    name,
    short: shortName(name),
    description: str(row.description),
    category: str(row.category) || 'general',
    tier: str(row.provenance) || 'agent',
    provider: str(row.provenance),
    enabled: row.enabled !== false,
    usage: typeof row.usage === 'number' ? row.usage : 0,
    locked: Boolean(row.locked),
    tools: [],
    hooks: [],
    middleware: [],
    requiresEnv: [],
    platforms: [],
    screenshots: []
  }
}

function catalogSkillItem(row) {
  const name = str(row.name)
  const identifier = str(row.installIdentifier) || str(row.identifier) || name

  return {
    uid: `hub:${str(row.identifier) || name}`,
    kind: 'skill',
    origin: 'catalog',
    key: name,
    identifier,
    name: name || identifier,
    short: shortName(name || identifier),
    description: str(row.description),
    category: str(row.categoryLabel) || str(row.category) || 'hub',
    tier: str(row.source) || 'hub',
    provider: str(row.source),
    tags: Array.isArray(row.tags) ? row.tags.filter(tag => typeof tag === 'string') : [],
    installed: false,
    enabled: true,
    usage: 0,
    tools: [],
    hooks: [],
    middleware: [],
    requiresEnv: [],
    platforms: [],
    screenshots: []
  }
}

/** A skill the curator archived: the .archive folder is the whole record. */
function archivedSkillItem(row) {
  const name = str(row.name)

  return {
    uid: `archive:${str(row.folder) || name}`,
    kind: 'skill',
    origin: 'archive',
    key: name,
    name: name || str(row.folder),
    short: shortName(name || str(row.folder)),
    description: str(row.description),
    category: str(row.category) || 'archived',
    tier: 'archived',
    provider: 'curator',
    version: str(row.version),
    archivedAt: str(row.archivedAt),
    folder: str(row.folder),
    path: str(row.path),
    installed: false,
    enabled: false,
    usage: 0,
    tools: [],
    hooks: [],
    middleware: [],
    requiresEnv: [],
    platforms: [],
    screenshots: []
  }
}

function toolsetItem(row) {
  const name = str(row.name)
  const tools = Array.isArray(row.tools) ? row.tools : []

  return {
    uid: `tool:${name}`,
    kind: 'tool',
    origin: 'installed',
    key: name,
    name: str(row.label) || name,
    short: shortName(name),
    description: str(row.description),
    category: row.configured ? 'configured' : '',
    tier: '',
    provider: '',
    enabled: row.enabled !== false,
    configured: Boolean(row.configured),
    tools,
    hooks: [],
    middleware: [],
    requiresEnv: [],
    platforms: [],
    screenshots: [],
    usage: tools.length
  }
}

function serverItem(row) {
  const name = str(row.name)

  return {
    uid: `conn:${name}`,
    kind: 'connector',
    origin: 'installed',
    key: name,
    name,
    short: shortName(name),
    description: str(row.description) || [str(row.transport), str(row.command) || str(row.url)].filter(Boolean).join(' · '),
    category: str(row.transport) || 'mcp',
    tier: str(row.source) || 'config',
    provider: str(row.source) || 'config',
    enabled: row.enabled !== false,
    transport: str(row.transport),
    url: str(row.url),
    command: str(row.command),
    args: Array.isArray(row.args) ? row.args : [],
    requiresEnv: Array.isArray(row.env) ? row.env : [],
    auth: str(row.auth),
    tools: [],
    hooks: [],
    middleware: [],
    platforms: [],
    screenshots: []
  }
}

function mcpCatalogItem(row) {
  const name = str(row.name)
  const slug = str(row.connector_slug) || shortName(name)

  return {
    uid: `mcp:${slug}`,
    kind: 'connector',
    origin: 'catalog',
    key: slug,
    name,
    short: shortName(slug),
    description: str(row.description),
    category: str(row.transport) || 'mcp',
    tier: 'preset',
    provider: 'MCP catalog',
    enabled: Boolean(row.enabled),
    installed: Boolean(row.installed),
    transport: str(row.transport),
    requiresEnv: Array.isArray(row.requires) ? row.requires : [],
    tools: [],
    hooks: [],
    middleware: [],
    platforms: [],
    screenshots: []
  }
}

/** Catalog rows remember which of them this profile already has installed. */
/** Append a page without duplicating a row an earlier page already painted. */
function mergeRows(previous, incoming) {
  const seen = new Set(previous.map(row => row.uid))

  return [...previous, ...incoming.filter(row => !seen.has(row.uid))]
}

function annotateCatalog(rows, installed) {
  if (!installed.length) {
    return rows
  }

  const byName = new Map()

  for (const row of installed) {
    byName.set(shortName(row.catalogKey || row.name), row)
  }

  return rows.map(row => {
    const match = byName.get(row.key)

    return match
      ? {
          ...row,
          installed: true,
          enabled: match.enabled,
          installedVersion: match.version,
          updateAvailable: match.updateAvailable
        }
      : row
  })
}

function matches(item, query) {
  if (!query) {
    return true
  }

  const haystack = [
    item.name,
    item.short,
    item.description,
    item.category,
    item.tier,
    item.provider,
    item.key,
    item.transport,
    item.url,
    ...(item.tools || []),
    ...(item.hooks || []),
    ...(item.requiresEnv || [])
  ]
    .join(' ')
    .toLowerCase()

  return query
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every(part => haystack.includes(part))
}

function sortCatalog(rows) {
  return [...rows].sort((a, b) => {
    if (Boolean(a.featured) !== Boolean(b.featured)) {
      return a.featured ? -1 : 1
    }

    if ((b.stars || 0) !== (a.stars || 0)) {
      return (b.stars || 0) - (a.stars || 0)
    }

    return a.name.localeCompare(b.name)
  })
}

/* ------------------------------------------------------------------- atoms */

/** Chips are the app's own Badge, so tone mapping goes through its variants
 *  instead of a private pill style. */
const CHIP_VARIANT = { accent: 'default', plain: 'outline', muted: 'muted', warn: 'warn' }
const plural = (count, word) => `${count} ${word}${count === 1 ? '' : 's'}`

function Chip({ label, tone }) {
  return jsx(Badge, { variant: CHIP_VARIANT[tone] || 'outline', title: label, children: label })
}

function chipsFor(item) {
  const chips = []

  if (item.kind === 'tool') {
    if (item.configured) {
      chips.push({ label: 'configured', tone: 'plain' })
    }

    if (item.tools?.length) {
      chips.push({ label: plural(item.tools.length, 'tool'), tone: 'plain' })
    }

    return chips
  }

  if (item.kind === 'connector') {
    if (!item.installed && item.origin !== 'installed') {
      chips.push({ label: 'preset', tone: 'plain' })
    }

    if (item.transport || item.category) {
      chips.push({ label: item.transport || item.category, tone: 'plain' })
    }

    if (item.requiresEnv?.length) {
      chips.push({ label: `${item.requiresEnv.length} keys`, tone: 'plain' })
    }

    return chips
  }

  if (item.kind === 'plugin') {
    if (item.installed || item.origin === 'installed') {
      if (item.category) {
        chips.push({ label: item.category, tone: 'plain' })
      }

      if (item.updateAvailable) {
        chips.push({ label: 'update', tone: 'warn' })
      }

      return chips
    }

    if (item.category) {
      chips.push({ label: item.category, tone: 'plain' })
    }

    if (item.tier) {
      chips.push({ label: item.tier, tone: item.tier === 'official' || item.tier === 'verified' ? 'accent' : 'plain' })
    }

    return chips
  }

  if (item.category) {
    chips.push({ label: item.category, tone: 'plain' })
  }

  if (item.tier) {
    chips.push({ label: item.tier, tone: 'plain' })
  }

  if (item.usage) {
    chips.push({ label: `${item.usage} uses`, tone: 'plain' })
  }

  if (item.enabled === false) {
    chips.push({ label: 'off', tone: 'muted' })
  }

  return chips
}

function Thumb({ item, size = 40, radius = 10 }) {
  const hero = str(item.hero)
  const [broken, setBroken] = useState(false)

  useEffect(() => {
    setBroken(false)
  }, [hero])

  if (hero && !broken) {
    return el('img', {
      src: hero,
      alt: '',
      loading: 'lazy',
      draggable: false,
      onError: () => setBroken(true),
      style: {
        width: size,
        height: size,
        borderRadius: radius,
        objectFit: 'cover',
        border: `1px solid ${C.stroke2}`,
        boxShadow: 'inset 0 0 0 1px rgba(255,255,255,0.04)',
        flex: '0 0 auto',
        background: C.chip
      }
    })
  }

  const hue = hashOf(item.name || item.key)

  return el(
    'div',
    {
      'aria-hidden': true,
      style: {
        width: size,
        height: size,
        borderRadius: radius,
        flex: '0 0 auto',
        display: 'grid',
        placeItems: 'center',
        border: `1px solid ${C.stroke2}`,
        background: `linear-gradient(148deg, hsl(${hue} 34% 32%), hsl(${(hue + 34) % 360} 30% 17%))`,
        color: 'rgba(255,255,255,0.86)',
        fontSize: Math.round(size * 0.32),
        fontWeight: 600,
        letterSpacing: '0.02em'
      }
    },
    initialsOf(item.name || item.key)
  )
}

/* ------------------------------------------------------------------- rows */

/** Where the tags live depends on the kind: a plugin keeps its short name in a
 *  column and wears its tags on the description line, while skills, connectors
 *  and tools trade the short-name column for a tags column of their own. */
function layoutFor(item) {
  const switchable =
    item.kind === 'tool' ||
    (item.kind === 'plugin' && item.origin === 'installed') ||
    // A skill's switch is its archive state: off moves the folder into
    // skills/.archive so it stops loading, on moves it back out.
    item.kind === 'skill' ||
    (CAN_TOGGLE_CONNECTORS && item.kind === 'connector' && item.origin === 'installed')
  const online = item.origin === 'catalog'
  const tagsOnTextLine = item.kind === 'plugin' && !online
  const tail = tagsOnTextLine ? '190px' : '210px'
  const columns = online
    ? (switchable ? '44px minmax(0, 1fr) 44px' : '44px minmax(0, 1fr)')
    : (switchable ? `44px minmax(0, 1fr) ${tail} 44px` : `44px minmax(0, 1fr) ${tail}`)

  return { switchable, tagsOnTextLine, columns, online }
}

function Row({ item, selected, pending, onOpen, onHover, onHoverEnd, onToggle }) {
  const [hovered, setHovered] = useState(false)
  const chips = chipsFor(item)
  // A pill that describes the item as a whole rides the name line: the version
  // for a plugin, the usage count for a skill. Everything else is a tag and
  // stays with the description.
  const onNameLine = chip =>
    chip.label === 'update' || (item.kind === 'skill' && /^[\d.,]+\s+uses$/.test(chip.label))
  const nameChips = chips.filter(onNameLine)
  const tags = chips.filter(chip => !onNameLine(chip))
  const extra = Math.max(0, tags.length - 3)
  const shown = tags.slice(0, 3)
  const layout = layoutFor(item)

  const chipNodes = [
    ...shown.map(chip => jsx(Chip, { key: `${item.uid}:${chip.label}`, label: chip.label, tone: chip.tone })),
    extra > 0 ? jsx(Chip, { key: `${item.uid}:more`, label: `+${extra}`, tone: 'plain' }) : null
  ]

  const enter = event => {
    setHovered(true)
    onHover(item, event)
  }

  const move = event => onHover(item, event)

  const leave = () => {
    setHovered(false)
    onHoverEnd()
  }

  const open = () => onOpen(item)

  const text = item.description || (item.origin === 'installed' ? 'Installed locally' : '')

  return el(
    'div',
    {
      role: 'button',
      tabIndex: 0,
      'aria-label': `${item.name}. ${chipSummary(item)}`,
      'data-catalog-row': item.uid,
      onClick: open,
      onKeyDown: event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          open()
        }
      },
      onMouseEnter: enter,
      onMouseMove: move,
      onFocus: event => onHover(item, event),
      onBlur: leave,
      onMouseLeave: leave,
      style: {
        display: 'grid',
        gridTemplateColumns: layout.columns,
        alignItems: 'start',
        gap: 14,
        padding: '10px 14px',
        borderRadius: 12,
        cursor: 'pointer',
        outline: 'none',
        background: selected ? C.rowOpen : hovered ? C.rowHover : 'transparent',
        // An item that is off reads as inactive at a glance; it stays legible
        // and clickable, so the row is dimmed rather than ghosted.
        opacity: item.enabled === false ? 0.55 : 1,
        boxShadow: selected
          ? `inset 0 0 0 1px ${C.stroke2}`
          : `inset 0 -1px 0 color-mix(in srgb, ${C.stroke} 60%, transparent)`,
        transition: `background 150ms ${EASE_OUT}, box-shadow 150ms ${EASE_OUT}`,
        contain: 'layout paint'
      },
      children: [
        jsx(Thumb, { item, size: 38, radius: 9 }),
        el(
          'div',
          { style: { minWidth: 0, display: 'flex', flexDirection: 'column', gap: 3 } },
          el(
            'div',
            { style: { display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 } },
            jsx('span', {
              style: {
                fontSize: 13,
                fontWeight: 550,
                color: C.text,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                minWidth: 0
              },
              children: item.name
            }),
            nameChips.map(chip =>
              jsx(Chip, { key: `${item.uid}:name:${chip.label}`, label: chip.label, tone: chip.tone })
            )
          ),
          layout.tagsOnTextLine
            ? el(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 8, minWidth: 0 } },
                jsx('span', {
                  style: {
                    fontSize: 11.5,
                    color: C.text3,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    minWidth: 0,
                    flex: '0 1 auto'
                  },
                  children: text
                }),
                // Tags ride the description line, immediately after the text
                // rather than pushed to the far edge of the column.
                el(
                  'div',
                  {
                    style: {
                      display: 'flex',
                      alignItems: 'center',
                      gap: 5,
                      flex: '0 0 auto'
                    }
                  },
                  chipNodes
                )
              )
            : jsx('span', {
                style: {
                  fontSize: 11.5,
                  color: C.text3,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                },
                children: text
              })
        ),
        layout.online
          ? null
          : layout.tagsOnTextLine
          ? jsx('span', {
              title: item.short,
              style: {
                fontFamily: MONO,
                fontSize: 11.5,
                letterSpacing: '0.01em',
                color: C.text3,
                textAlign: 'left',
                paddingLeft: 2,
                paddingTop: 1,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                minWidth: 0
              },
              children: item.short
            })
          : el(
              'div',
              {
                style: {
                  display: 'flex',
                  alignItems: 'center',
                  gap: 5,
                  flexWrap: 'nowrap',
                  justifyContent: 'flex-start',
                  minWidth: 0,
                  paddingTop: 1,
                  overflow: 'hidden'
                }
              },
              chipNodes
            ),
        layout.switchable
          ? el(
              'div',
              {
                style: { display: 'flex', justifyContent: 'flex-end', paddingTop: 1 },
                // The switch is a control inside a clickable row: it must not
                // open the panel on its way to the backend.
                onClick: event => event.stopPropagation(),
                onKeyDown: event => event.stopPropagation()
              },
              jsx(Switch, {
                checked: item.enabled !== false,
                disabled: Boolean(pending),
                'aria-label': `${item.enabled === false ? 'Enable' : 'Disable'} ${item.name}`,
                onCheckedChange: value => onToggle?.(item, Boolean(value))
              })
            )
          : null
      ].filter(Boolean)
    }
  )
}

function chipSummary(item) {
  return [item.category, item.tier, item.installed ? (item.enabled ? 'enabled' : 'disabled') : 'catalog']
    .filter(Boolean)
    .join(', ')
}

/* ------------------------------------------------------------- hover card */

function HoverCard({ hover }) {
  const ref = useRef(null)
  const { item, rect } = hover

  useEffect(() => {
    tween(ref.current, [{ opacity: 0, transform: 'translate3d(0, 6px, 0) scale(0.985)' }, { opacity: 1, transform: 'none' }], {
      duration: 160,
      easing: EASE_OUT
    })
  }, [item.uid])

  const width = 384
  // A card carrying artwork is much taller than a text-only one, and the
  // placement has to know that or it flips above the row too late.
  const height = str(item.hero) ? 470 : 300
  const margin = 14
  const viewportW = typeof window === 'undefined' ? 1280 : window.innerWidth
  const viewportH = typeof window === 'undefined' ? 800 : window.innerHeight
  const rowLeft = rect ? rect.left : margin
  const below = rect ? rect.bottom + 6 : margin
  const above = rect ? rect.top - height - 6 : margin
  const left = Math.min(Math.max(margin, rowLeft + 44), Math.max(margin, viewportW - width - margin))
  const top = below + height + margin <= viewportH ? below : Math.max(margin, above)

  const hero = str(item.hero)

  const meta = (
    item.kind === 'skill'
      ? [
          { label: 'Category', value: item.category },
          { label: 'Source', value: item.tier },
          { label: 'Uses', value: item.usage ? plural(item.usage, 'use') : '' }
        ]
      : item.kind === 'tool'
        ? [
            { label: 'State', value: item.enabled ? 'enabled' : 'disabled' },
            { label: 'Tools', value: plural(item.tools?.length || 0, 'tool') },
            { label: 'Setup', value: item.configured ? 'ready' : 'needs config' }
          ]
        : item.kind === 'connector'
          ? [
              { label: 'Transport', value: item.transport || item.category },
              { label: 'Source', value: item.origin === 'installed' ? 'configured' : 'preset' },
              { label: 'Keys', value: item.requiresEnv?.length ? String(item.requiresEnv.length) : 'none' }
            ]
          : [
              { label: 'Provider', value: item.provider || item.tier },
              { label: 'Version', value: item.version ? `v${item.version}` : '' },
              { label: 'Stars', value: starsOf(item.stars) }
            ]
  ).filter(row => row.value)

  const capsule = [
    item.kind === 'plugin' || item.kind === 'connector' ? (item.tools?.length ? plural(item.tools.length, 'tool') : '') : '',
    item.hooks?.length ? plural(item.hooks.length, 'hook') : '',
    item.requiresEnv?.length ? plural(item.requiresEnv.length, 'env key') : '',
    item.requiresHermes ? `Hermes ${item.requiresHermes}` : ''
  ].filter(Boolean)

  return el(
    'div',
    {
      ref,
      role: 'tooltip',
      style: {
        position: 'fixed',
        left,
        top,
        width,
        zIndex: 80,
        pointerEvents: 'none',
        borderRadius: 14,
        border: `1px solid ${C.stroke2}`,
        ...SOLID,
        boxShadow: '0 22px 56px -22px rgba(0,0,0,0.6), 0 2px 10px -4px rgba(0,0,0,0.35)',
        overflow: 'hidden'
      }
    },
    // A plugin with artwork shows it twice on purpose: a wide banner for the
    // shape, and the thumbnail for identity beside the name.
    hero
      ? el('div', {
          style: {
            aspectRatio: '16 / 9',
            width: '100%',
            background: `linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,0.35)), url(${JSON.stringify(hero)}) center/cover`,
            borderBottom: `1px solid ${C.stroke}`
          }
        })
      : null,
    el(
      'div',
      { style: { padding: 14, display: 'flex', flexDirection: 'column', gap: 10 } },
      el(
        'div',
        { style: { display: 'flex', alignItems: 'center', gap: 10 } },
        jsx(Thumb, { item, size: 34, radius: 9 }),
        jsx('span', {
          style: { fontSize: 14.5, fontWeight: 600, color: C.text, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
          children: item.name
        })
      ),
      el(
        'div',
        { style: { display: 'flex', gap: 5, flexWrap: 'wrap' } },
        chipsFor(item).slice(0, 3).map(chip => jsx(Chip, { key: `hc:${chip.label}`, label: chip.label, tone: chip.tone }))
      ),
      jsx('p', {
        style: {
          margin: 0,
          fontSize: 12,
          lineHeight: 1.55,
          color: C.text2,
          display: '-webkit-box',
          WebkitLineClamp: 4,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden'
        },
        children: item.description || 'No description in the catalog.'
      }),
      el(
        'div',
        { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px 12px' } },
        [...meta, capsule.length ? { label: 'Includes', value: capsule.join(' · ') } : null]
          .filter(Boolean)
          .map(row =>
            el(
              'div',
              { key: `hc:${row.label}`, style: { minWidth: 0 } },
              jsx('div', {
                style: { fontSize: 9.5, letterSpacing: '0.09em', textTransform: 'uppercase', color: C.text4 },
                children: row.label
              }),
              jsx('div', {
                style: {
                  fontSize: 11.5,
                  color: C.text2,
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis'
                },
                children: row.value
              })
            )
          )
      )
    )
  )
}

/* ----------------------------------------------------------- detail panel */

function MetaRow({ action, label, value, mono }) {
  if (!value) {
    return null
  }

  return el(
    'div',
    { style: { display: 'flex', gap: 12, alignItems: 'baseline', padding: '5px 0' } },
    label
      ? jsx('span', {
          style: { fontSize: 10.5, letterSpacing: '0.07em', textTransform: 'uppercase', color: C.text4, width: 96, flex: '0 0 auto' },
          children: label
        })
      : null,
    jsx('span', {
      style: {
        fontSize: 12,
        color: C.text2,
        fontFamily: mono ? MONO : 'inherit',
        overflowWrap: 'anywhere',
        minWidth: 0,
        flex: 1
      },
      children: value
    }),
    action || null
  )
}

/** A label with its pills after it on the same line, so a short list reads as a
 *  property of the item instead of a heading with a block underneath. */
function LabelledTags({ label, values, empty }) {
  const list = Array.isArray(values) ? values.filter(Boolean) : []

  return el(
    'div',
    { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', minWidth: 0 } },
    jsx('span', {
      // Same label width as a metadata row, so the pills line up in a column
      // while still sitting beside their label.
      style: {
        fontSize: 10.5,
        letterSpacing: '0.07em',
        textTransform: 'uppercase',
        color: C.text4,
        width: 96,
        flex: '0 0 auto'
      },
      children: label
    }),
    list.length
      ? el(
          'div',
          { style: { display: 'flex', flexWrap: 'wrap', gap: 5, minWidth: 0 } },
          list.map(value => jsx(Chip, { key: `${label}:${value}`, label: value, tone: 'plain' }))
        )
      : jsx('span', { style: { fontSize: 11.5, color: C.text4 }, children: empty || 'None' })
  )
}

function Tags({ values, empty }) {
  if (!values || !values.length) {
    return jsx('div', { style: { fontSize: 11.5, color: C.text4 }, children: empty || 'None' })
  }

  return el(
    'div',
    { style: { display: 'flex', flexWrap: 'wrap', gap: 5 } },
    values.map(value => jsx(Chip, { key: `tag:${value}`, label: value, tone: 'plain' }))
  )
}

function sectionTitle(label) {
  return jsx('h3', {
    style: {
      margin: '0 0 8px',
      fontSize: 10.5,
      letterSpacing: '0.11em',
      textTransform: 'uppercase',
      color: C.text4,
      fontWeight: 600
    },
    children: label
  })
}

function DetailPanel({ item, profile, onClose, onChanged, onToggle }) {
  const [closing, setClosing] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [section, setSection] = useState('overview')
  const [enabled, setEnabled] = useState(item.enabled !== false)

  useEffect(() => {
    setEnabled(item.enabled !== false)
  }, [item.uid, item.enabled])
  const rootRef = useRef(null)
  const scrimRef = useRef(null)
  const railRef = useRef(null)
  const bodyRef = useRef(null)
  const refs = useRef({})

  const isPlugin = item.kind === 'plugin'
  const isSkill = item.kind === 'skill'
  const isTool = item.kind === 'tool'
  const isConnector = item.kind === 'connector'
  const isInstalled = item.installed || item.origin === 'installed'
  const itemChips = chipsFor(item).map(chip =>
    chip.label === 'on' ? { ...chip, label: 'Enabled' } : chip.label === 'off' ? { ...chip, label: 'Disabled' } : chip
  )

  const sections = [
    { id: 'overview', label: 'Overview', icon: 'preview' },
    ...(isTool
      ? [{ id: 'capabilities', label: 'Tools', icon: 'tools' }]
      : isConnector
        ? [{ id: 'capabilities', label: 'Connection', icon: 'plug' }]
        : isPlugin
          ? [
              { id: 'capabilities', label: 'Capabilities', icon: 'symbol-class' },
              { id: 'install', label: 'Install', icon: 'cloud-download' }
            ]
          : [{ id: 'install', label: 'Install', icon: 'cloud-download' }]),
    { id: 'actions', label: 'Actions', icon: 'settings-gear' }
  ]

  useEffect(() => {
    tween(rootRef.current, [{ opacity: 0, transform: 'translate3d(34px,0,0) scale(0.988)' }, { opacity: 1, transform: 'none' }], {
      duration: PANEL_MS,
      easing: EASE_SOFT
    })
    tween(scrimRef.current, [{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: EASE_OUT })

    const cancelFocus = later(() => rootRef.current?.focus?.(), 40)

    return cancelFocus
  }, [])

  useEffect(() => {
    tween(
      railRef.current,
      railOpen
        ? [{ opacity: 0, transform: 'translate3d(-10px,0,0)' }, { opacity: 1, transform: 'none' }]
        : [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translate3d(-8px,0,0)' }],
      { duration: 200, easing: railOpen ? EASE_OUT : EASE_IN }
    )
  }, [railOpen])

  /** The header switch: flip at once, let the page's own door do the work, and
   *  fall back if it refuses. */
  const flip = useCallback(
    value => {
      const next = Boolean(value)

      setEnabled(next)
      Promise.resolve(onToggle?.(item, next)).catch?.(() => setEnabled(!next))
    },
    [item, onToggle]
  )

  const requestClose = useCallback(() => {
    if (closing) {
      return
    }

    setClosing(true)
    tween(rootRef.current, [{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translate3d(28px,0,0) scale(0.99)' }], {
      duration: CLOSE_MS,
      easing: EASE_IN
    })
    tween(scrimRef.current, [{ opacity: 1 }, { opacity: 0 }], { duration: CLOSE_MS, easing: EASE_IN })
    later(onClose, CLOSE_MS)
  }, [closing, onClose])

  useEffect(() => {
    closePanel = requestClose

    return () => {
      closePanel = null
    }
  }, [requestClose])

  const goTo = id => {
    setSection(id)
    setRailOpen(false)
    const node = refs.current[id]
    const body = bodyRef.current

    if (node && body) {
      // Measure from the boxes: offsetTop is relative to the offset parent, not
      // to this scroll container, and the two diverge as soon as the panel gains
      // a positioned ancestor.
      const delta = node.getBoundingClientRect().top - body.getBoundingClientRect().top

      body.scrollTo({ top: Math.max(0, body.scrollTop + delta - 12), behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
    }
  }

  const copy = async text => {
    const ok = await ctxRef?.os?.writeClipboard?.(text)

    setNotice(ok ? 'Copied' : 'Could not copy')
  }

  const run = async (label, work, failure) => {
    setBusy(true)
    setNotice('')

    try {
      await work()
      setNotice(label)
      onChanged?.()
    } catch (error) {
      setNotice(`${failure}: ${String(error?.message || error || 'unknown error')}`)
    } finally {
      setBusy(false)
    }
  }

  const scoped = scopeParam(profile)

  const togglePlugin = () =>
    run(
      item.enabled ? 'Disabled' : 'Enabled',
      () => host.request('plugins.manage', { action: 'toggle', key: item.key, enable: !item.enabled, ...scoped }),
      'Could not toggle'
    )

  const toggleSkill = () =>
    run(
      item.enabled ? 'Disabled' : 'Enabled',
      () => host.skills.setEnabled(item.name, !item.enabled, profile && profile !== 'default' ? profile : undefined),
      'Could not toggle'
    )

  const toggleToolset = () =>
    run(
      item.enabled ? 'Disabled' : 'Enabled',
      () => host.toolsets.setEnabled(item.key, !item.enabled, profile && profile !== 'default' ? profile : undefined),
      'Could not toggle'
    )

  const installPlugin = () =>
    run(
      'Installed',
      () => host.request('plugins.manage', { action: 'install', catalog_name: item.name, enable: true, ...scoped }),
      'Install failed'
    )

  const updatePlugin = () =>
    run(
      'Updated',
      () => host.request('plugins.manage', { action: 'update', name: item.name, key: item.key, ...scoped }),
      'Update failed'
    )

  const installSkill = () =>
    run(
      'Installed',
      () => host.request('skills.manage', { action: 'install', query: item.identifier || item.name, ...scoped }),
      'Install failed'
    )

  const testServer = () =>
    run(
      'Connection OK',
      async () => {
        const result = await host.request('mcp.servers.test', { name: item.key, ...scoped })

        if (result && result.ok === false) {
          throw new Error(result.error || 'server did not answer')
        }
      },
      'Test failed'
    )

  const openNative = () => {
    const path = isTool ? '/capabilities?tab=toolsets' : isConnector ? '/capabilities?tab=connectors' : '/capabilities?tab=plugins'
    const result = ctxRef?.runAction?.('nav.capabilities')

    if (result && typeof result.then === 'function') {
      result.catch(() => host.navigate(path))
    } else if (!result) {
      host.navigate(path)
    }
  }

  /** The pair of moves: one sends the folder to skills/.archive, one brings it back. */
  const archiveSkill = () =>
    run(
      'Archived',
      async () => {
        await ctxRef.rest('/skills/archive/add', {
          method: 'POST',
          body: { name: item.folder || item.key }
        })

        cache.skills = null
        cache.skillsAt = 0
        cache.archived = null
        cache.archivedAt = 0
      },
      'Could not archive'
    )

  /** Archiving is a directory move, so a restore is the same move reversed. */
  const restoreSkill = () =>
    run(
      'Restored to skills',
      async () => {
        await ctxRef.rest('/skills/archive/restore', {
          method: 'POST',
          body: { folder: item.folder || item.key }
        })

        // Three caches just changed on disk: the archive row is gone, the
        // installed skill is new, and both counts moved.
        cache.archived = null
        cache.archivedAt = 0
        cache.skills = null
        cache.skillsAt = 0
      },
      'Could not restore'
    )

  const actions = []

  if (isSkill) {
    if (item.origin === 'archive') {
      actions.push({ id: 'restore', label: 'Restore skill', icon: 'history', run: restoreSkill, disabled: busy })
    } else if (isInstalled) {
      actions.push({ id: 'archive', label: 'Archive skill', icon: 'archive', run: archiveSkill, disabled: busy })
      if (!item.enabled) {
        actions.push({ id: 'enable', label: 'Enable skill', icon: 'check', run: toggleSkill, disabled: busy })
      }
    } else {
      actions.push({ id: 'install', label: 'Install skill', icon: 'cloud-download', run: installSkill, disabled: busy })
    }
  } else if (isTool) {
    actions.push({
      id: 'toggle',
      label: item.enabled ? 'Disable toolset' : 'Enable toolset',
      icon: item.enabled ? 'circle-slash' : 'check',
      run: toggleToolset,
      disabled: busy
    })
  } else if (isConnector) {
    if (isInstalled) {
      actions.push({ id: 'test', label: 'Test connection', icon: 'debug-alt', run: testServer, disabled: busy })
      if (item.url) {
        actions.push({ id: 'copy-url', label: 'Copy address', icon: 'copy', run: () => copy(item.url), disabled: false })
      }
    } else {
      actions.push({ id: 'add', label: 'Add from native Capabilities', icon: 'add', run: openNative, disabled: false })
    }
  } else if (isInstalled) {
    actions.push({
      id: 'toggle',
      label: item.enabled ? 'Disable plugin' : 'Enable plugin',
      icon: item.enabled ? 'circle-slash' : 'check',
      run: togglePlugin,
      disabled: busy
    })
    if (item.updateAvailable) {
      actions.push({ id: 'update', label: 'Update to catalog pin', icon: 'cloud-download', run: updatePlugin, disabled: busy })
    }
  } else {
    actions.push({ id: 'install', label: 'Install plugin', icon: 'cloud-download', run: installPlugin, disabled: busy })
  }


  actions.push({ id: 'native', label: 'Open in native Capabilities', icon: 'link-external', run: openNative, disabled: false })

  const keyRepeats = shortName(item.key) === shortName(item.name)

  const metaRows = [
    !keyRepeats ? jsx(MetaRow, { key: 'key', label: isSkill || isTool ? 'Name' : 'Key', value: item.key, mono: true }) : null,
    jsx(MetaRow, {
      key: 'provider',
      label: isSkill ? 'Category' : isTool ? 'State' : isConnector ? 'Transport' : 'Provider',
      value: isSkill ? item.category : isTool ? (item.enabled ? 'enabled' : 'disabled') : isConnector ? item.transport || item.category : item.provider || item.tier
    }),
    jsx(MetaRow, { key: 'version', label: 'Version', value: item.version ? `v${item.version}` : '' }),
    item.origin === 'archive'
      ? jsx(MetaRow, { key: 'archived', label: 'Archived', value: dateOf(item.archivedAt) })
      : null,
    jsx(MetaRow, {
      key: 'source',
      label: 'Source',
      value:
        item.origin === 'installed'
          ? 'Installed on this host'
          : item.origin === 'archive'
            ? 'Archived on this host'
            : isConnector
              ? 'MCP catalog preset'
              : 'Public catalog'
    }),
    jsx(MetaRow, {
      key: 'count',
      label: isSkill ? 'Uses' : isTool ? 'Tools' : 'Stars',
      value: isSkill ? String(item.usage || '') : isTool ? String(item.tools?.length || 0) : starsOf(item.stars)
    }),
    jsx(MetaRow, { key: 'updated', label: 'Updated', value: dateOf(item.updatedAt) })
  ].filter(Boolean)

  const body = [
    jsx('div', {
      key: 'overview-anchor',
      ref: node => {
        refs.current.overview = node
      }
    }),
    el(
      'div',
      { key: 'overview', style: { display: 'flex', flexDirection: 'column', gap: 14 } },
      el(
        'div',
        { style: { display: 'flex', gap: 12, alignItems: 'flex-start' } },
        jsx(Thumb, { item, size: 52, radius: 13 }),
        el(
          'div',
          { style: { minWidth: 0, flex: 1 } },
          el(
            'div',
            { style: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' } },
            jsx('span', {
              style: { fontSize: 17, fontWeight: 600, color: C.text, lineHeight: 1.25, overflowWrap: 'anywhere' },
              children: item.name
            }),
            itemChips.length === 1
              ? jsx(Chip, { label: itemChips[0].label, tone: itemChips[0].tone })
              : null
          ),
          item.short !== shortName(item.name)
            ? jsx('div', {
                style: { fontFamily: MONO, fontSize: 11.5, color: C.text4, marginTop: 3, overflowWrap: 'anywhere' },
                children: item.short
              })
            : null,
          // The description is a subtitle of the item, so it sits beside the
          // icon under the name rather than spanning the panel beneath it.
          jsx('p', {
            style: { margin: '6px 0 0', fontSize: 12.5, lineHeight: 1.55, color: C.text2, overflowWrap: 'anywhere' },
            children: item.description || 'No description available.'
          })
        )
      ),
      itemChips.length > 1
        ? el(
            'div',
            { style: { display: 'flex', flexWrap: 'wrap', gap: 5 } },
            itemChips.map(chip => jsx(Chip, { key: `dp:${chip.label}`, label: chip.label, tone: chip.tone }))
          )
        : null,
      el('div', { style: { borderTop: `1px solid ${C.stroke}`, paddingTop: 8 } }, metaRows)
    )
  ]

  if (!isSkill) {
    const capabilityRows = isTool
      ? [
          jsx(LabelledTags, { key: 'tools', label: 'Tools', values: item.tools, empty: 'No tools reported' })
        ]
      : isConnector
        ? [
            jsx(MetaRow, { key: 'transport', label: 'Transport', value: item.transport || item.category }),
            jsx(MetaRow, { key: 'url', label: 'Address', value: item.url, mono: true }),
            jsx(MetaRow, { key: 'cmd', label: 'Command', value: [item.command, ...(item.args || [])].filter(Boolean).join(' '), mono: true }),
            jsx(MetaRow, { key: 'auth', label: 'Auth', value: item.auth }),
            jsx(LabelledTags, { key: 'keys', label: 'Keys', values: item.requiresEnv, empty: 'No keys needed' })
          ]
        : [
            jsx(LabelledTags, { key: 'tools', label: 'Tools', values: item.tools, empty: 'No agent tools declared' }),
            jsx(LabelledTags, { key: 'hooks', label: 'Hooks', values: item.hooks, empty: 'No hooks declared' }),
            item.middleware.length
              ? jsx(LabelledTags, { key: 'mw', label: 'Middleware', values: item.middleware })
              : null,
            item.requiresEnv.length
              ? jsx(LabelledTags, { key: 'env', label: 'Environment', values: item.requiresEnv })
              : null,
            item.platforms.length
              ? jsx(LabelledTags, { key: 'platforms', label: 'Platforms', values: item.platforms })
              : null,
            item.requiresHermes ? jsx(MetaRow, { key: 'floor', label: 'Hermes', value: item.requiresHermes, mono: true }) : null
          ]

    body.push(
      el(
        'div',
        {
          key: 'capabilities',
          ref: node => {
            refs.current.capabilities = node
          },
          style: { borderTop: `1px solid ${C.stroke}`, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }
        },
        sectionTitle(sections.find(entry => entry.id === 'capabilities')?.label || 'Capabilities'),
        capabilityRows
      )
    )
  }

  if (isPlugin || isSkill) {
    const command =
      item.origin === 'archive'
        ? ''
        : isSkill
          ? item.identifier
            ? `hermes skills install ${item.identifier}`
            : ''
          : item.installCommand

    body.push(
      el(
        'div',
        {
          key: 'install',
          ref: node => {
            refs.current.install = node
          },
          style: { borderTop: `1px solid ${C.stroke}`, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }
        },
        sectionTitle(item.origin === 'archive' ? 'Archive' : 'Install'),
        item.origin === 'archive'
          ? el(
              'div',
              { style: { fontSize: 12, color: C.text2, lineHeight: 1.6 } },
              'The curator moved this skill out of skills/ so it stops loading. Restore moves the folder back; nothing was deleted.'
            )
          : null,
        item.origin === 'archive' && item.path
          ? jsx(MetaRow, {
              label: 'Folder',
              value: item.path,
              mono: true,
              action: el(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 4, flex: '0 0 auto' } },
                jsx(Button, {
                  size: 'xs',
                  variant: 'ghost',
                  onClick: () => ctxRef?.os?.revealPath?.(item.path),
                  children: 'Open'
                }),
                jsx(Button, {
                  size: 'xs',
                  variant: 'ghost',
                  'aria-label': 'Copy the folder path',
                  onClick: () => void copy(item.path),
                  children: jsx(Codicon, { name: 'copy', size: '0.8rem' })
                })
              )
            })
          : null,
        command
          ? el(
              'div',
              { style: { display: 'flex', gap: 8, alignItems: 'center' } },
              jsx('code', {
                style: {
                  flex: 1,
                  minWidth: 0,
                  fontFamily: MONO,
                  fontSize: 11.5,
                  color: C.text2,
                  background: C.chip,
                  border: `1px solid ${C.stroke}`,
                  borderRadius: 8,
                  padding: '7px 9px',
                  overflowX: 'auto',
                  whiteSpace: 'nowrap'
                },
                children: command
              }),
              jsx(Button, {
                size: 'xs',
                variant: 'outline',
                'aria-label': 'Copy the install command',
                onClick: () => void copy(command),
                children: jsx(Codicon, { name: 'copy', size: '0.8rem' })
              })
            )
          : null,
        jsx(MetaRow, { label: 'Repository', value: item.repo, mono: true }),
        jsx(MetaRow, { label: 'Commit', value: item.sha, mono: true }),
        item.pinnedSha ? jsx(MetaRow, { label: 'Catalog pin', value: item.pinnedSha, mono: true }) : null,
        item.installDir
          ? jsx(MetaRow, {
              label: 'Install folder',
              value: item.installDir,
              mono: true,
              action: el(
                'div',
                { style: { display: 'flex', alignItems: 'center', gap: 4, flex: '0 0 auto' } },
                jsx(Button, {
                  size: 'xs',
                  variant: 'ghost',
                  onClick: () => ctxRef?.os?.revealPath?.(item.installDir),
                  children: 'Open'
                }),
                jsx(Button, {
                  size: 'xs',
                  variant: 'ghost',
                  'aria-label': 'Copy the folder path',
                  onClick: () => void copy(item.installDir),
                  children: jsx(Codicon, { name: 'copy', size: '0.8rem' })
                })
              )
            })
          : null,
        isSkill && item.identifier ? jsx(MetaRow, { label: 'Identifier', value: item.identifier, mono: true }) : null,
        !command && !item.repo && !item.installDir && (!isSkill || !item.identifier)
          ? jsx('div', { style: { fontSize: 11.5, color: C.text4 }, children: 'Bundled with Hermes; nothing to install.' })
          : null
      )
    )
  }

  body.push(
    el(
      'div',
      {
        key: 'actions',
        ref: node => {
          refs.current.actions = node
        },
        style: { borderTop: `1px solid ${C.stroke}`, paddingTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }
      },
      sectionTitle('Actions'),
      el(
        'div',
        { style: { display: 'flex', flexWrap: 'wrap', gap: 7 } },
        actions.map(action =>
          jsx(Button, {
            key: action.id,
            size: 'sm',
            variant: action.id === 'native' ? 'ghost' : 'outline',
            disabled: action.disabled,
            onClick: () => void action.run(),
            children: el(
              'span',
              { style: { display: 'inline-flex', alignItems: 'center', gap: 6 } },
              jsx(Codicon, { name: action.icon, size: '0.85rem' }),
              action.label
            )
          })
        )
      ),
      notice
        ? jsx('div', {
            style: { fontSize: 11.5, color: notice.startsWith('Could not') || notice.startsWith('Test failed') ? 'var(--ui-red)' : C.text3 },
            children: notice
          })
        : null,
      jsx('div', {
        style: { fontSize: 10.5, color: C.text4, lineHeight: 1.5 },
        children:
          item.kind === 'connector'
            ? 'Connectors are MCP servers; a preset that needs keys is added in the native page, where the form lives.'
            : item.kind === 'tool'
              ? 'Toolsets decide what the agent may call. The toggle writes the same setting the native page writes.'
              : 'Enable state and installs go through the same backend the native page uses; desktop-only halves stay in Capabilities ▸ Plugins.'
      })
    )
  )

  return [
    jsx('div', {
      key: 'scrim',
      ref: scrimRef,
      onClick: requestClose,
      style: {
        position: 'absolute',
        inset: 0,
        background: 'color-mix(in oklab, var(--ui-bg-primary) 30%, transparent)',
        backdropFilter: 'blur(1.5px)',
        zIndex: 40
      }
    }),
    el(
      'aside',
      {
        key: 'panel',
        ref: rootRef,
        role: 'dialog',
        'aria-label': `${item.name} details`,
        tabIndex: -1,
        style: {
          position: 'absolute',
          top: 0,
          right: 0,
          bottom: 0,
          width: 'clamp(380px, 34vw, 462px)',
          zIndex: 41,
          display: 'flex',
          flexDirection: 'column',
          ...SOLID,
          borderLeft: `1px solid ${C.stroke2}`,
          boxShadow: '-36px 0 80px -40px rgba(0,0,0,0.72), -1px 0 0 color-mix(in srgb, var(--ui-base) 8%, transparent)',
          outline: 'none'
        }
      },
      // The plugin's own artwork as the panel's header, inside the surface and
      // clear of the rail: the same image the row thumbnails borrow.
      str(item.hero)
        ? jsx('div', {
            'aria-hidden': true,
            style: {
              marginLeft: 44,
              aspectRatio: '16 / 9',
              maxHeight: 210,
              flex: '0 0 auto',
              background: `linear-gradient(180deg, rgba(0,0,0,0) 45%, rgba(0,0,0,0.4)), url(${JSON.stringify(str(item.hero))}) center/cover`,
              borderBottom: `1px solid ${C.stroke}`
            }
          })
        : null,
      el(
        'div',
        {
          style: {
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '10px 12px 10px 56px',
            borderBottom: `1px solid ${C.stroke}`,
            minHeight: 44
          }
        },
        el(
          'div',
          { style: { flex: 1, minWidth: 0, display: 'flex', alignItems: 'baseline', gap: 7 } },
          jsx('span', {
            style: { fontSize: 9.5, letterSpacing: '0.11em', textTransform: 'uppercase', color: C.text4 },
            children: item.kind
          }),
          jsx('span', { style: { fontSize: 9.5, color: C.text4 }, children: '/' }),
          jsx('span', {
            style: { fontSize: 9.5, letterSpacing: '0.11em', textTransform: 'uppercase', color: C.text3 },
            children: section
          })
        ),
        // The header carries the item's own on/off, where the row switch is out
        // of reach: the section rail is always there, so its toggle is not.
        isInstalled
          ? jsx(Switch, {
              checked: enabled,
              disabled: busy,
              'aria-label': `${enabled ? 'Disable' : 'Enable'} ${item.name}`,
              onCheckedChange: flip
            })
          : null,
        jsx(Button, {
          size: 'icon',
          variant: 'ghost',
          'aria-label': 'Close details',
          onClick: requestClose,
          children: jsx(Codicon, { name: 'close', size: '0.9rem' })
        })
      ),
      jsx('div', {
        'aria-hidden': true,
        style: {
          position: 'absolute',
          top: 0,
          bottom: 0,
          left: 43,
          width: 22,
          pointerEvents: 'none',
          background: 'linear-gradient(to right, rgba(0,0,0,0.20), rgba(0,0,0,0))'
        }
      }),
      jsx('div', {
        ref: bodyRef,
        style: {
          flex: 1,
          minHeight: 0,
          overflowY: 'auto',
          overflowX: 'hidden',
          padding: '16px 16px 40px 56px',
          display: 'flex',
          flexDirection: 'column',
          gap: 14
        },
        children: body
      }),
      jsx('div', {
        'aria-hidden': true,
        style: {
          position: 'absolute',
          left: 44,
          right: 0,
          bottom: 0,
          height: 26,
          pointerEvents: 'none',
          // The panel's own surface, faded out by a mask: a gradient of a token
          // the theme may set to `transparent` would simply show the list through.
          backgroundColor: 'var(--theme-neutral-card, var(--ui-bg-editor, #161618))',
          backgroundImage: 'linear-gradient(var(--ui-bg-editor), var(--ui-bg-editor))',
          maskImage: 'linear-gradient(to top, rgba(0,0,0,1), rgba(0,0,0,0))',
          WebkitMaskImage: 'linear-gradient(to top, rgba(0,0,0,1), rgba(0,0,0,0))'
        }
      }),
      el(
        'nav',
        {
          onMouseEnter: () => setRailOpen(true),
          onMouseLeave: () => setRailOpen(false),
          style: {
            position: 'absolute',
            top: 0,
            bottom: 0,
            left: 0,
            width: 44,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            gap: 4,
            padding: '10px 0',
            borderRight: `1px solid ${C.stroke}`,
            background: 'color-mix(in oklab, var(--ui-bg-sidebar) 88%, transparent)'
          }
        },
        sections.map(entry =>
          jsx(Tip, {
            key: `rail:${entry.id}`,
            label: entry.label,
            children: jsx(Button, {
              size: 'icon',
              variant: 'ghost',
              'aria-label': entry.label,
              'aria-pressed': section === entry.id,
              onClick: () => goTo(entry.id),
              style: {
                color: section === entry.id ? C.accent : C.text3,
                background: section === entry.id ? 'color-mix(in oklab, var(--ui-accent) 14%, transparent)' : 'transparent',
                boxShadow: section === entry.id ? `inset 2px 0 0 ${C.accent}` : 'none'
              },
              children: jsx(Codicon, { name: entry.icon, size: '0.9rem' })
            })
          })
        ),
        el(
          'div',
          {
            ref: railRef,
            'aria-hidden': !railOpen,
            style: {
              position: 'absolute',
              left: 44,
              top: 10,
              width: 176,
              padding: 6,
              borderRadius: 10,
              border: `1px solid ${C.stroke2}`,
              ...SOLID,
              boxShadow: '0 18px 44px -22px rgba(0,0,0,0.6)',
              display: railOpen ? 'flex' : 'none',
              flexDirection: 'column',
              gap: 2,
              zIndex: 3
            }
          },
          sections.map(entry =>
            jsx(Button, {
              key: `sheet:${entry.id}`,
              size: 'sm',
              variant: 'ghost',
              onClick: () => goTo(entry.id),
              style: {
                justifyContent: 'flex-start',
                color: section === entry.id ? C.accent : C.text2,
                background: section === entry.id ? 'color-mix(in oklab, var(--ui-accent) 12%, transparent)' : 'transparent'
              },
              children: el(
                'span',
                { style: { display: 'inline-flex', alignItems: 'center', gap: 8 } },
                jsx(Codicon, { name: entry.icon, size: '0.8rem' }),
                entry.label
              )
            })
          )
        )
      )
    )
  ]
}

/* --------------------------------------------------------------- settings */

/** Moves a kind along the header selector. Buttons, not drag: the header is a
 *  segmented control, so the order should be readable and reversible by keyboard. */
function KindOrderControl({ draft, onChange }) {
  const order = normalizeOrder(draft.kindOrder)
  const labelOf = id => (KINDS.find(entry => entry.id === id) || { label: id }).label

  const move = (index, delta) => {
    const target = index + delta

    if (target < 0 || target >= order.length) {
      return
    }

    const next = order.slice()

    ;[next[index], next[target]] = [next[target], next[index]]
    onChange(next)
  }

  return el(
    'div',
    { style: { display: 'flex', flexDirection: 'column', paddingTop: 10 } },
    jsx('div', {
      style: { fontSize: 10.5, letterSpacing: '0.11em', textTransform: 'uppercase', color: C.text4 },
      children: 'Header order'
    }),
    jsx('div', {
      style: { fontSize: 11.5, color: C.text3, paddingTop: 2, paddingBottom: 4 },
      children: 'Left to right in the selector.'
    }),
    order.map((id, index) =>
      el(
        'div',
        {
          key: id,
          style: { display: 'flex', alignItems: 'center', gap: 4, padding: '2px 0', minHeight: 26 }
        },
        jsx('span', {
          style: { flex: '1 1 auto', fontSize: 12.5, color: C.text },
          children: labelOf(id)
        }),
        jsx(Button, {
          size: 'icon',
          variant: 'ghost',
          disabled: index === 0,
          'aria-label': `Move ${labelOf(id)} left`,
          onClick: () => move(index, -1),
          children: jsx(Codicon, { name: 'chevron-left', size: '0.85rem' })
        }),
        jsx(Button, {
          size: 'icon',
          variant: 'ghost',
          disabled: index === order.length - 1,
          'aria-label': `Move ${labelOf(id)} right`,
          onClick: () => move(index, 1),
          children: jsx(Codicon, { name: 'chevron-right', size: '0.85rem' })
        })
      )
    )
  )
}

function SettingsCard({ onClose, onOrderChange }) {
  const [draft, setDraft] = useState(settings)
  const ref = useRef(null)

  useEffect(() => {
    tween(ref.current, [{ opacity: 0, transform: 'translate3d(0,-6px,0) scale(0.99)' }, { opacity: 1, transform: 'none' }], {
      duration: 170,
      easing: EASE_OUT
    })
  }, [])

  const update = next => {
    const merged = { ...draft, ...next }

    setDraft(merged)
    persistSettings(next)
  }

  return el(
    'div',
    {
      ref,
      style: {
        position: 'absolute',
        top: 52,
        right: 16,
        width: 336,
        maxHeight: 'calc(100% - 96px)',
        overflow: 'auto',
        zIndex: 45,
        padding: '10px 14px 8px',
        borderRadius: 14,
        border: `1px solid ${C.stroke2}`,
        ...SOLID,
        boxShadow: '0 26px 60px -28px rgba(0,0,0,0.6)'
      }
    },
    jsx('div', {
      style: { fontSize: 10.5, letterSpacing: '0.11em', textTransform: 'uppercase', color: C.text4, paddingBottom: 4 },
      children: 'Page settings'
    }),
    jsx(ToggleRow, {
      label: 'Always show installed',
      description: 'Entering Skills, Plugins, Connectors or Tools opens on Installed instead of the catalog.',
      checked: draft.alwaysShowInstalled,
      onChange: value => update({ alwaysShowInstalled: Boolean(value) })
    }),
    jsx(KindOrderControl, {
      draft,
      onChange: next => {
        update({ kindOrder: next })
        onOrderChange?.(next)
      }
    }),
    el(
      'div',
      { style: { display: 'flex', justifyContent: 'flex-end', paddingTop: 8 } },
      jsx(Button, { size: 'xs', variant: 'ghost', onClick: onClose, children: 'Done' })
    )
  )
}

function SettingsPage() {
  const [draft, setDraft] = useState(settings)

  return el(
    'div',
    { style: { padding: '18px 20px', maxWidth: 620, display: 'flex', flexDirection: 'column', gap: 4 } },
    jsx('h2', { style: { margin: '0 0 6px', fontSize: 15, color: C.text, fontWeight: 600 }, children: 'Catalog Redesign' }),
    jsx('p', {
      style: { margin: '0 0 10px', fontSize: 12, color: C.text3, lineHeight: 1.6 },
      children: 'Settings for the catalog page. They are stored with the plugin, so they follow this window.'
    }),
    jsx(ToggleRow, {
      label: 'Always show installed',
      description: 'Entering Skills, Plugins, Connectors or Tools opens on Installed instead of the catalog.',
      checked: draft.alwaysShowInstalled,
      onChange: value => {
        setDraft({ ...draft, alwaysShowInstalled: Boolean(value) })
        persistSettings({ alwaysShowInstalled: Boolean(value) })
      }
    }),
    jsx(KindOrderControl, {
      draft,
      onChange: next => {
        setDraft({ ...draft, kindOrder: next })
        persistSettings({ kindOrder: next })
      }
    }),
  )
}

/* ------------------------------------------------------------------- page */

const KINDS = [
  { id: 'plugins', label: 'Plugins' },
  { id: 'skills', label: 'Skills' },
  { id: 'connectors', label: 'Connectors' },
  { id: 'tools', label: 'Tools' }
]

const PLACEHOLDER = {
  plugins: 'Search plugins, categories, tools',
  skills: 'Search skills',
  connectors: 'Search connectors, transports',
  tools: 'Search toolsets and tool names'
}

export function CatalogPage() {
  const profile = useAtomValue(host.state.profile) || 'default'
  const [kind, setKind] = useState('plugins')
  const [filter, setFilter] = useState(settings.alwaysShowInstalled ? 'installed' : 'catalog')
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [items, setItems] = useState([])
  const [page, setPage] = useState(1)
  const [pageInfo, setPageInfo] = useState({ totalPages: null, total: null })
  const [selected, setSelected] = useState(null)
  const [hover, setHover] = useState(null)
  const [limit, setLimit] = useState(PAGE_SIZE)
  const [settingsOpen, setSettingsOpen] = useState(false)
  // The order lives in state as well as storage: the header reads it on every
  // render, and a module variable alone would leave it stale until a remount.
  const [kindOrder, setKindOrder] = useState(() => normalizeOrder(settings.kindOrder))
  const [pending, setPending] = useState({})
  // The counts read module-level caches. Something has to re-render when one of
  // those caches fills, or the subtitle keeps reporting the number it saw first.
  const [countsTick, setCountsTick] = useState(0)
  const [reloadKey, setReloadKey] = useState(0)
  const hoverTimer = useRef(null)
  const sentinelRef = useRef(null)

  // Tools have no public catalog: the filter is a no-op there and the page
  // says so by hiding it rather than offering a dead segment.
  const effectiveFilter = kind === 'tools' ? 'installed' : filter

  // The filter the setting prescribes is applied on entry, not only at mount:
  // switching kinds is "entering" that catalog again.
  useEffect(() => {
    setFilter(settings.alwaysShowInstalled || kind === 'tools' ? 'installed' : 'catalog')
  }, [kind])

  useEffect(() => {
    let alive = true

    setLoading(true)
    setError('')

    // Warm the other doors before the visible load rather than after it: a door
    // that fails returns from the catch, and warming from there meant the
    // catalog tab waited for a request nobody had started.
    void warm(profile, kind, effectiveFilter, () => {
      if (alive) {
        setCountsTick(tick => tick + 1)
      }
    })

    const run = async () => {
      try {
        if (kind === 'plugins') {
          const painted = cache.installed?.length ? cache.installed : null

          if (painted) {
            setItems(painted.map(installedPluginItem))
            setPageInfo({ totalPages: null, total: painted.length })
            setLoading(false)
          }

          let installed = cache.installed || []

          try {
            const quick = await loadInstalledPluginsQuick(profile)

            if (alive && quick.length) {
              setItems(quick.map(installedPluginItem))
              setPageInfo({ totalPages: null, total: quick.length })
              setLoading(false)
            }
            // Artwork the plugin folders carry arrives separately: rows painted
            // with initials pick up their own image when it lands.
            void warmOnce('plugin-icons', () => loadPluginIcons())
              .then(() => {
                if (!alive) {
                  return
                }

                setItems(rows =>
                  rows.map(row => {
                    if (row.hero || row.kind !== 'plugin') {
                      return row
                    }

                    const icon =
                      cache.icons?.get(shortName(row.name)) || cache.icons?.get(shortName(row.key))

                    return icon ? { ...row, hero: icon } : row
                  })
                )
                setCountsTick(tick => tick + 1)
              })
              .catch(() => null)

            if (effectiveFilter === 'installed') {
              if (effectiveFilter === 'installed') {
              installed = await loadInstalledPlugins(profile, reloadKey > 0)
            } else {
              installed = cache.installed || []
              void loadInstalledPlugins(profile, reloadKey > 0).then(r => { cache.installed = r; cache.installedAt = Date.now() }).catch(() => {})
            }
            } else {
              installed = cache.installed || []
              void loadInstalledPlugins(profile, reloadKey > 0).then(r => { cache.installed = r; cache.installedAt = Date.now() }).catch(() => {})
            }
          } catch (err) {
            // The fast list is a real answer even when the detail scan does not
            // finish: keep it on screen and say so in the console instead of
            // replacing a working list with an error.
            if (effectiveFilter === 'installed' && (cache.quickInstalled?.length || cache.installed?.length)) {
              console.error(
                '[catalog] plugin list scan failed, keeping what is painted:',
                String(err?.message || err)
              )
              return
            }

            if (effectiveFilter !== 'installed') {
              console.error('[catalog] installed scan failed, proceeding with catalog:', String(err?.message || err))
            } else {
              throw err
            }
          }

          if (!alive) {
            return
          }

          if (effectiveFilter === 'installed') {
            const localRows = installed.map(installedPluginItem)

            setItems(localRows)
            setPageInfo({ totalPages: null, total: installed.length })

            // The backend row says what is installed, not what it looks like.
            // Enrich after paint from the catalog cache so an installed row
            // still carries its hero image, category and install command; a
            // catalog fetch that fails leaves the plain rows in place.
            // Shares the prefetch's single request instead of fetching the 5MB
            // feed a second time on the same mount.
            void warmOnce('catalog-plugins', () => loadCatalogPlugins())
              .then(catalog => {
                if (!alive) {
                  return
                }

                const byKey = new Map(catalog.map(catalogItem).map(entry => [entry.key, entry]))

                setItems(
                  localRows.map(row => {
                    const match = byKey.get(row.catalogKey || row.short)

                    return match
                      ? {
                          ...row,
                          hero: match.hero,
                          screenshots: match.screenshots,
                          category: match.category,
                          description: row.description || match.description,
                          tier: match.tier || row.tier,
                          stars: match.stars,
                          requiresHermes: match.requiresHermes,
                          installCommand: match.installCommand,
                          docsUrl: match.docsUrl,
                          repo: row.repo || match.repo,
                          updatedAt: match.updatedAt,
                          short: match.short || row.short
                        }
                      : row
                  })
                )
              })
              .catch(() => {})
          } else {
            const first = page <= 1
            const result = await loadCatalogPage('plugins', {
              page,
              query: query.trim(),
              force: reloadKey > 0 && first
            })

            if (!alive) {
              return
            }

            const merged = annotateCatalog(result.rows.map(catalogItem), installed.map(installedPluginItem))

            setItems(previous => (first ? merged : mergeRows(previous, merged)))
            setPageInfo({ totalPages: result.totalPages, total: result.total })
            cache.catalogTotal = result.total

            if (first) {
              cache.catalog = result.rows
              cache.catalogAt = Date.now()
              cache.catalogError = result.error
            }
          }
        } else if (kind === 'skills') {
          if (effectiveFilter === 'installed') {
            const skills = await loadInstalledSkills(profile, reloadKey > 0)

            if (!alive) {
              return
            }

            setItems(skills.map(skillItem))
            setPageInfo({ totalPages: null, total: skills.length })
          } else if (effectiveFilter === 'archive') {
            const archived = await loadArchivedSkills(reloadKey > 0)

            if (!alive) {
              return
            }

            setItems(archived.map(archivedSkillItem))
            setPageInfo({ totalPages: null, total: archived.length })
          } else {
            const first = page <= 1
            const result = await loadCatalogPage('skills', {
              page,
              query: query.trim(),
              force: reloadKey > 0 && first
            })

            if (!alive) {
              return
            }

            const mapped = result.rows.map(catalogSkillItem)

            setItems(previous => (first ? mapped : mergeRows(previous, mapped)))
            setPageInfo({ totalPages: result.totalPages, total: result.total })
            cache.skillsCatalogTotal = result.total

            if (first) {
              cache.skillsCatalog = result.rows
              cache.skillsCatalogAt = Date.now()
            }
          }
        } else if (kind === 'connectors') {
          if (effectiveFilter === 'installed') {
            const servers = await loadServers(profile, reloadKey > 0)

            if (!alive) {
              return
            }

            setItems(servers.map(serverItem))
            setPageInfo({ totalPages: null, total: servers.length })
          } else {
            const presets = await loadMcpCatalog(profile, reloadKey > 0)

            if (!alive) {
              return
            }

            setItems(presets.map(mcpCatalogItem))
            setPageInfo({ totalPages: null, total: presets.length })
          }
        } else {
          const toolsets = await loadToolsets(profile, reloadKey > 0)

          if (!alive) {
            return
          }

          setItems(toolsets.map(toolsetItem))
          setPageInfo({ totalPages: null, total: toolsets.length })
        }

        if (alive) {
          setLoading(false)
        }

      } catch (err) {
        if (!alive) {
          return
        }

        const message = String(err?.message || err || 'Could not load this catalog')

        try {
          console.error(`[catalog] ${kind}/${effectiveFilter} failed:`, message, err?.stack || '')
        } catch {
          // console is best-effort
        }

        setItems([])
        setError(message)
        setLoading(false)
        // A failed door still lets the rest warm, so one broken tab does not
        // hold every other tab hostage.
        void warm(profile, kind, effectiveFilter)
      }
    }

    const cancelRun = later(
      () => void run(),
      query && kind === 'skills' && effectiveFilter === 'catalog' ? 280 : 0
    )

    return () => {
      alive = false
      cancelRun()
    }
  }, [kind, effectiveFilter, query, page, profile, reloadKey])

  useEffect(() => {
    setLimit(PAGE_SIZE)
    setPage(1)
  }, [kind, effectiveFilter, query])

  useEffect(() => () => hoverTimer.current?.(), [])

  // Escape closes the panel first, then the settings card.
  useEffect(() => {
    const onKey = event => {
      if (event.key !== 'Escape') {
        return
      }

      if (settingsOpen) {
        setSettingsOpen(false)
        return
      }

      if (closePanel) {
        event.stopPropagation()
        closePanel()
      }
    }

    return ctxRef?.addEventListener?.(window, 'keydown', onKey, true)
  }, [settingsOpen])

  // A catalog kind is paged by the gateway: the query and the ranking already
  // ran over the whole snapshot, so the page neither re-filters nor re-sorts,
  // and the rows on screen are exactly the page it asked for.
  const isPaged = effectiveFilter === 'catalog' && (kind === 'plugins' || kind === 'skills')

  const filtered = useMemo(() => {
    if (isPaged) {
      return items
    }

    return items.filter(item => matches(item, query.trim()))
  }, [items, isPaged, query])

  const visible = isPaged ? filtered : filtered.slice(0, limit)
  const pagesLeft = Boolean(pageInfo.totalPages) && page < pageInfo.totalPages
  const hasMore = isPaged ? pagesLeft : filtered.length > visible.length

  const counts = useMemo(
    () => ({
      // The rows are painted from the fast list, so the count has to read the
      // same list: counting only the 75s detail scan left the header at zero
      // while the rows were already on screen.
      plugins: cache.quickInstalled?.length ?? cache.installed?.length ?? 0,
      // The total the gateway reports for the snapshot, not the number of rows it
      // happened to send: page one is 150 of 2,380 and the header says which.
      pluginsCatalog: cache.catalogTotal || (cache.catalog?.length ?? 0),
      skills: cache.skills?.length ?? 0,
      archived: cache.archived?.length ?? 0,
      skillsCatalog: cache.skillsCatalogTotal ?? 0,
      connectors: cache.servers?.length ?? 0,
      connectorPresets: cache.mcpCatalog?.length ?? 0,
      tools: cache.toolsets?.length ?? 0
    }),
    [items, loading, reloadKey, countsTick]
  )

  const n = value => Number(value || 0).toLocaleString()

  const subtitle = {
    plugins: `${n(counts.plugins)} installed · ${n(counts.pluginsCatalog)} in the catalog`,
    skills: `${n(counts.skills)} installed · ${n(counts.archived)} archived · ${n(counts.skillsCatalog)} in the catalog`,
    connectors: `${counts.connectors} configured · ${counts.connectorPresets} presets`,
    tools: `${counts.tools} toolsets`
  }[kind]

  const onHover = useCallback((item, event) => {
    const x = event?.clientX ?? 0
    const y = event?.clientY ?? 0
    const target = event?.currentTarget
    const rect = target && typeof target.getBoundingClientRect === 'function' ? target.getBoundingClientRect() : null

    hoverTimer.current?.()
    hoverTimer.current = later(() => setHover({ item, rect, x, y }), HOVER_DELAY)
  }, [])

  const loadMore = useCallback(() => {
    if (loading) {
      return
    }

    if (isPaged) {
      if (pagesLeft) {
        setPage(value => value + 1)
      }

      return
    }

    setLimit(value => value + PAGE_SIZE)
  }, [loading, isPaged, pagesLeft])

  // Reaching the end of the list fetches the next page by itself: a catalog of
  // 104k rows is not something a reader should have to click through.
  useEffect(() => {
    const node = sentinelRef.current

    if (!isPaged || !hasMore || !node || typeof IntersectionObserver === 'undefined') {
      return undefined
    }

    const observer = new IntersectionObserver(
      entries => {
        if (entries.some(entry => entry.isIntersecting)) {
          loadMore()
        }
      },
      { rootMargin: '600px 0px' }
    )

    observer.observe(node)

    return () => observer.disconnect()
  }, [isPaged, hasMore, loadMore, visible.length, pageInfo.totalPages])

  const onHoverEnd = useCallback(() => {
    hoverTimer.current?.()
    hoverTimer.current = null
    setHover(null)
  }, [])

  /** The switch is the plugins tab's enable bit, so it goes through the same
   *  `plugins.manage toggle` the native page uses. The row flips at once and
   *  flips back if the backend refuses, because a switch that lies about the
   *  backend state is worse than one that lags. */
  const togglePlugin = useCallback(
    async (item, enable) => {
      setItems(rows => rows.map(row => (row.uid === item.uid ? { ...row, enabled: enable } : row)))
      setPending(state => ({ ...state, [item.key]: true }))

      try {
        const result = await ask(
          'plugins.manage',
          { action: 'toggle', key: item.key, enable, ...scopeParam(profile) },
          RPC_MS,
          'plugins.manage'
        )

        if (result && result.ok === false) {
          throw new Error(result.error || 'The backend refused the change.')
        }

        if (Array.isArray(cache.installed)) {
          cache.installed = cache.installed.map(row =>
            str(row.key) === item.key || str(row.name) === item.key
              ? { ...row, status: enable ? 'enabled' : 'disabled' }
              : row
          )
        }

        setSelected(current => (current?.uid === item.uid ? { ...current, enabled: enable } : current))
      } catch (err) {
        setItems(rows => rows.map(row => (row.uid === item.uid ? { ...row, enabled: !enable } : row)))
        console.error('[catalog] toggle failed:', item.key, String(err?.message || err))
      } finally {
        setPending(state => {
          const next = { ...state }

          delete next[item.key]

          return next
        })
      }
    },
    [profile]
  )

  /** Optimistic flip for a row whose backend door is not plugins.manage: the
   *  row changes at once and changes back if the call fails. */
  const flipRow = useCallback(async (item, enable, work, label) => {
    setItems(rows => rows.map(row => (row.uid === item.uid ? { ...row, enabled: enable } : row)))
    setPending(state => ({ ...state, [item.key]: true }))

    try {
      await work()
      setSelected(current => (current?.uid === item.uid ? { ...current, enabled: enable } : current))
    } catch (err) {
      setItems(rows => rows.map(row => (row.uid === item.uid ? { ...row, enabled: !enable } : row)))
      console.error(`[catalog] ${label} toggle failed:`, item.key, String(err?.message || err))
    } finally {
      setPending(state => {
        const next = { ...state }

        delete next[item.key]

        return next
      })
    }
  }, [])

  const scopedProfile = profile && profile !== 'default' ? profile : undefined

  /** One switch, three doors: plugins and toolsets have SDK calls, connectors go
   *  through this plugin's own Python half because MCP has no JSON-RPC toggle. */
  const toggleRow = useCallback(
    (item, enable) => {
      if (item.kind === 'plugin') {
        return togglePlugin(item, enable)
      }

      if (item.kind === 'tool') {
        return flipRow(
          item,
          enable,
          async () => {
            await host.toolsets.setEnabled(item.key, enable, scopedProfile)

            if (Array.isArray(cache.toolsets)) {
              cache.toolsets = cache.toolsets.map(row =>
                str(row.name) === item.key ? { ...row, enabled: enable } : row
              )
            }
          },
          'toolset'
        )
      }

      if (item.kind === 'skill') {
        const folder = item.folder || item.key

        // Archiving is a move out of skills/, so the pair of calls is a pair of
        // moves: off sends the folder to .archive, on brings it back. A skill
        // that is installed but disabled by config is re-enabled instead, since
        // archiving it is not what that switch asked for.
        if (item.origin === 'archive') {
          return flipRow(
            item,
            enable,
            async () => {
              await ctxRef.rest('/skills/archive/restore', { method: 'POST', body: { folder } })

              cache.archived = null
              cache.archivedAt = 0
              cache.skills = null
              cache.skillsAt = 0
            },
            'skill'
          )
        }

        if (enable && !item.enabled) {
          return flipRow(item, enable, () => host.skills.setEnabled(item.name, true, scopedProfile), 'skill')
        }

        return flipRow(
          item,
          enable,
          async () => {
            await ctxRef.rest('/skills/archive/add', { method: 'POST', body: { name: folder } })

            cache.skills = null
            cache.skillsAt = 0
            cache.archived = null
            cache.archivedAt = 0
          },
          'skill'
        )
      }

      if (item.kind === 'connector') {
        return flipRow(
          item,
          enable,
          () =>
            ctxRef.rest('/servers/toggle', {
              method: 'POST',
              body: { name: item.key, enabled: enable, ...(scopedProfile ? { profile: scopedProfile } : {}) }
            }),
          'connector'
        )
      }

      return null
    },
    [flipRow, scopedProfile, togglePlugin]
  )

  const openRow = item => {
    setHover(null)
    setSelected(item)
  }

  const reload = () => {
    cache.installedAt = 0
    cache.skillsAt = 0
    cache.catalogAt = 0
    cache.toolsetsAt = 0
    cache.serversAt = 0
    cache.mcpCatalogAt = 0
    setReloadKey(key => key + 1)
  }

  const filterOptions = [
    {
      id: 'installed',
      label: `Installed ${Number(
        kind === 'plugins'
          ? counts.plugins
          : kind === 'skills'
            ? counts.skills
            : kind === 'connectors'
              ? counts.connectors
              : counts.tools
      ).toLocaleString()}`
    },
    // Skills carry a third state: the curator moves an unused skill into
    // skills/.archive rather than deleting it, so it is neither installed
    // (it does not load) nor absent (it is one move from coming back).
    kind === 'skills'
      ? {
          id: 'archive',
          label: `Archive ${Number(counts.archived).toLocaleString()}`
        }
      : null,
    {
      id: 'catalog',
      label: `Catalog ${Number(
        kind === 'plugins'
          ? counts.pluginsCatalog
          : kind === 'skills'
            ? counts.skillsCatalog
            : counts.connectorPresets || 0
      ).toLocaleString()}`
    }
  ].filter(Boolean)

  return el(
    'div',
    {
      style: {
        position: 'relative',
        height: '100%',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        background: C.surface,
        overflow: 'hidden'
      }
    },
    el(
      'header',
      {
        style: {
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '12px 16px',
          borderBottom: `1px solid ${C.stroke}`,
          flex: '0 0 auto'
        }
      },
      // Three zones, with the title and the tools sharing the leftover space
      // evenly. The selectors therefore sit at the header's centre and stay
      // there when the subtitle changes length.
      el(
        'div',
        {
          key: 'title',
          style: {
            flex: '1 1 0',
            minWidth: 0,
            display: 'flex',
            alignItems: 'baseline',
            gap: 8,
            overflow: 'hidden'
          }
        },
        jsx('span', {
          style: { fontSize: 13.5, fontWeight: 600, color: C.text, letterSpacing: '-0.01em', flex: '0 0 auto' },
          children: 'Catalog'
        }),
        (kind === 'skills' || (kind === 'plugins' && (cache.installed || []).some(r => r.updateAvailable))) &&
          jsx('button', {
            type: 'button',
            style: { fontSize: 11, padding: '2px 8px', borderRadius: 6, border: `1px solid ${C.stroke}`, background: 'transparent', color: C.text, cursor: 'pointer', flex: '0 0 auto' },
            onClick: () => setReloadKey(k => k + 1),
            children: 'Update all'
          }),
        jsx('span', {
          style: {
            fontSize: 11,
            color: C.text4,
            minWidth: 0,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          },
          children: subtitle
        })
      ),
      el(
        'div',
        {
          key: 'selectors',
          style: { flex: '0 0 auto', display: 'flex', alignItems: 'center', gap: 10 }
        },
        jsx(SegmentedControl, {
          options: orderedKinds(kindOrder),
          value: kind,
          onChange: next => setKind(next),
          sizing: 'content'
        }),
        kind === 'tools'
          ? null
          : jsx('span', {
              key: 'divider',
              'aria-hidden': true,
              style: { width: 1, height: 18, background: C.stroke, margin: '0 2px', flex: '0 0 auto' }
            }),
        kind === 'tools'
          ? null
          : jsx(SegmentedControl, {
              key: 'filter',
              options: filterOptions,
              value: filter,
              onChange: next => setFilter(next),
              sizing: 'content'
            })
      ),
      el(
        'div',
        {
          key: 'tools',
          style: {
            flex: '1 1 0',
            minWidth: 0,
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: 6
          }
        },
        el(
          'div',
          { style: { width: 'clamp(150px, 19vw, 220px)', minWidth: 0, display: 'flex' } },
          jsx(SearchField, {
            placeholder: PLACEHOLDER[kind],
            value: query,
            onChange: setQuery,
            onClear: () => setQuery(''),
            loading,
            variant: 'underline',
            'aria-label': 'Search the catalog'
          })
        ),
        jsx(Tip, {
          label: 'Refresh',
          children: jsx(Button, {
            size: 'icon',
            variant: 'ghost',
            'aria-label': 'Refresh catalog',
            onClick: reload,
            children: jsx(Codicon, { name: 'refresh', size: '0.9rem' })
          })
        }),
        jsx(Button, {
          size: 'icon',
          variant: 'ghost',
          'aria-label': 'Page settings',
          onClick: () => setSettingsOpen(open => !open),
          children: jsx(Codicon, { name: 'settings-gear', size: '0.9rem' })
        })
      )
    ),
    settingsOpen
      ? jsx(SettingsCard, {
          onClose: () => setSettingsOpen(false),
          onOrderChange: next => setKindOrder(next)
        })
      : null,
    el(
      'div',
      { style: { position: 'relative', flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' } },
      // The column header lives INSIDE the panel's positioning context, so an
      // open panel covers the tag column it no longer shows instead of leaving
      // a header floating over the panel.
      el(
        'div',
        {
          style: {
            display: 'grid',
            gridTemplateColumns: layoutFor({ kind, origin: 'installed' }).columns,
            gap: 14,
            padding: '9px 14px 7px',
            borderBottom: `1px solid ${C.stroke}`,
            fontSize: 9.5,
            letterSpacing: '0.11em',
            textTransform: 'uppercase',
            color: C.text3,
            flex: '0 0 auto'
          }
        },
        jsx('span', { children: '' }),
        jsx('span', { children: 'Name' }),
        // One column heading for all four kinds: what sits there is a tag,
        // whether it is the normalized short name or the item's own tags.
        jsx('span', { children: 'Tags' }),
        layoutFor({ kind, origin: 'installed' }).switchable ? jsx('span', { children: '' }) : null
      ),
      el(
      'div',
      { style: { position: 'relative', flex: 1, minHeight: 0 } },
      jsx(ScrollArea, {
        style: { height: '100%' },
        children: el(
          'div',
          { style: { padding: '6px 8px 24px', display: 'flex', flexDirection: 'column', gap: 2 } },
          loading && !visible.length
            ? el(
                'div',
                { style: { display: 'grid', placeItems: 'center', gap: 8, padding: '48px 0' } },
                jsx(Loader, { label: 'Loading' }),
                kind === 'plugins' && effectiveFilter === 'installed'
                  ? jsx('div', {
                      style: { fontSize: 11.5, color: C.text3 },
                      children: 'Scanning the installed plugins. This reads every manifest on disk, which can take a minute on the first open.'
                    })
                  : null
              )
            : null,
          error
            ? el(
                'div',
                { style: { padding: 18, fontSize: 12, color: 'var(--ui-red)', lineHeight: 1.6 } },
                error,
                jsx('div', {
                  style: { marginTop: 8, color: C.text3 },
                  children:
                    effectiveFilter === 'catalog' && kind !== 'plugins'
                      ? 'The catalog behind this kind is a network surface; installed entries still work offline.'
                      : 'Check the network, then use Refresh.'
                })
              )
            : null,
          !loading && !error && !filtered.length
            ? jsx(EmptyState, {
                title: 'Nothing matches this filter',
                description:
                  kind === 'connectors' && effectiveFilter === 'installed'
                    ? 'No MCP servers are configured for this profile yet.'
                    : kind === 'tools'
                      ? 'No toolsets reported for this profile.'
                      : 'Try a shorter search, or switch to the other filter.'
              })
            : null,
          visible.map(item =>
            jsx(Row, {
              key: item.uid,
              item,
              selected: selected?.uid === item.uid,
              pending: Boolean(pending[item.key]),
              onOpen: openRow,
              onHover,
              onHoverEnd,
              onToggle: toggleRow
            })
          ),
          el('div', { key: 'sentinel', ref: sentinelRef, style: { height: 1 } }),
          hasMore
            ? el(
                'div',
                { style: { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, padding: '14px 0 20px' } },
                jsx(Button, {
                  size: 'sm',
                  variant: 'outline',
                  loading,
                  onClick: loadMore,
                  children: isPaged
                    ? `Load more of ${(pageInfo.total || 0).toLocaleString()}`
                    : `Show ${Math.min(PAGE_SIZE, filtered.length - visible.length)} more of ${filtered.length}`
                }),
                isPaged && pageInfo.total
                  ? jsx('span', {
                      style: { fontSize: 10.5, color: C.text4 },
                      children: `${visible.length.toLocaleString()} of ${pageInfo.total.toLocaleString()} rows read`
                    })
                  : null
              )
            : null
        )
      })
      ),
      selected
        ? jsx(DetailPanel, {
            key: selected.uid,
            item: selected,
            profile,
            onClose: () => setSelected(null),
            onChanged: reload,
            onToggle: toggleRow
          })
        : null
    ),
    hover && !selected ? jsx(HoverCard, { hover }) : null
  )
}

/* -------------------------------------------------------------- register */

/** A route that throws is replaced by the app's error boundary, which says
 *  nothing useful in a log. This one keeps the message on screen. */
class PageBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // The app's boundary swallows the message; this lands in desktop.log so the
    // next failure is diagnosable without a debugger.
    try {
      console.error('[catalog] render failed:', String(error?.stack || error), info?.componentStack || '')
    } catch {
      // console is best-effort
    }
  }

  render() {
    if (this.state.error) {
      return el(
        'div',
        { style: { padding: '16px 18px', height: '100%', overflow: 'auto' } },
        jsx('div', {
          style: { fontSize: 13, fontWeight: 600, color: 'var(--ui-red)' },
          children: 'Catalog Redesign could not render'
        }),
        jsx('pre', {
          style: {
            marginTop: 10,
            whiteSpace: 'pre-wrap',
            fontSize: 11,
            lineHeight: 1.5,
            color: C.text2,
            fontFamily: MONO
          },
          children: String(this.state.error?.stack || this.state.error)
        })
      )
    }

    return this.props.children
  }
}

function pageShell() {
  return jsx(PageBoundary, { children: jsx(CatalogPage, {}) })
}

export default {
  id: ID,
  name: 'Catalog Redesign',
  description: 'Wide one-row-per-item catalog for skills, plugins, connectors and tools, with hover previews and a sliding detail panel.',
  defaultEnabled: true,
  register(ctx) {
    ctxRef = ctx
    savedSettings()

    try {
      const snapshot = ctx.storage?.get?.(INSTALLED_SNAPSHOT_KEY)

      if (Array.isArray(snapshot?.rows) && snapshot.rows.length) {
        // Paint the last scan now, refresh it behind the paint.
        cache.installed = snapshot.rows
        cache.installedAt = 0
      }
    } catch {
      // No snapshot: the first open pays for the scan.
    }

    ctx.register({
      id: 'route-catalog',
      area: ROUTES_AREA,
      data: { path: ROUTE },
      render: pageShell
    })
    ctx.register({
      id: 'nav-catalog',
      area: SIDEBAR_NAV_AREA,
      order: 10,
      data: { path: ROUTE, label: 'Catalog', codicon: 'library' }
    })
    ctx.register({
      id: 'palette-catalog',
      area: PALETTE_AREA,
      data: {
        id: `${ID}.open`,
        label: 'Catalog: Open Catalog',
        keywords: ['catalog', 'plugins', 'skills', 'capabilities', 'install'],
        run: () => host.navigate(ROUTE)
      }
    })

    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({
        id: 'hermes-catalog-redesign',
        title: 'Catalog Redesign',
        icon: 'library',
        order: 41,
        render: () => jsx(SettingsPage, {})
      })
    }
  }
}
