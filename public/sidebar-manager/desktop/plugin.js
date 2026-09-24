/**
 * Sidebar Manager for Hermes (public / listed edition).
 *
 * A statusbar chip opens a dialog: toggle the sidebar's core nav rows on/off
 * and reorder them. Prefs are contributed through the SDK's
 * SIDEBAR_NAV_PREFS_AREA (hide + order) and persisted in ctx.storage, which is
 * cleaned with the plugin. Session sections (Pinned, Recents, Cron jobs) are
 * not covered by the SDK area; see LIMITATIONS.md.
 */

import {
  cn,
  Codicon,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  Button,
  ListRow,
  ToggleRow,
  SIDEBAR_NAV_PREFS_AREA,
  STATUSBAR_AREAS,
} from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useEffect, useState } from 'react'

const ID = 'sidebar-manager'
const SOURCE = 'https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/sidebar-manager'
const STYLE_ID = 'sidebar-manager-style'

// Core nav rows (SidebarNavId). `artifacts` and `cron` only render in
// Advanced mode; hiding them there is still valid.
const NAV_ROWS = [
  { id: 'new-session', label: 'New session' },
  { id: 'capabilities', label: 'Capabilities' },
  { id: 'messaging', label: 'Messaging' },
  { id: 'artifacts', label: 'Artifacts' },
  { id: 'cron', label: 'Cron jobs' },
]
// The row hosting the Plugins tab can be moved but never hidden (core
// arbitration ignores it in `hide`).
const HIDE_LOCKED = new Set(['capabilities'])

let storageApi = null
let openExternal = null
let contribute = () => {}

function loadPrefs() {
  try {
    const raw = storageApi ? storageApi.get('navPrefs', null) : null
    if (!raw) return { hide: [], order: [] }
    return {
      hide: Array.isArray(raw.hide) ? raw.hide.map(String).filter(Boolean) : [],
      order: Array.isArray(raw.order) ? raw.order.map(String).filter(Boolean) : [],
    }
  } catch {
    return { hide: [], order: [] }
  }
}

function savePrefs(next) {
  try {
    if (storageApi) storageApi.set('navPrefs', next)
  } catch {
    /* storage full or unavailable: prefs stay session-local */
  }
  contribute(next)
}

function orderedIds(prefs) {
  const core = NAV_ROWS.map(row => row.id)
  const named = prefs.order.filter(id => core.includes(id))
  const rest = core.filter(id => !named.includes(id))
  return [...named, ...rest]
}

function moveId(prefs, id, delta) {
  const ids = orderedIds(prefs)
  const from = ids.indexOf(id)
  const to = from + delta
  if (from < 0 || to < 0 || to >= ids.length) return prefs
  ids.splice(to, 0, ids.splice(from, 1)[0])
  return { ...prefs, order: ids }
}

function toggleHidden(prefs, id) {
  if (HIDE_LOCKED.has(id)) return prefs
  const hide = new Set(prefs.hide)
  if (hide.has(id)) hide.delete(id)
  else hide.add(id)
  return { ...prefs, hide: [...hide] }
}

function ManagerDialog({ open, onOpenChange }) {
  const [prefs, setPrefs] = useState(() => loadPrefs())

  useEffect(() => {
    if (open) setPrefs(loadPrefs())
  }, [open])

  const apply = next => {
    setPrefs(next)
    savePrefs(next)
  }

  const labelFor = id => {
    const row = NAV_ROWS.find(r => r.id === id)
    return row ? row.label : id
  }

  return jsx(Dialog, {
    open,
    onOpenChange,
    children: jsx(DialogContent, {
      fitContent: true,
      'data-context-menu-skip': '',
      className: cn(
        'min-w-[24rem] max-w-lg rounded-xl shadow-nous border-(--ui-accent)',
        'bg-(--ui-chat-bubble-background)'
      ),
      bodyClassName: 'gap-3 overflow-auto max-h-[70vh]',
      children: [
        jsxs(DialogHeader, {
          className: 'flex flex-row items-center justify-between gap-2 pr-8 h-7 -mt-2',
          children: [
            jsx(DialogTitle, { children: 'Sidebar nav' }),
            jsx('a', {
              href: SOURCE,
              title: 'Source on GitHub',
              target: '_blank',
              rel: 'noreferrer',
              onClick: e => {
                e.preventDefault()
                if (openExternal) openExternal(SOURCE)
              },
              className:
                'inline-flex items-center text-(--ui-text-quaternary) hover:text-(--ui-text-tertiary)',
              children: jsx(Codicon, { name: 'github', size: '0.7rem' }),
            }),
          ],
        }),
        jsx('div', {
          className: 'text-[0.7rem] text-(--ui-text-tertiary)',
          children:
            'Toggles hide nav rows; arrows reorder them. Session sections are not covered by the SDK area.',
        }),
        orderedIds(prefs).map(id =>
          jsx(ListRow, {
            key: id,
            title: labelFor(id),
            action: jsxs('div', {
              className: 'flex items-center gap-1',
              children: [
                jsx(Button, {
                  variant: 'ghost',
                  size: 'sm',
                  type: 'button',
                  'aria-label': 'Move up',
                  onClick: () => apply(moveId(prefs, id, -1)),
                  children: jsx(Codicon, { name: 'chevron-up', size: '0.8rem' }),
                }),
                jsx(Button, {
                  variant: 'ghost',
                  size: 'sm',
                  type: 'button',
                  'aria-label': 'Move down',
                  onClick: () => apply(moveId(prefs, id, 1)),
                  children: jsx(Codicon, { name: 'chevron-down', size: '0.8rem' }),
                }),
              ],
            }),
            below: jsx(ToggleRow, {
              label: 'Show row',
              checked: !prefs.hide.includes(id),
              disabled: HIDE_LOCKED.has(id),
              onChange: () => apply(toggleHidden(prefs, id)),
            }),
          })
        ),
      ],
    }),
  })
}

function Chip() {
  const [open, setOpen] = useState(false)

  return jsxs('span', {
    className: 'inline-flex items-center gap-1',
    children: [
      jsx('button', {
        type: 'button',
        title: 'Sidebar nav rows: hide / reorder',
        onClick: () => setOpen(true),
        className:
          'inline-flex h-6 items-center gap-1 rounded-md border border-(--ui-stroke-secondary) px-1.5 text-[0.65rem] text-(--ui-text-secondary) hover:bg-(--chrome-action-hover)',
        children: jsx(Codicon, { name: 'list-ordered', size: '0.7rem' }),
      }),
      jsx(ManagerDialog, { open, onOpenChange: setOpen }),
    ],
  })
}

export default {
  id: ID,
  name: 'Sidebar Manager',
  description:
    'Hide and reorder the sidebar core nav rows from a statusbar dialog (SDK sidebarNav.prefs).',
  defaultEnabled: false,
  register(ctx) {
    openExternal = ctx.os && ctx.os.openExternal
    storageApi = ctx.storage

    let dispose = () => {}
    contribute = prefs => {
      dispose()
      dispose = ctx.register({
        id: 'prefs',
        area: SIDEBAR_NAV_PREFS_AREA,
        data: { hide: prefs.hide || [], order: prefs.order || [] },
      })
    }
    contribute(loadPrefs())

    ctx.register({
      id: 'host',
      area: STATUSBAR_AREAS.right,
      order: 410,
      render: () =>
        jsx('span', {
          'aria-hidden': true,
          style: { display: 'contents' },
          children: jsx(Chip, {}),
        }),
    })

    ctx.onDispose(() => {
      dispose()
      contribute = () => {}
      storageApi = null
      document.getElementById(STYLE_ID)?.remove()
    })
  },
}
