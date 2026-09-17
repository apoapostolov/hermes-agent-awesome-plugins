<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>RSS Reader</h1>
  <strong>A calmer place for the stories you mean to finish.</strong>
  <p>Read, organize, search, summarize, and investigate RSS and Atom feeds without turning your reading list into another job.</p>
  [![Hermes Desktop](https://img.shields.io/badge/Hermes%20Desktop-plugin-6f42c1)](https://github.com/NousResearch/hermes-agent) [![Version](https://img.shields.io/badge/version-1.0.1-2ea44f)](plugin.yaml) [![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)
</div>

[Install it](#install) · [See what it does](#what-it-does) · [Understand the data](#privacy)

## What it does

RSS Reader gives Hermes a focused three-column reading space:

- **Read.** Subscribe to RSS 2.0 and Atom feeds, Reddit `r/...` communities, search your library, and open original articles.
- **Start quickly.** Use the Subscribe starter pills for Newswire sources and popular Reddit communities.
- **Organize.** Create folders and nested folders, move feeds between them, and remember open or closed state.
- **Protect attention.** Use unread, saved, feed, folder, mute, and search views without losing the article you are reading.
- **Capture articles.** Fetch full articles through the Python API and keep useful images and tables in reader mode.
- **Use Hermes deliberately.** Start summaries, discussions, evidence checks, digests, and optional grading only when you ask.

## Install

Install the plugin from the community pack:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/plugins/rss-reader
```

Enable **RSS Reader** under **Capabilities → Plugins**, add a feed URL, and press **Refresh**.

## First use

1. Add a direct RSS or Atom feed URL, or paste a Reddit community URL such as `https://www.reddit.com/r/programming`.
2. Use a starter pill to fill a Newswire or Reddit source quickly, then add it like any other subscription.
3. Refresh the library.
4. Select a story and choose Open, Save, Capture, Summary, Evidence, or Discuss.
5. Enable subscription edit mode to create folders, subfolders, and feed moves.

In Unread view, a selected story is marked read after one second but remains visible until focus moves to another story. Normal views keep immediate marking behavior.

## `/rss` commands

```text
/rss refresh
/rss add https://example.com, Example feed
/rss mute phrase
/rss mark-read all
/rss digest unread 7d
/rss health
```

The command queue is profile-aware and uses the same local library as the desktop page.

## Privacy

```text
Your Hermes Desktop → local RSS library → your configured provider when you ask
```

Subscriptions, articles, read state, saved state, summaries, and folders stay in the local library. Feed and article URLs use the Python API, which validates public HTTP(S) destinations, rejects embedded credentials, blocks private hosts, follows bounded redirects, and caps response size. AI actions receive only the selected or bounded article context.

## Limits

- Feed and article downloads are bounded by the Python API.
- An entry may contain only an excerpt; full capture depends on the original page.
- Images with a largest intrinsic or declared dimension of 480 px or less stay capped and float beside text. Larger images keep the reading width.
- Saved stories survive feed removal. Paywall bypass services are not used.

## Development

- `desktop/plugin.js`: reader UI and Hermes actions
- `dashboard/plugin_api.py`: feed, article, grading, and preference routes
- `dashboard/manifest.json`: API registration
- `scripts/test-pure.mjs` and `tests_commands.py`: local checks

Licensed under [MIT](../../LICENSE). This is an independent community plugin inspired by [`Adolanium/hermes-rss`](https://github.com/Adolanium/hermes-rss).
