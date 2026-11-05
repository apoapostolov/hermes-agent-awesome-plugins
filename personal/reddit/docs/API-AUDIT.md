# Reddit plugin and API audit

Reviewed November 5, 2026. Scope: the installed Hermes Agent plugin and its matching source under `workstation/plugins/reddit`. The baseline was plugin 1.0.1 with thirteen tools and 58 passing offline tests. Version 1.1.0 adds nine tools, a local library, a Desktop browser, maintenance and CLI workflows. The standalone release provides 22 tools.

## Main finding

The plugin already had working account OAuth, application-only OAuth, public reading, posting and a generic API tool. Its main functional gap was retrieval and organization of saved content: saving an item on Reddit did not produce a local, searchable record of its contents or why it mattered.

That gap can be addressed now, but Reddit's API transition materially limits the long-term design. Reddit announced that new public API requests closed October 31, 2026, unregistered access removal starts January 12, 2027, and all remaining public access ends in March 2027. Existing credentials working today do not establish continued access after those dates. [Reddit's migration announcement](https://www.reddit.com/r/redditdev/comments/1wubcvf/moving_data_api_apps_to_the_developer_platform/).

Devvit explicitly withholds personal saved items, subscriptions and voting history. Moving the same methods to a Devvit server therefore cannot preserve this plugin's personal-library synchronization. This is a documented platform gap, not a missing wrapper in the Python code. [Devvit private user data](https://developers.reddit.com/docs/capabilities/server/reddit-api#private-user-data).

## Anonymous, app-only and account access

| Mode | Authentication | Useful access | Important limit |
| --- | --- | --- | --- |
| No credentials | No OAuth token | Local library operations | Public `.json` scraping is not the supported fallback |
| App-only OAuth | Registered application's client credentials | Public posts, communities, threads and available public user history | No personal saves, inbox or account writes |
| User OAuth | App credentials plus the user's authorization and refresh token | Personal listings, accessible private communities and permitted writes | Each endpoint still requires scopes and account permissions |
| Moderator OAuth | User OAuth for an account with moderator permissions | Permitted queues, moderation actions, modmail and wiki/configuration work | Requesting moderator scopes does not make an account a moderator |
| Devvit | Reddit-managed app authentication | Community app behavior through the supported Devvit client | Does not expose the personal data needed by this library's sync |

Application-only OAuth is authenticated access without a user context. The legacy OAuth guide describes client-credentials grants for confidential applications and a separate installed-client grant for installed applications. User authorization uses a code exchange; permanent authorization supplies a refresh token, and subsequent access tokens are short-lived. This plugin supports a confidential web app with a loopback callback, not every app type. It does not collect passwords or implement the password grant. [Reddit's OAuth guide](https://github.com/reddit-archive/reddit/wiki/OAuth2).

Reddit's current policy requires approved access, accurate identification and respect for usage limits. It also describes registration and transparency requirements for apps and AI agents. API credentials and an account name alone do not prove that a proposed new use case has approval. The implementation does not attempt to evade restrictions through cookies, account rotation or alternate scrape hosts. [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).

## Rates and account information

Eligible free OAuth access is published as 100 requests per minute per client ID, averaged over a ten-minute window. Both app-only and account tokens use OAuth; logging in does not create a separate published allowance per person. A truthful User-Agent with the operator's username identifies the client, but is not an authentication grant or quota purchase. Unauthenticated traffic has no reliable current API allowance. Do not reuse the old 2023 claim of ten anonymous requests per minute as a present guarantee. [Current Data API guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki).

Live checks verified account and app-only public reads. Response headers are observed window state, not a promised requests-per-minute entitlement. No remote content was written during validation.

The updated client reads rate headers, remembers an exhausted budget in its process, retries short 429 windows, and reports longer delays without shortening them. Processes for the same OS user now share a locked client-ID request budget and space requests; profile-locked access caching also avoids duplicate token refreshes. Account age, karma and community rules can also restrict actions independently of transport quota; the plugin cannot promise that authentication removes posting restrictions.

`reddit_status` exposes identity, granted scopes, safe credential state, rate headers and transition dates. `reddit_setup(contact_username=...)` can set an accurate contact User-Agent without replacing the app ID or secret. Prefer the Desktop form or hidden CLI prompt for secrets so they do not enter chat transcripts or shell history.

## API coverage

The following map describes the documented Data API, not a guarantee that every historical endpoint remains available to every client. The generic tool preserves access where dedicated wrappers are absent. [Endpoint and scope reference](https://www.reddit.com/dev/api/oauth).

| Operation | Representative endpoint | Access/scope | Plugin surface |
| --- | --- | --- | --- |
| Public reading | `/r/{name}/new`, `/comments/{id}`, `/api/info` | `read` | Subreddit, thread, content |
| Search | `/search` | `read` | Search; link, community and user results |
| Personal history | `/user/{name}/saved`, `/hidden`, `/upvoted`, `/downvoted` | User, `history` | Account and library sync |
| Identity/preferences | `/api/v1/me`, `/api/v1/me/prefs` | User, `identity` / `account` | Account/status |
| Saves | `/api/save`, `/api/unsave` | User, `save` | Manage |
| Publishing | `/api/submit`, `/api/comment` | User, `submit` | Submit/comment |
| Editing/deletion | `/api/editusertext`, `/api/del` | User, `edit` | Content |
| Voting | `/api/vote` | User, `vote` | Vote |
| Subscriptions | `/api/subscribe`, `/subreddits/mine/subscriber` | User, `subscribe` / `mysubreddits` | Manage/account |
| Reports/hiding | `/api/report`, `/api/hide`, `/api/unhide` | User, `report` | Content/manage |
| Messages | `/message/inbox`, `/api/read_message` | User, `privatemessages` | Inbox/messages |
| Moderation | `/about/modqueue`, `/api/approve`, `/api/remove` | Moderator, `modposts` | Moderation |
| Modmail | `/api/mod/conversations` | Moderator, `modmail` | Raw API |
| Wiki | `/wiki/pages`, `/wiki/page/{page}` | `wikiread`; writes `wikiedit` / `modwiki` | Wiki |
| Flair/multis | `/api/link_flair_v2`, `/api/multi/mine` | `flair` / `read` and applicable permissions | Community/custom feeds |

The baseline advertised global comment search with `type=comment`, although that result type is absent from the documented search contract. The wrapper now rejects it and directs the caller to local saved-comment search. Search and public-user listings now expose continuation cursors.

Listing limits and cursors make bounded retrieval possible; they do not constitute an archival export contract. The library reads at most ten pages per sync call, supports continuation and never infers an unsave from absence. Thread expansion is also bounded: the existing reader makes one extra `morechildren` request and returns a capped excerpt, rather than claiming a complete discussion. Historical scope names such as awards-related scopes do not prove the associated product still exists.

## Implemented local library

The SQLite database lives in `plugin-data/reddit/library.sqlite3` under the active Hermes home. It uses account namespaces, transactions, a busy timeout and secure deletion. It stores selected source fields rather than raw API responses, and never stores access tokens, refresh tokens or app secrets.

`reddit_library` provides sync, capture, get, annotate, refresh, remove, stats and purge. `reddit_library_search` searches titles, body text, source excerpts, summaries, context, notes, authors, subreddits and tags. Queries support literal AND terms, quoted phrases, exclusions, metadata filters and pagination. Title and summary/context matches receive higher rank. The search normalizes Unicode case and uses bound SQL parameters. It scans normalized text within the selected account; it is not a vector index or an FTS5 implementation.

Posts and comments are identified by validated fullnames or canonical Reddit URLs. Ambiguous share links and arbitrary external URLs are rejected. Body snapshots are capped at 40,000 characters and report truncation. Search results shorten body previews; `get` returns the stored snapshot. No external article fetch occurs.

An initial extractive excerpt provides immediate searchable context without a model call. Agent/user summaries are explicitly labeled and can be written alongside the reason for saving and tags. Unchanged sources preserve annotations; changed source text invalidates them. A saved comment records its own text and structural parent/thread IDs. It does not borrow other comments' text without tracking their lifecycle.

Remote save and local capture have separate outcomes. A successful Reddit save followed by a failed local read reports the remote success and a local error. Unsave retains a local bookmark and updates its known remote state. Local removal does not unsave on Reddit. Explicit content edits or deletion clear cached copies so old text cannot continue appearing in local search.

## Retention and deletion limits

Reddit requires deletion of removed source content and author-identifying information for deleted accounts; its guidance recommends routine deletion within 48 hours. Keeping a derived summary is not an exception to source deletion. [Retention guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki).

The implementation expires source snapshots and all annotations after 48 hours without a successful fetch. It leaves content-free bookmark identifiers for later refresh. Revalidation removes inaccessible items only from the current account. Confirmed deleted or removed source text is purged across copies. A malformed response or transport failure does not count as an empty result and does not erase the library. Author redaction is not treated as proof of account deletion. Only the affected source is removed; unrelated saves remain.

Expiry runs on library access. Hosts with unload support also run cleanup every minute while the plugin is loaded; older hosts use on-access cleanup. Optional online revalidation is off by default and checks at most 100 known bookmarks per 30 minutes. Stopped Hermes cannot physically delete expired bytes, so strict wall-clock retention across process downtime needs an external maintenance process. Filesystem backups are outside SQLite's deletion control and should not retain expired Reddit content. This implementation reduces retention risk; it is not a claim that every deployment automatically satisfies every Reddit obligation.

The current implementation stores annotation text with the source lifecycle. It does not provide permanent notes that might preserve deleted Reddit content. The content database is not encrypted. New credential files and access-cache tokens use authenticated encryption. Windows protects the key with DPAPI; other platforms store it separately with private file permissions.

## Defects fixed in this audit

| Finding | Baseline behavior | Local change |
| --- | --- | --- |
| Subreddit subscriptions | Sent a name using the fullname-only `sr` field | Names use `sr_name`; fullnames keep `sr` |
| Operation failures | Several tools reported success for HTTP 200 responses containing Reddit errors | Central request handling rejects `json.errors` |
| Long rate windows | A long reset was capped to 30 seconds, permitting an early retry | Return the actual delay when too long to wait inline |
| DELETE parameters | Form data was discarded | Form body is retained |
| Application-only writes | A write could request an app-only token | Rejected before transport |
| Callback port | Default 8080 could ignore the configured redirect port | Listener follows the configured port |
| Manual OAuth state | Missing state could bypass comparison; separate CLI calls lost pending state | Persist an expiring state and require exact state on completion |
| Callback output | An OAuth error could be inserted into HTML without escaping | Error text is escaped |
| Local organization | No searchable local saved-content store | Library, source lifecycle and context search |

## Follow-up implementation and remaining dependencies

The release adds a profile-bound maintenance worker, opt-in bounded revalidation, shared client-ID rate coordination, locked token refresh/access caching, a source-hash checked summary queue, read status, identifier-only bookmark transfer and a Desktop library browser. Dedicated moderation, message-state, wiki and custom-feed tools cover the management recommendations. New credential writes use authenticated Fernet encryption; Windows protects the key with DPAPI. Existing files can be migrated with the secure command.

Two external dependencies remain. Reddit must provide a supported route for the personal data excluded from Devvit; a local implementation cannot create that permission. Separately, Hermes catalog rule 11 requires host-managed OAuth, but its current plugin route lacks Reddit's client-secret Basic authentication, fixed callback declaration and form-body request transport. Existing [issue #142687](https://github.com/NousResearch/hermes-agent/issues/142687) tracks the authentication/redirect gap. See [LIMITATIONS.md](../LIMITATIONS.md) for the listing prerequisites. This release remains standalone and unlisted.

Embedding search, full-thread ingestion and linked-article ingestion are not included. They would require additional source-dependency tracking and deletion propagation. Identifier-only transfer is deliberately narrower than a permanent content archive or Reddit account-export importer.

## Validation

All 123 offline tests pass, compared with 58 before changes. The expanded suite covers source expiry and removal from SQLite bytes, annotations, account/profile separation, Unicode and literal search, concurrent local writes, sync continuation, malformed responses, partial save success, URL validation, OAuth state and port selection, HTTP 200 operation errors, DELETE bodies and long rate windows.

Live validation verified account and app-only reads, personal saved items, karma, community rules and post requirements. Bounded saved-item sync and offline search were verified. Remote posting, voting, editing and deletion were not performed against the user's account; write transport and error handling were checked offline.
