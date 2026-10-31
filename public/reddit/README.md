# Reddit

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Reddit" />
</div>

Reddit with your own account behind it. You register one Reddit API app, paste its
client id and secret once, log in through Reddit's own consent page, and from then
on the agent talks to the full Reddit API as you.

Reads use your account token, so private subreddits, saved items, moderation queues
and the inbox are reachable. Writes publish under your account.

## Before you start

Create a Reddit app at <https://www.reddit.com/prefs/apps>:

1. **create another app** at the bottom of the page
2. type **web app**
3. redirect uri: `http://localhost:8080`
4. copy the client id (the short string under the app name) and the secret

Reddit's app settings are the authority here: the redirect uri in step 3 must match
what you configure below, character for character.

## Setup

```bash
hermes reddit setup          # prompts for client id, secret and redirect uri
hermes reddit login          # prints a consent URL, waits for the callback
hermes reddit status         # account, scopes, token file, rate limits
hermes reddit logout         # delete the stored refresh token
```

**In Desktop:** Settings ▸ Plugins ▸ Reddit is the same setup as a form — client
id, secret, redirect uri and user agent with a Save & verify button, then Log in,
Check account and Log out. Log in opens Reddit's consent page in your browser; the
page finishes the exchange by itself and also accepts a pasted redirect URL when
the local catcher cannot be reached.

From chat, the same steps are the `reddit_setup` and `reddit_login` tools. Setup
validates the credentials with a read-only request before saving them.

### Stored credentials

Everything stays on your machine:

- `$HERMES_HOME/reddit-config.json` — client id, secret, redirect uri, user agent
- `$HERMES_HOME/reddit-oauth.json` — refresh token, granted scopes, account name

Both files are chmod 600 where the platform allows it and are the only sources the
plugin reads. It never reads environment variables or `.env` files for credentials:
one Hermes process can serve several profiles, and an environment read can pick up
another profile's values.

### Network and token handling

The plugin talks to `www.reddit.com` (OAuth endpoints) and `oauth.reddit.com` (the
API) with the app and account you authorized. Access tokens live one hour; the
plugin refreshes them from your stored refresh token when fewer than 90 seconds
remain. Calls share one session per Hermes process, so a refresh serves several
tool calls, and the token file is rewritten only when the granted scopes change.
Nothing is sent anywhere else, and there is no telemetry.

## Login

The plugin runs the authorization-code flow with `duration=permanent` and catches the
callback on `http://localhost:8080`. A refresh token is stored, and access tokens are
renewed automatically when fewer than 90 seconds remain.

If the browser cannot reach the local catcher, approve anyway and finish manually:

```bash
hermes reddit complete "http://localhost:8080/?code=...&state=..."
```

`reddit_login` accepts the same redirect URL through `action='complete'`.

## Tools

| Tool | Purpose |
| --- | --- |
| `reddit_setup` | show or save your Reddit app credentials |
| `reddit_login` | `start`, `status`, `complete`, `logout` |
| `reddit_status` | login state, scopes, identity, karma, rate headers |
| `reddit_api` | any endpoint on `oauth.reddit.com`: mod, wiki, flair, modmail, prefs |
| `reddit_subreddit` | listings: hot, best, new, top, rising, controversial |
| `reddit_search` | posts, comments or subreddits, optionally inside one subreddit |
| `reddit_thread` | one post with its comment tree |
| `reddit_submit` | create a self or link post |
| `reddit_comment` | reply to a post, comment or private message |
| `reddit_vote` | upvote, downvote or clear |
| `reddit_manage` | save, unsave, subscribe, unsubscribe, hide, unhide |
| `reddit_inbox` | unread, inbox, sent, mentions, modmail |

`reddit_api` is the escape hatch for the rest of the API:

```bash
hermes reddit api GET /api/v1/me
hermes reddit api GET /subreddits/mine/moderator --param limit=10
hermes reddit api POST /api/distinguish --data id=t1_abc --data how=yes
```

## Scopes

Login requests every scope the account can grant. The list mirrors `GET /api/v1/scopes`
and is pinned by a test, because a name that does not exist fails the whole consent
page with `invalid scope requested`. Ask for less with `--scope "read identity"`.

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `invalid redirect_uri parameter` | the app's registered redirect uri differs from the one configured here |
| `invalid scope requested` | a scope name Reddit does not have; compare with `GET /api/v1/scopes` |
| consent page bounces to login | normal: Reddit only validates redirect and scope after login |
| `invalid_grant` on a password flow | 2FA on the account or a non-script app; use this OAuth flow |
| no refresh token returned | the app grant was not permanent; re-run login |
| `403` on a call | the token lacks that scope, or the account cannot do it |

## Tests

```bash
uv run --with pytest python -m pytest tests -q
```

Offline only: no network, no real credentials.

## Layout

- `client.py` — config and token storage, refresh, request helpers, listing compaction
- `login.py` — loopback OAuth catcher and code exchange
- `tools.py` — tool schemas and handlers
- `cli.py` — `hermes reddit` subcommands
