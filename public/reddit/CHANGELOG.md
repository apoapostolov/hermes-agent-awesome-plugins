# Changelog

## [reddit 1.0.1] - 2026-11-02

### Added

- `reddit_user` reads one user's public posts and comments: overview, submitted
  or comments, with a sort and time-window option.
- Reads work without a login. When no account token is stored, the plugin asks
  Reddit for an app-only `client_credentials` token and reads public
  subreddits, search, threads and user pages with it. `reddit_status` reports
  `read_only: true`; writes and private data still require `reddit_login`.
- `reddit_thread` keeps the reply tree: every comment carries its `depth`, the
  response reports `hidden_comments` and where those comments sit in `more`, and
  `expand_more` (default true) fetches them from `/api/morechildren` into the
  same list.

### Fixed

- A `429` from Reddit no longer fails the call. The client waits the
  `Retry-After` / `X-Ratelimit-Reset` window once (at most 30 seconds) and
  retries, and reports what it waited in `reddit_status`'s rate headers.
- A thread read with more replies than the first page used to return an empty
  `{"kind": "more"}` stub with no count, no ids and no way to reach them.

## 1.0.0

First stable release. Same twelve tools, editions and login flow as 0.3.0.

### Fixed

- Saving credentials with verification reported a raw `urllib` or JSON exception
  when the app token was granted and the follow-up read failed (rate limit, an
  HTML error page, no network). It now reports what Reddit answered, or that the
  read could not reach Reddit, and says the credentials themselves were accepted.

## 0.3.0

First public release.

### Added

- Reddit login with OAuth: the authorization-code flow runs from chat, a
  command, or Settings > Plugins, with a loopback catcher on
  `http://localhost:8080`, a permanent refresh token, and automatic access-token
  renewal.
- Bring your own Reddit app. Client id, secret, redirect URI and user agent are
  stored per profile; setup verifies them against Reddit before saving.
- Tools for the whole API: `reddit_setup`, `reddit_login`, `reddit_status`,
  `reddit_api`, `reddit_subreddit`, `reddit_search`, `reddit_thread`,
  `reddit_submit`, `reddit_comment`, `reddit_vote`, `reddit_manage`,
  `reddit_inbox`.
- `reddit_api` for everything the curated tools do not cover: moderator queues,
  modmail, wiki, flair, multireddits and account preferences.
- Desktop settings page with credential form, login, account check and logout,
  served by the plugin's own backend at `/api/plugins/reddit/`. The page uses the
  plugin SDK's fields and buttons, so it follows the app theme.
- `hermes reddit setup|login|complete|status|logout|smoke|api` commands.

### Notes

- Reads use the account token, so private subreddits, saved items, moderator
  views and the inbox work. Writes publish under the logged-in account.
- The plugin requests every scope Reddit grants. Narrow it with `--scope`.
- No third-party dependencies.
