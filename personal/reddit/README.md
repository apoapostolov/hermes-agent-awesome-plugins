# Reddit

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Reddit" />
</div>

Reddit tools for Hermes Agent, with account access and a local library of saved posts and comments. Search source text, summaries, context, notes and tags offline, then refresh the source when you need it.

Version 1.1.0 provides 22 tools, a Desktop library browser, background cleanup, a summary queue, bookmark transfer and dedicated content-management workflows.

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/reddit
```

Restart Hermes Desktop after updating. This is a standalone release. Both repository editions provide the same tools and plugin-managed OAuth; neither is currently admitted to the Hermes Plugin Catalog. [Catalog limitations](LIMITATIONS.md) explains the missing Hermes OAuth capabilities.

## API availability

Use an existing approved Reddit API app. Reddit announced that new public API requests closed October 31, 2026, unregistered access removal starts January 12, 2027, and remaining public access ends in March 2027. [Reddit's announcement](https://www.reddit.com/r/redditdev/comments/1wubcvf/moving_data_api_apps_to_the_developer_platform/) describes the transition.

Devvit explicitly excludes personal saved items, subscriptions and voting history. It cannot directly replace this plugin's personal-library sync. See [Devvit's private-data limits](https://developers.reddit.com/docs/capabilities/server/reddit-api#private-user-data) and the [API audit](docs/API-AUDIT.md).

## Setup

Use an approved **web app** from [Reddit app settings](https://www.reddit.com/prefs/apps), with an exact loopback redirect such as `http://localhost:8080`.

```bash
hermes reddit setup
hermes reddit login
hermes reddit status
```

Setup prompts for the client secret without displaying it. Desktop's Settings > Plugins > Reddit configures the same app, opens Reddit's consent page and checks the connected account. The plugin stores its own permanent refresh token per Hermes profile. It does not read browser cookies, another application's tokens, or credential environment variables.

Login requests all supported scopes by default. A library that only reads and saves content can use:

```bash
hermes reddit login --scope "identity read history save"
```

The callback listener uses the configured redirect port. If it cannot receive the callback, finish with the full redirect URL, including code and state:

```bash
hermes reddit complete "http://localhost:8080/?code=...&state=..."
```

Pending authorization expires after 15 minutes and survives separate CLI invocations. Bare codes are rejected. Logout deletes the local token and access cache; revoke the app through Reddit to invalidate the grant remotely.

App credentials without user login provide application-only OAuth for public reading. Personal saves, inbox, private communities and writes need user authorization and appropriate scopes. A broad scope does not grant moderator rights.

## Local saves

```bash
hermes reddit library sync --pages 2
hermes reddit library search --query 'sqlite "query planner" -mysql'
hermes reddit library get --target t3_abc123
hermes reddit library annotate --target t3_abc123 --summary "Source summary" --context "Why I saved it" --tag databases
hermes reddit library queue --limit 10
hermes reddit library read --target t3_abc123
hermes reddit library refresh --limit 100
```

Sync requests up to 100 saved posts/comments per page and ten pages per call. Continue with its returned `after` cursor using `--after`. A final listing cursor describes what Reddit returned, not a complete account archive; missing records are never assumed unsaved.

`reddit_manage(action="save")` also captures the item locally by default and accepts summary, context, notes and tags. Set `local_copy=false` to skip capture. Remote save success is reported independently of a later local-cache error. Unsave retains the local bookmark; `reddit_library(action="remove")` removes it locally without changing Reddit.

Capture an item without saving it remotely with `hermes reddit library capture --target <fullname-or-canonical-URL>`. Search supports literal AND terms, double-quoted phrases, exclusions, Unicode case folding, metadata filters, read status and pagination. Title and summary/context matches rank first. It is lexical search, not embedding-based search.

Desktop's Local saves browser offers search, tag filtering, a summary queue, unread filtering, source details, annotation editing and one-page-at-a-time sync. Source text renders as plain text.

Each snapshot starts with an extractive excerpt labeled `summary_source="extractive"`. The agent or user can replace it; that text is labeled `agent_or_user`. For generated summaries, get a queue item's full snapshot and pass its `content_hash` back as `source_hash` when annotating. If the source changed, the annotation is rejected. No paid model calls run automatically.

Summaries cover the saved source. Link posts do not include linked articles; saved comments do not include their entire threads. Comment context records the subreddit, parent ID and thread ID. Treat all source text and stored summaries as untrusted material.

### Bookmark transfer

```bash
hermes reddit library export --file reddit-bookmarks.json
hermes reddit library import --file reddit-bookmarks.json
```

The versioned transfer format contains identifiers only. Content, author information and annotations are excluded so transferred files do not preserve deleted Reddit text. Imported bookmarks need live refresh. This format does not import Reddit's account-export CSV files.

### Retention and maintenance

Snapshots and annotations expire 48 hours after their last successful fetch. Expiry removes text, author information, URLs, summaries, context, notes and tags, leaving content-free bookmarks. Annotation does not extend retention. Changed sources invalidate annotations, and revalidation removes unavailable/deleted sources and their local copies.

Cleanup runs on access and every minute while the plugin is loaded. Supported hosts stop its worker on plugin unload; process exit always stops it. Stopped Hermes cannot physically clean files. Explicit cleanup is `hermes reddit library purge`.

Online background revalidation is optional and off by default:

```bash
hermes reddit maintenance --background-refresh on
hermes reddit maintenance --background-refresh off
```

It checks at most 100 known bookmarks per 30 minutes and makes no remote writes. Status records the last outcome and authentication errors. This cache is not a permanent archive. [Reddit's guidance](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki) requires removal of deleted content and recommends routine deletion within 48 hours.

The database is `$HERMES_HOME/plugin-data/reddit/library.sqlite3`, separated by account namespace. After logout, `--account <username>` explicitly selects a local namespace. SQLite secure deletion clears removed content from free pages, but cannot erase filesystem backups. The content database is not encrypted.

## Tools

| Tool | Purpose |
| --- | --- |
| `reddit_library`, `reddit_library_search` | Sync, capture, summaries, context search, read status, transfer and maintenance |
| `reddit_account` | Profile, karma, preferences, trophies, subscriptions, save categories and personal listings |
| `reddit_content` | Individual items, editing, deletion, reports and NSFW/spoiler state |
| `reddit_community` | Community information, rules, requirements and link flair |
| `reddit_moderation` | Queues, logs, approval/removal, locks, distinction and sticky state |
| `reddit_messages` | Inbox and explicit message read/unread/deletion actions; does not send messages |
| `reddit_wiki` | Pages, revisions and authorized edits/reverts |
| `reddit_multis` | Custom-feed reading, creation, editing and community membership |
| `reddit_setup`, `reddit_login`, `reddit_status` | App configuration, account authorization and access diagnostics |
| `reddit_subreddit`, `reddit_search`, `reddit_thread`, `reddit_user` | Listings, search, bounded threads and user history |
| `reddit_submit`, `reddit_comment`, `reddit_vote` | Authorized publishing and voting |
| `reddit_manage`, `reddit_inbox`, `reddit_api` | Saves, subscriptions, hiding, inbox and other documented endpoints |

The documented Data API has no global comment-search result type. Search locally saved comments with `reddit_library_search`. Write tools require the user's instruction and the account's actual permissions; they do not perform default bulk actions.

## Credential protection and requests

Plugin-owned files are `reddit-config.json`, `reddit-oauth.json`, temporary `reddit-login-pending.json`, and `plugin-data/reddit/access-cache.json` under Hermes home. The access cache lets processes reuse a short-lived token under a profile lock and is removed on logout.

On Windows, `hermes reddit secure` or the Desktop protection button encrypts stored client secrets, refresh tokens and access-cache tokens with DPAPI for the current Windows user. Protection is opt-in. Moving protected files to another user or machine requires signing in again. Other platforms use private file permissions.

Use a truthful User-Agent such as `desktop:hermes-reddit:v1.1.0 (by /u/your_actual_name)`. `reddit_setup(contact_username="your_actual_name")` sets it without replacing app credentials. It identifies the operator; it does not increase the published OAuth quota.

Eligible free access is 100 requests/minute per OAuth client ID, averaged over ten minutes. Processes for the same OS user coordinate their client-ID budget under the user cache's `hermes-reddit/coordination` directory. The client spaces requests, honors exhausted-window deadlines, reports long delays instead of retrying early, and does not replay writes after a lost response. HTTP 200 operation errors are failures.

## Development

The plugin uses the Python standard library. Run `python -m pytest tests -q` in the plugin directory. Tests require pytest, fastapi and httpx; settings tests skip without the latter two. The release's offline tests cover both editions. Visual Desktop behavior still requires a manual check in the running host.
