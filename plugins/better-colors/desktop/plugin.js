/**
 * Better Colors for Hermes.
 *
 * Paints the whole session name with the Appearance color (lightness
 * flipped for the current mode). Bold is optional. Appearance submenu
 * gets a glyph gallery that replaces the idle bullet.
 *
 * Live door: desktop-plugins/better-colors/plugin.js (auto-on).
 */

const ID = 'better-colors'
const ROW = '[data-sessions-mode] .row-hover'
const TITLE = '.hover-marquee'
const IDLE_DOT = 'span.size-1.rounded-full'
const EXTRA_ATTR = 'data-better-colors'
const STYLE_ID = 'better-colors-style'

const GLYPH_NAMES = [
  "account", "activate-breakpoints", "add-small", "add", "agent", "archive",
  "arrow-both", "arrow-circle-down", "arrow-circle-left", "arrow-circle-right", "arrow-circle-up", "arrow-down",
  "arrow-left", "arrow-right", "arrow-small-down", "arrow-small-left", "arrow-small-right", "arrow-small-up",
  "arrow-swap", "arrow-up", "ask", "attach", "azure-devops", "azure",
  "beaker-stop", "beaker", "bell-dot", "bell-slash-dot", "bell-slash", "bell",
  "blank", "bold", "book", "bookmark", "bracket-dot", "bracket-error",
  "briefcase", "broadcast", "browser", "bug", "build", "calendar",
  "call-incoming", "call-outgoing", "case-sensitive", "chat-sparkle-error", "chat-sparkle-warning", "chat-sparkle",
  "check-all", "check", "checklist", "chevron-down", "chevron-left", "chevron-right",
  "chevron-up", "chip", "chrome-close", "chrome-maximize", "chrome-minimize", "chrome-restore",
  "circle-filled", "circle-large-filled", "circle-large", "circle-slash", "circle-small-filled", "circle-small",
  "circle", "circuit-board", "claude", "clear-all", "clippy", "clockface",
  "close-all", "close", "cloud-download", "cloud-small", "cloud-upload", "cloud",
  "code-oss", "code-review", "code", "coffee", "collapse-all", "collection-small",
  "collection", "color-mode", "combine", "comment-discussion-quote", "comment-discussion-sparkle", "comment-discussion",
  "comment-draft", "comment-unresolved", "comment", "compass-active", "compass-dot", "compass",
  "copilot-blocked", "copilot-error", "copilot-in-progress", "copilot-large", "copilot-not-connected", "copilot-snooze",
  "copilot-success", "copilot-unavailable", "copilot-warning-large", "copilot-warning", "copilot", "copy",
  "coverage", "credit-card", "cursor", "dash", "dashboard", "database",
  "debug-all", "debug-alt-small", "debug-alt", "debug-breakpoint-conditional-unverified", "debug-breakpoint-conditional", "debug-breakpoint-data-unverified",
  "debug-breakpoint-data", "debug-breakpoint-function-unverified", "debug-breakpoint-function", "debug-breakpoint-log-unverified", "debug-breakpoint-log", "debug-breakpoint-unsupported",
  "debug-connected", "debug-console", "debug-continue-small", "debug-continue", "debug-coverage", "debug-disconnect",
  "debug-line-by-line", "debug-pause", "debug-rerun", "debug-restart-frame", "debug-restart", "debug-reverse-continue",
  "debug-stackframe-active", "debug-stackframe", "debug-start", "debug-step-back", "debug-step-into", "debug-step-out",
  "debug-step-over", "debug-stop", "debug", "desktop-download", "device-camera-video", "device-camera",
  "device-mobile", "diff-added", "diff-ignored", "diff-modified", "diff-multiple", "diff-removed",
  "diff-renamed", "diff-single", "diff", "discard", "download", "edit-code",
  "edit-session", "edit-sparkle", "edit", "editor-layout", "ellipsis", "empty-window",
  "eraser", "error-small", "error", "exclude", "expand-all", "export",
  "extensions-large", "extensions", "eye-closed", "eye", "feedback", "file-binary",
  "file-code", "file-media", "file-pdf", "file-submodule", "file-symlink-directory", "file-symlink-file",
  "file-text", "file-zip", "file", "files", "filter-filled", "filter",
  "flag", "flame", "fold-down", "fold-up", "fold", "folder-active",
  "folder-library", "folder-opened", "folder", "forward", "game", "gear",
  "gift", "gist-secret", "gist", "git-branch-changes", "git-branch-conflicts", "git-branch-staged-changes",
  "git-branch", "git-commit", "git-compare", "git-fetch", "git-merge", "git-pull-request-closed",
  "git-pull-request-create", "git-pull-request-done", "git-pull-request-draft", "git-pull-request-go-to-changes", "git-pull-request-new-changes", "git-pull-request",
  "git-stash-apply", "git-stash-pop", "git-stash", "github-action", "github-alt", "github-inverted",
  "github-project", "github", "globe", "go-to-editing-session", "go-to-file", "go-to-search",
  "grabber", "graph-left", "graph-line", "graph-scatter", "graph", "gripper",
  "group-by-ref-type", "heart-filled", "heart", "history", "home", "horizontal-rule",
  "hubot", "inbox", "indent", "index-zero", "info", "insert",
  "inspect", "issue-draft", "issue-reopened", "issues", "italic", "jersey",
  "json", "kebab-vertical", "key", "keyboard-tab-above", "keyboard-tab-below", "keyboard-tab",
  "law", "layers-active", "layers-dot", "layers", "layout-activitybar-left", "layout-activitybar-right",
  "layout-centered", "layout-menubar", "layout-panel-center", "layout-panel-dock", "layout-panel-justify", "layout-panel-left",
  "layout-panel-off", "layout-panel-right", "layout-panel", "layout-sidebar-left-dock", "layout-sidebar-left-off", "layout-sidebar-left",
  "layout-sidebar-right-dock", "layout-sidebar-right-off", "layout-sidebar-right", "layout-statusbar", "layout", "library",
  "lightbulb-autofix", "lightbulb-empty", "lightbulb-sparkle", "lightbulb", "link-external", "link",
  "list-filter", "list-flat", "list-ordered", "list-selection", "list-tree", "list-unordered",
  "live-share", "loading", "location", "lock-small", "lock", "magnet",
  "mail-read", "mail", "map-filled", "map-vertical-filled", "map-vertical", "map",
  "markdown", "mcp", "megaphone", "mention", "menu", "merge-into",
  "merge", "mic-filled", "mic", "milestone", "mirror", "mortar-board",
  "move", "multiple-windows", "music", "mute", "new-collection", "new-file",
  "new-folder", "new-session", "newline", "no-newline", "note", "notebook-template",
  "notebook", "octoface", "open-in-product", "open-in-window", "open-preview", "openai",
  "organization", "output", "package", "paintcan", "pass-filled", "pass",
  "percentage", "person-add", "person", "piano", "pie-chart", "pin",
  "pinned-dirty", "pinned", "play-circle", "play", "plug", "preserve-case",
  "preview", "primitive-square", "project", "pulse", "python", "question",
  "quote", "quotes", "radio-tower", "reactions", "record-keys", "record-small",
  "record", "redo", "references", "refresh", "regex", "remote-explorer",
  "remote", "remove-small", "remove", "rename", "replace-all", "replace",
  "reply", "repo-clone", "repo-fetch", "repo-force-push", "repo-forked", "repo-pinned",
  "repo-pull", "repo-push", "repo-selected", "repo", "report", "robot",
  "rocket", "root-folder-opened", "root-folder", "rss", "ruby", "run-above",
  "run-all-coverage", "run-all", "run-below", "run-coverage", "run-errors", "run-with-deps",
  "save-all", "save-as", "save", "screen-cut", "screen-full", "screen-normal",
  "search-fuzzy", "search-large", "search-sparkle", "search-stop", "search", "send-to-remote-agent",
  "send", "server-environment", "server-process", "server", "session-in-progress", "settings-gear",
  "settings", "share", "shield", "sign-in", "sign-out", "skip",
  "smiley", "snake", "sort-precedence", "sparkle-filled", "sparkle", "split-horizontal",
  "split-vertical", "squirrel", "star-empty", "star-full", "star-half", "stop-circle",
  "strikethrough", "surround-with", "symbol-array", "symbol-boolean", "symbol-class", "symbol-color",
  "symbol-constant", "symbol-enum-member", "symbol-enum", "symbol-event", "symbol-field", "symbol-interface",
  "symbol-key", "symbol-keyword", "symbol-method-arrow", "symbol-method", "symbol-misc", "symbol-numeric",
  "symbol-operator", "symbol-parameter", "symbol-property", "symbol-ruler", "symbol-snippet", "symbol-structure",
  "symbol-variable", "sync-ignored", "sync", "table", "tag", "target",
  "tasklist", "telescope", "terminal-bash", "terminal-cmd", "terminal-debian", "terminal-git-bash",
  "terminal-linux", "terminal-powershell", "terminal-tmux", "terminal-ubuntu", "terminal", "text-size",
  "thinking", "three-bars", "thumbsdown-filled", "thumbsdown", "thumbsup-filled", "thumbsup",
  "tools", "trash", "triangle-down", "triangle-left", "triangle-right", "triangle-up",
  "twitter", "type-hierarchy-sub", "type-hierarchy-super", "type-hierarchy", "unarchive", "unfold",
  "ungroup-by-ref-type", "unlock", "unmute", "unverified", "variable-group", "verified-filled",
  "verified", "vm-active", "vm-connect", "vm-outline", "vm-pending", "vm-running",
  "vm-small", "vm", "vr", "vscode-insiders", "vscode", "wand",
  "warning", "watch", "whitespace", "whole-word", "window-active", "word-wrap",
  "workspace-trusted", "workspace-unknown", "workspace-untrusted", "worktree-small", "worktree", "zoom-in",
  "zoom-out"
]

const WORD_ALIASES = {
  account: 'user person profile',
  add: 'plus create new',
  archive: 'box store',
  bell: 'alert notify',
  bookmark: 'save mark',
  bug: 'issue insect',
  check: 'tick done ok',
  circle: 'dot bullet',
  close: 'x cancel',
  cloud: 'sync',
  comment: 'chat message',
  copy: 'clone',
  database: 'db data',
  debug: 'bug breakpoint',
  error: 'fail',
  eye: 'view preview',
  file: 'document',
  filter: 'funnel',
  flame: 'fire hot',
  folder: 'directory',
  gear: 'settings cog',
  git: 'vcs source',
  globe: 'world web',
  heart: 'love like',
  home: 'house',
  info: 'information',
  key: 'password',
  lightbulb: 'idea',
  link: 'url',
  location: 'pin map',
  lock: 'secure',
  mail: 'email',
  pass: 'success done',
  person: 'user people',
  pin: 'location',
  pinned: 'pin',
  play: 'run start',
  plus: 'add',
  record: 'dot rec',
  refresh: 'reload sync',
  rocket: 'launch',
  save: 'disk',
  search: 'find',
  settings: 'gear cog',
  sparkle: 'ai magic',
  star: 'favorite',
  stop: 'square halt',
  sync: 'refresh',
  tag: 'label',
  target: 'aim',
  terminal: 'cli shell',
  trash: 'delete',
  triangle: 'play caret',
  warning: 'alert warn',
  watch: 'clock time'
}

function wordsFor(name) {
  const parts = name.split('-')
  const extra = []
  for (const part of parts) {
    if (WORD_ALIASES[part]) extra.push(WORD_ALIASES[part])
  }
  if (WORD_ALIASES[name]) extra.push(WORD_ALIASES[name])
  return [name, parts.join(' '), ...parts, ...extra].join(' ').toLowerCase()
}


let store = {
  get(key, fallback) {
    return fallback
  },
  set() {}
}

function loadBolds() {
  const raw = store.get('bolds', {})
  return raw && typeof raw === 'object' ? raw : {}
}

function sessionBold(sessionId) {
  return !!(sessionId && loadBolds()[sessionId])
}

function saveBold(sessionId, on) {
  if (!sessionId) return
  const next = { ...loadBolds() }
  if (on) next[sessionId] = true
  else delete next[sessionId]
  store.set('bolds', next)
}

function loadGlyphs() {
  const raw = store.get('glyphs', {})
  return raw && typeof raw === 'object' ? raw : {}
}

function saveGlyph(sessionId, glyph) {
  const next = { ...loadGlyphs() }
  if (glyph) next[sessionId] = glyph
  else delete next[sessionId]
  store.set('glyphs', next)
}

function isDark() {
  const scheme = getComputedStyle(document.documentElement).colorScheme || ''
  if (scheme.includes('dark')) return true
  if (scheme.includes('light')) return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function parseRgb(color) {
  if (!color) return null
  const box = document.createElement('span')
  box.style.color = color
  document.documentElement.appendChild(box)
  const out = getComputedStyle(box).color
  box.remove()
  const m = out.match(/rgba?\((\d+)[,\s]+(\d+)[,\s]+(\d+)/)
  if (!m) return null
  return { r: +m[1], g: +m[2], b: +m[3] }
}

function rgbToHsl(r, g, b) {
  r /= 255
  g /= 255
  b /= 255
  const max = Math.max(r, g, b)
  const min = Math.min(r, g, b)
  const l = (max + min) / 2
  if (max === min) return { h: 0, s: 0, l: l * 100 }
  const d = max - min
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min)
  let h = 0
  if (max === r) h = (g - b) / d + (g < b ? 6 : 0)
  else if (max === g) h = (b - r) / d + 2
  else h = (r - g) / d + 4
  return { h: h * 60, s: s * 100, l: l * 100 }
}

function adaptColor(color) {
  const rgb = parseRgb(color)
  if (!rgb) return color
  const { h, s, l } = rgbToHsl(rgb.r, rgb.g, rgb.b)
  if (s < 4) {
    return isDark() ? 'hsl(0 0% 82%)' : 'hsl(0 0% 28%)'
  }
  const nextL = isDark() ? Math.max(62, Math.min(78, l + 12)) : Math.min(42, Math.max(28, l - 14))
  return `hsl(${Math.round(h)} ${Math.round(s)}% ${Math.round(nextL)}%)`
}

function fiberOf(el) {
  if (!el) return null
  for (const key of Object.keys(el)) {
    if (key.startsWith('__reactFiber$') || key.startsWith('__reactInternalInstance$')) {
      return el[key]
    }
  }
  return null
}

function findProps(el, test, cap = 90) {
  const root = fiberOf(el)
  if (!root) return null
  const seen = new Set()
  const queue = [root]
  let n = 0
  while (queue.length && n < cap) {
    const fiber = queue.pop()
    n += 1
    if (!fiber || seen.has(fiber)) continue
    seen.add(fiber)
    const props = fiber.memoizedProps || fiber.pendingProps
    if (props && test(props)) return props
    if (fiber.return) queue.push(fiber.return)
  }
  return null
}

function colorSwatchProps(el) {
  return findProps(el, p => typeof p.onChange === 'function' && Array.isArray(p.swatches))
}

function sessionIdFrom(el) {
  const props = findProps(el, p => typeof p.sessionId === 'string' || (p.session && typeof p.session.id === 'string'))
  if (!props) return null
  return typeof props.sessionId === 'string' ? props.sessionId : props.session.id
}

function rowSessionId(row) {
  if (row.dataset.bcSid) return row.dataset.bcSid
  const start = row.querySelector('button') || row
  const id = sessionIdFrom(start)
  if (id) row.dataset.bcSid = id
  return id || null
}

function ensureStyle() {
  let style = document.getElementById(STYLE_ID)
  if (!style) {
    style = document.createElement('style')
    style.id = STYLE_ID
    document.head.appendChild(style)
  }
  style.textContent = `
    ${ROW}[data-bc-color] ${TITLE},
    ${ROW}[data-bc-color] ${TITLE} .hover-marquee-inner {
      color: var(--bc-color) !important;
    }
    ${ROW}[data-bc-bold="1"] ${TITLE},
    ${ROW}[data-bc-bold="1"] ${TITLE} .hover-marquee-inner {
      font-weight: 700 !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
      white-space: nowrap !important;
      animation: none !important;
      transform: none !important;
    }
    ${ROW}[data-bc-bold="1"] ${TITLE} .hover-marquee-inner {
      display: block !important;
      max-width: 100% !important;
    }
    ${ROW}[data-bc-bold="1"] ${TITLE}[data-marquee='true'] {
      text-overflow: ellipsis !important;
    }
    [${EXTRA_ATTR}="host"] {
      display: grid;
      grid-template-columns: 1fr 1fr;
      column-gap: 0.375rem;
      row-gap: 0;
    }
    [${EXTRA_ATTR}="host"] > .grid {
      grid-column: 1 / -1;
    }
    [${EXTRA_ATTR}="host"] > button:not([${EXTRA_ATTR}]) {
      margin-top: 0.5rem !important;
      width: auto !important;
    }
    [${EXTRA_ATTR}="custom"] {
      position: relative;
      overflow: hidden;
      margin-top: 0.5rem;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.375rem;
      width: 100%;
      border: 0;
      border-radius: 0.375rem;
      padding: 0.25rem 0;
      background: transparent;
      font-size: 0.75rem;
      color: var(--ui-text-tertiary);
      cursor: pointer;
    }
    [${EXTRA_ATTR}="custom"]:hover {
      background: var(--ui-control-hover-background);
      color: var(--foreground, var(--ui-text-primary));
    }
    [${EXTRA_ATTR}="picker"] {
      position: absolute;
      inset: 0;
      width: 100%;
      height: 100%;
      margin: 0;
      padding: 0;
      border: 0;
      opacity: 0;
      cursor: pointer;
    }
    [${EXTRA_ATTR}="panel"] {
      grid-column: 1 / -1;
      margin-top: 0.5rem;
      padding-top: 0.5rem;
      border-top: 1px solid var(--ui-stroke-secondary, var(--ui-border));
    }
    [${EXTRA_ATTR}="bold"] {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      margin: 0;
      font-size: 0.75rem;
      color: var(--ui-text-secondary);
      cursor: pointer;
      user-select: none;
    }
    [${EXTRA_ATTR}="rule"] {
      height: 1px;
      margin: 0.5rem 0;
      background: var(--ui-stroke-tertiary, var(--ui-stroke-secondary, var(--ui-border)));
    }
    [${EXTRA_ATTR}="icon-label"] {
      margin: 0 0 0.35rem;
      font-size: 0.75rem;
      font-weight: 600;
      color: var(--ui-text-secondary);
    }
    [${EXTRA_ATTR}="search"] {
      display: block;
      width: 100%;
      margin: 0 0 0.45rem;
      padding: 0.15rem 0 0.25rem;
      border: 0;
      border-bottom: 1px solid var(--ui-text-tertiary);
      border-radius: 0;
      outline: none;
      box-shadow: none;
      background: transparent;
      color: var(--ui-text-primary);
      font-size: 0.75rem;
    }
    [${EXTRA_ATTR}="search"]:focus {
      border-bottom-color: var(--ui-accent, var(--foreground));
    }
    [${EXTRA_ATTR}="glyphs"] {
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 0.25rem;
      max-height: 12.5rem;
      overflow-y: auto;
    }
    [${EXTRA_ATTR}="glyph-btn"],
    [${EXTRA_ATTR}="glyph-clear"] {
      display: grid;
      place-items: center;
      aspect-ratio: 1;
      border: 0;
      border-radius: 0.3rem;
      padding: 0;
      background: transparent;
      color: var(--ui-text-tertiary);
      cursor: pointer;
    }
    [${EXTRA_ATTR}="glyph-btn"]:hover,
    [${EXTRA_ATTR}="glyph-clear"]:hover {
      background: var(--ui-control-hover-background);
      color: var(--foreground, var(--ui-text-primary));
    }
    [${EXTRA_ATTR}="glyph-btn"][data-on="1"],
    [${EXTRA_ATTR}="glyph-clear"][data-on="1"] {
      background: var(--ui-control-active-background);
      color: var(--foreground, var(--ui-text-primary));
    }
    ${IDLE_DOT}[data-bc-glyph-hidden] {
      width: 0.875rem !important;
      height: 0.875rem !important;
      min-width: 0.875rem !important;
      min-height: 0.875rem !important;
      display: grid !important;
      place-items: center !important;
      overflow: hidden !important;
      border-radius: 0 !important;
      line-height: 0 !important;
      background: none !important;
      background-color: transparent !important;
      box-shadow: none !important;
    }
    ${IDLE_DOT}[data-bc-glyph-hidden] [${EXTRA_ATTR}="glyph"] {
      display: flex !important;
      align-items: center;
      justify-content: center;
      width: 11px;
      height: 11px;
      overflow: hidden;
      font: 11px/1 codicon !important;
      font-size: 11px !important;
      line-height: 1 !important;
    }
  `
}

function clearTitle(row) {
  delete row.dataset.bcColor
  row.style.removeProperty('--bc-color')
}

function paintTitle(row, color) {
  if (!color) {
    clearTitle(row)
    return
  }
  row.dataset.bcColor = '1'
  row.style.setProperty('--bc-color', adaptColor(color))
}

function clearGlyphNode(el) {
  el.querySelector(`[${EXTRA_ATTR}="glyph"]`)?.remove()
  if (el.dataset.bcGlyphHidden) {
    el.style.removeProperty('background')
    el.style.removeProperty('background-color')
    delete el.dataset.bcGlyphHidden
  }
}

function rowIsBusy(row) {
  if (row.getAttribute('data-working') === 'true') return true
  if (row.querySelector('[role="status"]')) return true
  for (const dot of row.querySelectorAll('span.rounded-full')) {
    if (dot.className.includes('size-1.5')) return true
  }
  return false
}

function paintGlyph(row, color) {
  if (rowIsBusy(row)) {
    row.querySelectorAll(`[${EXTRA_ATTR}="glyph"]`).forEach(node => node.remove())
    row.querySelectorAll('[data-bc-glyph-hidden]').forEach(clearGlyphNode)
    return
  }
  const idle = row.querySelector(IDLE_DOT)
  if (!idle) {
    row.querySelectorAll(`[${EXTRA_ATTR}="glyph"]`).forEach(node => node.remove())
    return
  }
  const sid = rowSessionId(row)
  const glyph = sid ? loadGlyphs()[sid] : null
  const tint = adaptColor(color || row._bcCached || 'var(--ui-text-quaternary)')
  const existing = idle.querySelector(`[${EXTRA_ATTR}="glyph"]`)
  if (!glyph) {
    clearGlyphNode(idle)
    return
  }
  const fill = idle.style.backgroundColor
  if (fill && fill !== 'transparent' && fill !== 'rgba(0, 0, 0, 0)') {
    row._bcCached = fill
  }
  idle.style.setProperty('background', 'none', 'important')
  idle.style.setProperty('background-color', 'transparent', 'important')
  idle.dataset.bcGlyphHidden = '1'
  if (existing && existing.classList.contains(`codicon-${glyph}`)) {
    if (existing.style.color !== tint) existing.style.color = tint
    return
  }
  existing?.remove()
  const icon = document.createElement('i')
  icon.className = `codicon codicon-${glyph}`
  icon.setAttribute(EXTRA_ATTR, 'glyph')
  icon.style.color = tint
  idle.appendChild(icon)
}

function paintSessionTitles() {
  document.querySelectorAll(ROW).forEach(row => {
    const sid = rowSessionId(row)
    if (sessionBold(sid)) {
      row.dataset.bcBold = '1'
      row.querySelectorAll(TITLE).forEach(el => {
        delete el.dataset.marquee
        el.style.removeProperty('--marquee-d')
        el.style.removeProperty('--marquee-t')
      })
    } else delete row.dataset.bcBold
    const idle = row.querySelector(IDLE_DOT)
    if (idle) {
      const fill = idle.style.backgroundColor
      const live = fill && fill !== 'transparent' && fill !== 'rgba(0, 0, 0, 0)'
      if (live) row._bcCached = fill
      else if (!idle.dataset.bcGlyphHidden) {
        delete row._bcCached
        clearTitle(row)
        paintGlyph(row, null)
        return
      }
    }
    if (row._bcCached) paintTitle(row, row._bcCached)
    paintGlyph(row, row._bcCached)
  })
}

function tintStock(buttons) {
  const flag = isDark() ? '1' : '0'
  buttons.forEach(btn => {
    const orig = btn.dataset.bcOrig || btn.style.backgroundColor
    if (!orig) return
    if (btn.dataset.bcOrig && btn.dataset.bcDark === flag) return
    btn.dataset.bcOrig = orig
    const shown = adaptColor(orig)
    btn.style.backgroundColor = shown
    btn.style.color = shown
    btn.dataset.bcDark = flag
  })
}

function injectCustomButton(host, stockBtn) {
  if (host.querySelector(`[${EXTRA_ATTR}="custom"]`)) return
  const props = colorSwatchProps(stockBtn)
  if (!props) return
  const custom = document.createElement('label')
  custom.setAttribute(EXTRA_ATTR, 'custom')
  custom.setAttribute('aria-label', 'Custom color')
  const picker = document.createElement('input')
  picker.type = 'color'
  picker.setAttribute(EXTRA_ATTR, 'picker')
  picker.tabIndex = 0
  const current = props.value || ''
  if (/^#([0-9a-f]{6})$/i.test(current)) picker.value = current
  const apply = hex => {
    const live = colorSwatchProps(stockBtn)
    const onChange = live?.onChange || props.onChange
    onChange(hex)
  }
  picker.addEventListener('input', () => apply(picker.value))
  picker.addEventListener('change', () => apply(picker.value))
  const holdOpen = event => event.stopPropagation()
  picker.addEventListener('pointerdown', holdOpen)
  picker.addEventListener('mousedown', holdOpen)
  picker.addEventListener('click', holdOpen)
  custom.addEventListener('pointerdown', holdOpen)
  custom.addEventListener('mousedown', holdOpen)
  const icon = document.createElement('i')
  icon.className = 'codicon codicon-symbol-color'
  custom.appendChild(picker)
  custom.appendChild(icon)
  custom.appendChild(document.createTextNode('Custom'))
  const clearBtn = [...host.querySelectorAll(':scope > button')].find(btn => !btn.hasAttribute(EXTRA_ATTR))
  if (clearBtn) clearBtn.after(custom)
  else host.appendChild(custom)
}

function injectPanel(host, stockBtn) {
  const props = colorSwatchProps(stockBtn)
  if (!props) return
  const sid = sessionIdFrom(stockBtn)
  if (!sid) return
  const openRow = document.querySelector(`${ROW} [data-state="open"]`)?.closest('.row-hover')
  if (openRow) openRow.dataset.bcSid = sid

  const panel = document.createElement('div')
  panel.setAttribute(EXTRA_ATTR, 'panel')

  const bold = document.createElement('label')
  bold.setAttribute(EXTRA_ATTR, 'bold')
  const box = document.createElement('input')
  box.type = 'checkbox'
  box.checked = sessionBold(sid)
  box.addEventListener('change', () => {
    saveBold(sid, box.checked)
    paintSessionTitles()
  })
  bold.appendChild(box)
  bold.appendChild(document.createTextNode('Bold Session'))
  panel.appendChild(bold)

  const rule = document.createElement('div')
  rule.setAttribute(EXTRA_ATTR, 'rule')
  panel.appendChild(rule)

  const heading = document.createElement('div')
  heading.setAttribute(EXTRA_ATTR, 'icon-label')
  heading.textContent = 'Icon'
  panel.appendChild(heading)

  const search = document.createElement('input')
  search.type = 'search'
  search.setAttribute(EXTRA_ATTR, 'search')
  search.placeholder = 'Search icons'
  search.autocomplete = 'off'
  search.addEventListener('keydown', event => event.stopPropagation())
  search.addEventListener('mousedown', event => event.stopPropagation())
  search.addEventListener('input', () => filterGlyphs(panel, search.value))
  panel.appendChild(search)

  const grid = document.createElement('div')
  grid.setAttribute(EXTRA_ATTR, 'glyphs')

  const clear = document.createElement('button')
  clear.type = 'button'
  clear.setAttribute(EXTRA_ATTR, 'glyph-clear')
  clear.setAttribute('aria-label', 'Default dot')
  clear.title = 'Default dot'
  clear.dataset.words = 'default none empty dot bullet'
  clear.innerHTML = '<i class="codicon codicon-circle-slash"></i>'
  clear.addEventListener('click', event => {
    event.preventDefault()
    event.stopPropagation()
    saveGlyph(sid, null)
    paintSessionTitles()
    syncGlyphButtons(panel, sid)
  })
  grid.appendChild(clear)

  GLYPH_NAMES.forEach(name => {
    const btn = document.createElement('button')
    btn.type = 'button'
    btn.setAttribute(EXTRA_ATTR, 'glyph-btn')
    btn.dataset.glyph = name
    btn.dataset.words = wordsFor(name)
    btn.setAttribute('aria-label', name)
    btn.title = name.replace(/-/g, ' ')
    const icon = document.createElement('i')
    icon.className = `codicon codicon-${name}`
    btn.appendChild(icon)
    btn.addEventListener('click', event => {
      event.preventDefault()
      event.stopPropagation()
      saveGlyph(sid, name)
      paintSessionTitles()
      syncGlyphButtons(panel, sid)
    })
    grid.appendChild(btn)
  })
  panel.appendChild(grid)
  syncGlyphButtons(panel, sid)
  host.appendChild(panel)
}

function filterGlyphs(panel, query) {
  const needles = query.trim().toLowerCase().split(/\s+/).filter(Boolean)
  panel.querySelectorAll(`[${EXTRA_ATTR}="glyph-btn"]`).forEach(btn => {
    const hay = btn.dataset.words || ''
    const ok = !needles.length || needles.every(n => hay.includes(n))
    btn.style.display = ok ? '' : 'none'
  })
}

function syncGlyphButtons(panel, sid) {
  const current = loadGlyphs()[sid] || ''
  panel.querySelectorAll(`[${EXTRA_ATTR}="glyph-btn"]`).forEach(btn => {
    btn.dataset.on = btn.dataset.glyph === current ? '1' : '0'
  })
  const clear = panel.querySelector(`[${EXTRA_ATTR}="glyph-clear"]`)
  if (clear) clear.dataset.on = current ? '0' : '1'
}

function enhancePickers() {
  document.querySelectorAll('.grid.grid-cols-6').forEach(grid => {
    const stock = [...grid.querySelectorAll('button.size-5.rounded-full')].filter(
      btn => !btn.hasAttribute(EXTRA_ATTR)
    )
    if (stock.length < 8) return
    tintStock(stock)
    const host = grid.parentElement
    if (!host) return
    host.setAttribute(EXTRA_ATTR, 'host')
    injectCustomButton(host, stock[0])
    if (host.querySelector(`[${EXTRA_ATTR}="panel"]`)) return
    injectPanel(host, stock[0])
  })
}

function start() {
  ensureStyle()
  paintSessionTitles()
  enhancePickers()

  let scheduled = false
  const observer = new MutationObserver(() => {
    if (scheduled) return
    scheduled = true
    requestAnimationFrame(() => {
      scheduled = false
      paintSessionTitles()
      enhancePickers()
    })
  })
  observer.observe(document.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style', 'class', 'data-working']
  })
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ['style', 'class', 'data-theme']
  })

  return () => {
    observer.disconnect()
    document.getElementById(STYLE_ID)?.remove()
    document.querySelectorAll(`[${EXTRA_ATTR}]`).forEach(node => node.remove())
    document.querySelectorAll(`${ROW}[data-bc-color]`).forEach(clearTitle)
    document.querySelectorAll(`${ROW}[data-bc-bold]`).forEach(row => delete row.dataset.bcBold)
  }
}

export default {
  id: ID,
  name: 'Better Colors',
  description: 'Session list appearance: color and bold titles, extra Appearance colors, idle-bullet glyphs.',
  defaultEnabled: true,
  register(ctx) {
    store = ctx.storage
    ctx.onDispose(start())
  }
}
