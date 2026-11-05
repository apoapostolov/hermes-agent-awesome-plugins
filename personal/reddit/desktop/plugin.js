/**
 * Reddit — Settings ▸ Plugins page.
 *
 * One page that does what the CLI does: save this user's own Reddit app
 * credentials, verify them, run the OAuth login with the loopback catcher, and
 * show which account is connected. Backend calls go through
 * `ctx.rest(...)` → `/api/plugins/reddit/` (dashboard/plugin_api.py).
 *
 * The page paints no control chrome of its own: fields, buttons and tags come
 * from the app's SDK components, so they follow the active theme. Inline styles
 * carry layout and live theme tokens only.
 */

import { Badge, Button, Input, host, PALETTE_AREA } from '@hermes/plugin-sdk'
import { useCallback, useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'reddit'
const APPS_URL = 'https://www.reddit.com/prefs/apps'
const SETTINGS_HREF = '/settings?tab=plugins&plugin=reddit'
const PALETTE = typeof PALETTE_AREA === 'string' ? PALETTE_AREA : 'palette'

const S = {
  page: { display: 'flex', flexDirection: 'column', gap: 6, maxWidth: 760 },
  section: { display: 'flex', flexDirection: 'column', gap: 2, paddingTop: 6 },
  heading: { display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between', minHeight: 28 },
  title: { fontSize: 13, fontWeight: 500, margin: 0 },
  intro: { fontSize: 12, lineHeight: 1.5, margin: 0, color: 'var(--ui-text-tertiary)' },
  row: { display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', paddingTop: 6 },
  field: { display: 'flex', flexDirection: 'column', gap: 4, paddingTop: 6 },
  label: { fontSize: 12, fontWeight: 500 },
  hint: { fontSize: 11.5, lineHeight: 1.5, margin: 0, color: 'var(--ui-text-tertiary)', overflowWrap: 'anywhere' },
  spacer: { flex: 1 },
  note: { fontSize: 11.5, margin: 0, color: 'var(--ui-text-quaternary)', overflowWrap: 'anywhere' },
  pending: {
    display: 'flex',
    flexDirection: 'column',
    gap: 10,
    padding: '12px 14px',
    margin: '6px 0',
    borderRadius: 3,
    background: 'var(--ui-bg-tertiary)'
  },
  dot: { width: 6, height: 6, borderRadius: 999, background: 'currentColor', display: 'inline-block' },
  ok: { fontSize: 12.5, margin: 0, color: 'var(--ui-green)' },
  err: { fontSize: 12.5, margin: 0, color: 'var(--ui-red)' }
}

/** `ctx.rest` throws "<status>: <json body>"; pull FastAPI's `detail` out. */
function readError(error) {
  const raw = error instanceof Error ? error.message : String(error)
  const match = /^(\d{3}):\s*([\s\S]*)$/.exec(raw)
  if (!match) return raw.slice(0, 400)
  try {
    const body = JSON.parse(match[2])
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) return body.detail.map(part => part.msg || '').join('; ') || raw
  } catch {
    /* not JSON: fall through */
  }
  return `${match[1]}: ${match[2].slice(0, 300)}`
}

function Field({ hint, label, onChange, placeholder, type = 'text', value }) {
  return jsxs('label', {
    style: S.field,
    children: [
      jsx('span', { style: S.label, children: label }),
      jsx(Input, {
        onChange: event => onChange(event.currentTarget.value),
        placeholder,
        spellCheck: false,
        type,
        value
      }),
      hint ? jsx('span', { style: S.hint, children: hint }) : null
    ]
  })
}

function Btn({ busy, disabled, children, onClick, primary, title }) {
  return jsx(Button, {
    disabled: !!busy || !!disabled,
    onClick,
    size: 'sm',
    title,
    type: 'button',
    variant: primary ? 'default' : 'outline',
    children: busy ? `${busy}…` : children
  })
}

function Tag({ children }) {
  return jsx(Badge, { variant: 'muted', children })
}

function RedditLibrary({ ctx, account }) {
  const [query, setQuery] = useState('')
  const [tag, setTag] = useState('')
  const [queue, setQueue] = useState(false)
  const [unread, setUnread] = useState(false)
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [cursor, setCursor] = useState('')
  const [transfer, setTransfer] = useState('')
  const [offset, setOffset] = useState(0)
  useEffect(() => {
    const deadlines = (data?.results.items || []).map(item => (item.checked_at + 48 * 60 * 60) * 1000).filter(Number.isFinite)
    if (!deadlines.length) return undefined
    const timer = setTimeout(() => {
      setData(null)
      setNotice('Cached sources expired. Reload the library to retrieve current results.')
    }, Math.max(0, Math.min(...deadlines) - Date.now()) + 10)
    return () => clearTimeout(timer)
  }, [data])
  useEffect(() => {
    if (!selected || !selected.expires_at) return undefined
    const remaining = selected.expires_at * 1000 - Date.now()
    if (remaining <= 0) { setSelected(null); return undefined }
    const timer = setTimeout(() => setSelected(null), Math.min(remaining, 2147483647))
    return () => clearTimeout(timer)
  }, [selected])
  const requestRef = useRef(0)
  const load = async (nextOffset = 0) => {
    const params = new URLSearchParams({ query, tag, account, limit: '15', offset: String(nextOffset) })
    if (queue) params.set('summary_source', 'extractive')
    if (unread) params.set('read', 'false')
    const token = ++requestRef.current
    try {
      const next = await ctx.rest(`library?${params}`)
      if (token !== requestRef.current) return
      setData(next)
      setOffset(nextOffset)
    } catch (err) {
      if (token === requestRef.current) setError(readError(err))
    }
  }
  useEffect(() => {
    const token = ++requestRef.current
    ctx.rest('library?account=' + encodeURIComponent(account) + '&limit=15').then(next => {
      if (token === requestRef.current) setData(next)
    }).catch(err => { if (token === requestRef.current) setError(readError(err)) })
  }, [ctx, account])
  const run = async (label, task) => {
    setBusy(label)
    setError('')
    setNotice('')
    try { await task() } catch (err) { setError(readError(err)) } finally { setBusy('') }
  }
  const action = body => ctx.rest('library', { method: 'POST', timeoutMs: 60000, body: { ...body, account } })
  const sync = () => run('Syncing', async () => {
    const result = await action({ action: 'sync', pages: 1, after: cursor })
    setCursor(result.after || '')
    setNotice(`${result.stored} sources cached.${result.after ? ' More pages are available.' : ' Reddit returned its final listing page.'}`)
    await load(0)
  })
  return jsxs('section', { style: S.section, 'aria-label': 'Local Reddit library', children: [
    jsx('h3', { style: S.title, children: 'Local saves' }),
    jsx('p', { style: S.intro, children: data ? `${data.stats.fresh} fresh sources, ${data.stats.stale} expired bookmarks. Snapshots and annotations expire after 48 hours without refresh.` : 'Load and search saved content on this machine.' }),
    jsxs('form', { onSubmit: event => { event.preventDefault(); run('Searching', () => load(0)) }, children: [
      jsx(Field, { label: 'Search saved text and context', value: query, onChange: setQuery, placeholder: 'sqlite "query planner" -mysql' }),
      jsx(Field, { label: 'Filter by tag', value: tag, onChange: setTag, placeholder: 'Optional tag' }),
      jsxs('div', { style: S.row, children: [
        jsx(Btn, { busy, onClick: () => run('Searching', () => load(0)), primary: true, children: 'Search' }),
        jsx(Btn, { busy, onClick: () => setQueue(!queue), title: 'Apply with Search', children: queue ? 'Summary queue: on' : 'Summary queue: off' }),
        jsx(Btn, { busy, onClick: () => setUnread(!unread), title: 'Apply with Search', children: unread ? 'Unread only: on' : 'Unread only: off' })
      ] })
    ] }),
    jsxs('div', { style: S.row, children: [
      jsx(Btn, { busy, onClick: sync, children: cursor ? 'Sync next page' : 'Sync saves' }),
      jsx(Btn, { busy, onClick: () => run('Refreshing', async () => { await action({ action: 'refresh' }); setSelected(null); await load(offset) }), children: 'Refresh oldest 100' }),
      jsx(Btn, { busy, onClick: () => run('Cleaning', async () => { await action({ action: 'purge' }); await load(offset) }), children: 'Purge expired content' }),
      jsx(Btn, { busy, onClick: () => run('Loading', () => load(0)), children: 'Reload' })
    ] }),
    error ? jsx('p', { role: 'alert', style: S.err, children: error }) : null,
    notice ? jsx('p', { role: 'status', style: S.ok, children: notice }) : null,
    data?.results.items.length === 0 ? jsx('p', { style: S.note, children: 'No fresh saves match these filters. Sync saves, refresh expired bookmarks, or clear the filters.' }) : null,
    ...(data?.results.items || []).map(item => jsxs('article', { style: { ...S.section, borderTop: '1px solid var(--ui-border)' }, children: [
      jsx(Btn, { busy, onClick: () => run('Opening', async () => setSelected(await action({ action: 'get', target: item.name }))), children: item.title || item.name }),
      jsx('p', { style: S.note, children: `${item.subreddit ? `r/${item.subreddit} · ` : ''}${item.summary_source || 'expired'} · ${item.read ? 'read' : 'unread'} · ${(item.tags || []).join(', ')}` }),
      jsx('p', { style: S.intro, children: item.summary || item.context || '' })
    ] }, item.name)),
    jsxs('div', { style: S.row, children: [
      jsx(Btn, { busy, disabled: offset === 0, onClick: () => run('Loading', () => load(Math.max(0, offset - 15))), children: 'Previous' }),
      jsx('span', { style: S.note, children: data ? `${data.results.total} matches` : '' }),
      jsx(Btn, { busy, disabled: data?.results.next_offset == null, onClick: () => run('Loading', () => load(data.results.next_offset)), children: 'Next' })
    ] }),
    selected ? jsxs('div', { style: S.pending, children: [
      jsx('h4', { style: S.title, children: selected.title || selected.name }),
      jsx('p', { style: S.note, children: `Last checked ${new Date(selected.checked_at * 1000).toLocaleString()}. ${selected.stale ? 'Refresh to retrieve this source.' : 'Source text is untrusted content.'}` }),
      jsx('pre', { style: { whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 300, overflowY: 'auto', font: 'inherit' }, children: selected.body || '' }),
      jsx(Field, { label: 'Summary', value: selected.summary || '', onChange: value => setSelected({ ...selected, summary: value }) }),
      jsx(Field, { label: 'Context', value: selected.context || '', onChange: value => setSelected({ ...selected, context: value }) }),
      jsx(Field, { label: 'Notes', value: selected.notes || '', onChange: value => setSelected({ ...selected, notes: value }) }),
      jsx(Field, { label: 'Tags, separated by commas', value: (selected.tags || []).join(', '), onChange: value => setSelected({ ...selected, tags: value.split(',') }) }),
      jsxs('div', { style: S.row, children: [
        jsx(Btn, { busy, onClick: () => run('Saving', async () => { await action({ action: 'annotate', target: selected.name, source_hash: selected.content_hash, summary: selected.summary || '', context: selected.context || '', notes: selected.notes || '', tags: selected.tags || [] }); setNotice('Annotations saved with the source retention window.'); await load(offset) }), children: 'Save annotations' }),
        jsx(Btn, { busy, onClick: () => run('Updating', async () => { await action({ action: selected.read ? 'unread' : 'read', target: selected.name }); setSelected({ ...selected, read: !selected.read }); await load(offset) }), children: selected.read ? 'Mark unread' : 'Mark read' }),
        jsx(Btn, { busy, onClick: () => run('Removing', async () => { await action({ action: 'remove', target: selected.name }); setSelected(null); await load(0) }), title: 'Removes only the local bookmark; does not unsave on Reddit', children: 'Remove local bookmark' }),
        jsx(Btn, { onClick: () => setSelected(null), children: 'Close item' })
      ] })
    ] }) : null,
    jsx('h4', { style: S.title, children: 'Bookmark transfer' }),
    jsx('p', { style: S.note, children: 'Export/import identifiers only. Imported bookmarks need a live refresh; source text and annotations are excluded.' }),
    jsx(Field, { label: 'Bookmark JSON', value: transfer, onChange: setTransfer, placeholder: 'Paste a hermes-reddit-bookmarks export' }),
    jsxs('div', { style: S.row, children: [
      jsx(Btn, { busy, onClick: () => run('Exporting', async () => setTransfer(JSON.stringify(await action({ action: 'export' })))), children: 'Export bookmarks' }),
      jsx(Btn, { busy, onClick: () => run('Importing', async () => { await action({ action: 'import', bookmarks: JSON.parse(transfer) }); await load(0); setNotice('Bookmarks imported. Refresh retrieves accessible content.') }), children: 'Import bookmarks' })
    ] }),
    jsx('p', { style: S.note, children: data?.maintenance.limit || 'Background cleanup runs only while Hermes is running.' })
  ] })
}

function RedditSettingsPage({ ctx }) {
  const [status, setStatus] = useState(null)
  const [form, setForm] = useState({
    client_id: '',
    client_secret: '',
    redirect_uri: 'http://localhost:8080',
    user_agent: ''
  })
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState(null)
  const [pending, setPending] = useState(null)
  const [paste, setPaste] = useState('')
  const [identity, setIdentity] = useState(null)
  const [copied, setCopied] = useState(false)
  const [libraryAccount, setLibraryAccount] = useState('')
  const [accountDraft, setAccountDraft] = useState('')
  useEffect(() => { setAccountDraft(libraryAccount) }, [libraryAccount])
  useEffect(() => {
    if (status?.logged_in && status.username) setLibraryAccount(status.username)
  }, [status?.logged_in, status?.username])

  const rest = useCallback(
    (path, options) => ctx.rest(path, { timeoutMs: 60000, ...(options || {}) }),
    [ctx]
  )

  const refresh = useCallback(async () => {
    try {
      const next = await rest('status')
      setStatus(next)
      setForm(current => ({
        ...current,
        client_id: next.client_id || '',
        redirect_uri: next.redirect_uri || 'http://localhost:8080',
        user_agent: next.user_agent || ''
      }))
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    }
  }, [rest])

  useEffect(() => {
    refresh()
  }, [refresh])

  // Poll the OAuth flow while a login is in flight.
  useEffect(() => {
    if (!pending) return undefined
    let stopped = false
    const tick = async () => {
      try {
        const next = await rest('login/status')
        if (stopped) return
        if (next.status === 'logged_in') {
          setPending(null)
          setMessage({ kind: 'ok', text: `Connected as u/${next.username}` })
          refresh()
        } else if (next.status === 'failed') {
          setPending(null)
          setMessage({ kind: 'err', text: next.error || 'Login failed' })
        }
      } catch {
        /* transient poll failure: try again on the next tick */
      }
    }
    tick()
    const timer = setInterval(tick, 2000)
    return () => {
      stopped = true
      clearInterval(timer)
    }
  }, [pending, refresh, rest])

  const setField = (key, value) => setForm(current => ({ ...current, [key]: value }))

  const configureExtras = async values => {
    setBusy('Updating')
    setMessage(null)
    try {
      await rest('config', { method: 'POST', body: { ...values, verify: false } })
      await refresh()
      setMessage({ kind: 'ok', text: 'Local protection and maintenance settings updated.' })
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally { setBusy('') }
  }

  const save = async validate => {
    setBusy('Saving')
    setMessage(null)
    try {
      const saved = await rest('config', {
        method: 'POST',
        body: {
          client_id: form.client_id,
          client_secret: form.client_secret,
          redirect_uri: form.redirect_uri,
          user_agent: form.user_agent,
          verify: validate
        }
      })
      setForm(current => ({ ...current, client_secret: '' }))
      setMessage({
        kind: 'ok',
        text: validate
          ? `Saved and verified: Reddit accepted these credentials (app scopes ${saved.validation?.scopes || 'ok'}).`
          : 'Saved. Verification skipped.'
      })
      refresh()
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally {
      setBusy('')
    }
  }

  const startLogin = async () => {
    setBusy('Starting')
    setMessage(null)
    try {
      const started = await rest('login/start', { method: 'POST', body: {} })
      setPending(started)
      if (typeof ctx.os?.openExternal === 'function') {
        await ctx.os.openExternal(started.authorize_url)
      } else if (typeof host.notify === 'function') {
        host.notify({ kind: 'info', message: 'Open the consent URL shown below.' })
      }
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally {
      setBusy('')
    }
  }

  const finishLogin = async () => {
    if (!paste.trim()) return
    setBusy('Finishing')
    try {
      const done = await rest('login/complete', { method: 'POST', body: { value: paste.trim() } })
      setPending(null)
      setPaste('')
      setMessage({ kind: 'ok', text: `Connected as u/${done.username}` })
      refresh()
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally {
      setBusy('')
    }
  }

  const logout = async () => {
    setBusy('Logging out')
    try {
      await rest('logout', { method: 'POST' })
      setIdentity(null)
      setMessage({ kind: 'ok', text: 'Token deleted. The app credentials are kept.' })
      refresh()
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally {
      setBusy('')
    }
  }

  const verify = async () => {
    setBusy('Checking')
    setIdentity(null)
    try {
      const live = await rest('identity')
      setIdentity(live)
      setMessage(
        live.logged_in
          ? { kind: 'ok', text: `Reddit answered for u/${live.username} (${live.link_karma} link, ${live.comment_karma} comment karma).` }
          : { kind: 'err', text: live.error || live.hint || 'Not connected.' }
      )
    } catch (error) {
      setMessage({ kind: 'err', text: readError(error) })
    } finally {
      setBusy('')
    }
  }

  const copyUrl = async () => {
    if (!pending?.authorize_url) return
    const ok = typeof ctx.os?.writeClipboard === 'function' && (await ctx.os.writeClipboard(pending.authorize_url))
    setCopied(!!ok)
    if (!ok && typeof host.notify === 'function') {
      host.notify({ kind: 'warning', message: 'Select the URL and copy it manually.' })
    }
  }

  const configured = !!status?.configured
  const connected = !!status?.logged_in
  const scopeCount = status?.scopes ? status.scopes.split(/\s+/).filter(Boolean).length : 0

  return jsxs('div', {
    'data-reddit-settings': '',
    style: S.page,
    children: [
      jsxs('div', {
        style: S.heading,
        children: [
          jsxs('div', {
            style: S.section,
            children: [
              jsx('h2', { style: S.title, children: 'Reddit' }),
              jsx('p', {
                style: S.intro,
                children:
                  'Use your own Reddit API app. Reads and writes run as the account you log in with, so private subreddits, saved items, mod queues and the inbox all work.'
              })
            ]
          }),
          jsxs(Badge, {
            variant: connected ? 'success' : configured ? 'warn' : 'muted',
            children: [
              jsx('span', { style: S.dot }),
              connected ? `u/${status?.username || 'connected'}` : configured ? 'app saved' : 'not set up'
            ]
          })
        ]
      }),

      message
        ? jsx('p', { style: message.kind === 'ok' ? S.ok : S.err, children: message.text })
        : null,

      // ---- app credentials -------------------------------------------
      jsxs('section', {
        style: S.section,
        children: [
          jsxs('div', {
            style: S.heading,
            children: [
              jsx('h3', { style: S.title, children: 'Reddit app' }),
              jsx(Btn, {
                onClick: () => ctx.os?.openExternal?.(APPS_URL),
                title: APPS_URL,
                children: 'Open reddit.com/prefs/apps'
              })
            ]
          }),
          jsx('p', {
            style: S.intro,
            children:
              'Use an existing approved web app and match its redirect URI exactly. Reddit closed new public Data API requests on October 31, 2026 and plans to end remaining public access in March 2027. Devvit does not expose personal saved items.'
          }),
          jsx(Field, {
            label: 'Client id',
            onChange: value => setField('client_id', value),
            placeholder: 'e.g. 7c9Sz-lmS6KuFFc8IGdBug',
            value: form.client_id
          }),
          jsx(Field, {
            label: 'Client secret',
            hint: status?.client_secret_set ? 'A secret is already stored. Leave blank to keep it.' : undefined,
            onChange: value => setField('client_secret', value),
            placeholder: status?.client_secret_set ? '•••••••• stored' : 'app secret',
            type: 'password',
            value: form.client_secret
          }),
          jsx(Field, {
            label: 'Redirect uri',
            hint: 'Must match the app exactly, character for character.',
            onChange: value => setField('redirect_uri', value),
            placeholder: 'http://localhost:8080',
            value: form.redirect_uri
          }),
          jsx(Field, {
            label: 'User agent',
            hint: 'Use a truthful contact, e.g. desktop:hermes-reddit:v1.1.0 (by /u/yourname).',
            onChange: value => setField('user_agent', value),
            placeholder: 'desktop:hermes-reddit:v1.1.0 (by /u/yourname)',
            value: form.user_agent
          }),
          jsxs('div', {
            style: S.row,
            children: [
              jsx(Btn, { busy: busy === 'Saving', onClick: () => save(true), primary: true, children: 'Save & verify' }),
              jsx(Btn, { busy: busy === 'Saving', onClick: () => save(false), children: 'Save only' }),
              jsx('span', { style: S.spacer }),
              jsx('span', {
                style: S.note,
                title: status?.config_file || '',
                children: status?.source ? `source: ${status.source}` : 'no credentials found'
              })
            ]
          }),
          jsx('p', { style: S.note, children: `Stored in ${status?.config_file || '$HERMES_HOME/reddit-config.json'}` }),
          jsxs('div', { style: S.row, children: [
            status?.secret_protection_available ? jsx(Btn, { busy, onClick: () => configureExtras({ protect_secrets: true }), children: status?.protect_secrets ? 'Recheck credential encryption' : 'Encrypt stored credentials' }) : null,
            jsx(Btn, { busy, onClick: () => configureExtras({ background_refresh: !status?.background_refresh }), children: status?.background_refresh ? 'Turn off background revalidation' : 'Enable background revalidation' })
          ] }),
          jsx('p', { style: S.note, children: 'Cleanup runs every minute while the plugin is loaded. Optional online revalidation checks up to 100 known bookmarks per 30 minutes; it does not change Reddit content.' })
        ]
      }),

      // ---- account ----------------------------------------------------
      jsxs('section', {
        style: S.section,
        children: [
          jsx('h3', { style: S.title, children: 'Account' }),
          jsx('p', {
            style: S.intro,
            children: connected
              ? `Logged in as u/${status?.username || 'unknown'}${scopeCount ? ` with ${scopeCount} scopes` : ''}. Access tokens refresh automatically.`
              : 'Not connected yet. Log in opens Reddit’s consent page; the code comes back to http://localhost:8080 and is exchanged for a refresh token.'
          }),

          pending
            ? jsxs('div', {
                style: S.pending,
                children: [
                  jsx('p', { style: S.intro, children: 'Waiting for approval. Open the consent page, approve, and this page finishes on its own.' }),
                  jsx(Input, {
                    className: 'font-mono',
                    onFocus: event => event.currentTarget.select(),
                    readOnly: true,
                    size: 'sm',
                    value: pending.authorize_url
                  }),
                  jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(Btn, {
                        onClick: () => ctx.os?.openExternal?.(pending.authorize_url),
                        primary: true,
                        children: 'Open consent page'
                      }),
                      jsx(Btn, { onClick: copyUrl, children: copied ? 'Copied' : 'Copy URL' }),
                      jsx('span', { style: S.spacer }),
                      jsx('span', { style: S.note, children: `listening on ${pending.listening_on}` })
                    ]
                  }),
                  jsx('p', {
                    style: S.note,
                    children:
                      'If Reddit cannot reach the local catcher, approve anyway and paste the full URL you land on below.'
                  }),
                  jsxs('div', {
                    style: S.row,
                    children: [
                      jsx(Input, {
                        className: 'font-mono flex-1 min-w-0',
                        onChange: event => setPaste(event.currentTarget.value),
                        placeholder: 'http://localhost:8080/?code=…&state=…',
                        size: 'sm',
                        value: paste
                      }),
                      jsx(Btn, { busy: busy === 'Finishing', onClick: finishLogin, children: 'Finish login' })
                    ]
                  })
                ]
              })
            : null,

          jsxs('div', {
            style: S.row,
            children: [
              jsx(Btn, {
                busy: busy === 'Starting',
                onClick: startLogin,
                primary: !connected,
                title: configured ? '' : 'Save your app credentials first',
                children: connected ? 'Log in again' : 'Log in'
              }),
              jsx(Btn, { busy: busy === 'Checking', onClick: verify, children: 'Check account' }),
              jsx('span', { style: S.spacer }),
              jsx(Btn, { busy: busy === 'Logging out', onClick: logout, children: 'Log out' })
            ]
          }),

          identity?.logged_in
            ? jsxs('div', {
                style: S.row,
                children: [
                  jsx(Tag, { children: `u/${identity.username}` }),
                  jsx(Tag, { children: `${identity.link_karma} link karma` }),
                  jsx(Tag, { children: `${identity.comment_karma} comment karma` }),
                  identity.is_mod ? jsx(Tag, { children: 'moderator' }) : null
                ]
              })
            : null,

          jsx('p', { style: S.note, children: `Refresh token: ${status?.token_file || '$HERMES_HOME/reddit-oauth.json'}` })
        ]
      }),

      jsx(Field, { label: 'Local library account', value: accountDraft, onChange: setAccountDraft, placeholder: 'local', hint: 'Type a namespace, then press Use account. Network actions require the connected account.' }),
      jsx(Btn, { onClick: () => setLibraryAccount(accountDraft.trim()), children: 'Use account' }),
      jsx(RedditLibrary, { ctx, account: libraryAccount || 'local' }, libraryAccount || 'local'),
      jsx('p', {
        style: S.note,
        children:
          'The same settings are available from a terminal: hermes reddit setup, login, status and logout.'
      })
    ]
  })
}

export default {
  id: PLUGIN_ID,
  name: 'Reddit',
  description: 'Reddit app credentials, OAuth login and account status in Settings ▸ Plugins.',
  register(ctx) {
    if (typeof ctx.registerSettingsPage === 'function') {
      ctx.registerSettingsPage({
        icon: 'comment-discussion',
        id: 'setup',
        order: 120,
        render: () => jsx(RedditSettingsPage, { ctx }),
        title: 'Reddit'
      })
    }

    ctx.register({
      id: 'reddit-open-settings',
      area: PALETTE,
      data: {
        id: 'reddit.settings',
        label: 'Reddit: setup and login',
        keywords: ['reddit', 'oauth', 'login', 'client id', 'api'],
        run: () => {
          if (typeof host.navigate === 'function') host.navigate(SETTINGS_HREF)
        }
      }
    })
  }
}
