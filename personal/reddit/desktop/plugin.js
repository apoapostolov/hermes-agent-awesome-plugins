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
import { useCallback, useEffect, useState } from 'react'
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

function Btn({ busy, children, onClick, primary, title }) {
  return jsx(Button, {
    disabled: !!busy,
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
      const started = await rest('login/start', { method: 'POST', body: { port: 8080 } })
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
              'Create an app of type "web app" and set its redirect uri to exactly the value below. The client id sits under the app name; the secret is beside it.'
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
            hint: 'Reddit wants a descriptive UA, e.g. hermes-reddit/0.3 (by /u/yourname).',
            onChange: value => setField('user_agent', value),
            placeholder: 'hermes-reddit/0.3 (by /u/yourname)',
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
          jsx('p', { style: S.note, children: `Stored in ${status?.config_file || '$HERMES_HOME/reddit-config.json'}` })
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
