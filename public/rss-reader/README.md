<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>RSS Reader</h1>
  <strong>A three-column place for feeds you mean to finish.</strong>
  <p>Folders, mute and search, reader-mode capture, YouTube and Substack feeds, optional Hermes tools, and an optional headline ticker.</p>
  <p>
    <a href="https://github.com/NousResearch/hermes-agent"><img src="https://img.shields.io/badge/Hermes%20Desktop-plugin-6f42c1" alt="Hermes Desktop plugin" /></a>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.2.0-2ea44f" alt="Version 1.2.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="RSS Reader" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" alt="RSS Reader three-column layout with folders, article list, and reader pane" />
</div>

## What You Can Do

- Subscribe to RSS 2.0 and Atom feeds, plus Reddit `r/...` communities, YouTube channels and playlists, and Substack pages. Starter pills help fill common sources, including YouTube and Substack.
- Organize with folders and nested folders. Move feeds between them.
- Work from unread, saved, feed, folder, mute, and search views without losing the article you have open.
- Capture full articles into reader mode (images and tables kept when useful).
- Play YouTube posts in the reader with a 16:9 embed and chapter timestamps. Playlist feeds list oldest first.
- Set a User-Agent and optional YouTube cookies under Settings → Advanced.
- Ask Hermes for summaries, discussions, evidence checks, digests, and optional grading only when you choose.
- Optionally register Hermes tools so the agent can read, find, tag, filter, and manage subscriptions.
- Optionally show an animated headline ticker with grade colors and tag pills.
- Run a scheduled digest as an Automation Blueprint: `/blueprint rss-reader:daily-digest` picks the days, the time, and which articles, and delivers the digest where you set it up (also in the dashboard Blueprints tab and the Desktop Cron page).
- Post a digest straight into a Telegram or Discord chat with inline Save / Open / Mute feed buttons: `/rss digest-post [unread|saved|all]`.
- Drive the same local library from chat:

```text
/rss refresh
/rss refresh 30m
/rss mute phrase
/rss refine starred
/rss refine 30d
/rss add https://example.com, Example feed
/rss add r/programming
/rss mark-read all
/rss digest unread 7d
/rss digest-post unread
/rss health
/rss find …
/rss tag … / /rss untag …
/rss mute tag … / /rss unmute …
```

In Unread view, a selected story is marked read after one second but stays visible until focus moves. Other views mark immediately.

## Install

Requires [Hermes Agent](https://github.com/NousResearch/hermes-agent) **0.21.0 or newer**.

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

Or install just this plugin:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/rss-reader
```

Enable **RSS Reader** under **Capabilities → Plugins**, add a feed URL, and press **Refresh**.

## Requirements / Limits

Desktop reader plus a local Python API for feed, article, grading, and preference work.

- Subscriptions, articles, read/saved state, summaries, and folders stay in the local library.
- Feed and article downloads are bounded. Public HTTP(S) only; no embedded credentials; private hosts blocked.
- An entry may be excerpt-only; full capture depends on the original page.
- Small images (largest dimension 480 px or less) stay capped beside text. Larger images keep reading width.
- Saved stories survive feed removal. Paywall bypass services are not used.
- AI actions receive only the selected or bounded article context.

This plugin is a fork of [Adolanium/hermes-rss](https://github.com/Adolanium/hermes-rss) (MIT). Copyright notices are in [LICENSE](../../LICENSE).

The public edition does not use archive or proxy mirrors and does not submit a self-improvement prompt that edits the installed plugin. One disclosed exception to the SDK-only import rule: the interactive digest reads `gateway.session_context` to learn which chat a `/rss digest-post` command came from, the same read the core's own `/blueprint` command uses for its delivery origin. The import is guarded, and the command degrades to a plain text digest when the module is unavailable. Catalog rule 13 disclosure.

## License

[MIT](../../LICENSE)
