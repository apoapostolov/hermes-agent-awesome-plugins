![Hermes Agent](https://raw.githubusercontent.com/NousResearch/hermes-agent/main/assets/banner.png)

# RSS Reader

**A calmer place for the stories you mean to finish.**

[Install it](#install) · [See what it does](#rss-with-an-agent-in-the-room) · [Understand the data](#privacy-you-can-explain-in-one-breath)

[![Hermes Desktop](https://img.shields.io/badge/Hermes%20Desktop-plugin-6f42c1)](https://github.com/NousResearch/hermes-agent)
[![Version](https://img.shields.io/badge/version-1.0.1-2ea44f)](plugin.yaml)
[![License](https://img.shields.io/badge/license-MIT-green)](../../LICENSE)

## RSS with an agent in the room

RSS Reader turns a noisy collection of feeds into a focused three-column reading space for Hermes Desktop. Keep subscriptions organized, read articles locally, and bring Hermes into the story when you want a summary, a discussion, a source check, or a grading pass.

The reader stays quiet until you ask it to do more. AI actions are explicit and use your configured Hermes providers.

|  |  |
| --- | --- |
| **Read.** Subscribe to RSS 2.0 and Atom feeds, search your library, and open the original article. | **Organize.** Group feeds into folders, create nested folders, drag feeds between folders, and reorder subscriptions. |
| **Understand.** Ask Hermes for a short summary with supporting passages, or check claims against sources. | **Keep your attention.** Use unread, saved, feed, folder, mute, and search filters to decide what deserves attention next. |

## Less feed maintenance. More finishing.

RSS Reader handles the small decisions that make a reader pleasant to return to:

- **Folders that stay organized.** Create folders such as `News/AI`, collapse the ones you do not need, and keep that open or closed state across Hermes sessions.
- **A better unread queue.** Selecting an unread article does not remove it from the list immediately. It is marked read after a short delay and leaves the list when you move to another post.
- **Reader-mode articles.** Fetch the full article through the RSS Reader Python API, keep useful images and tables, and read it without leaving Hermes.
- **Explicit AI actions.** Summarize an article, discuss it in Hermes, check its sources, or run optional importance grading when you choose.
- **Mute rules that remember scope.** Mute phrases across all feeds, one feed, or selected folders while keeping saved articles in your library.
- **A library you can search.** Search article titles and captured text, save stories, mark feeds or the whole library read, and keep saved stories when unsubscribing.
- **Keyboard navigation.** Use Google Reader style `j` and `k` navigation, `s` to save, and `d` to discuss. Shortcuts stay out of the way while you type.
- **OPML portability.** Import and export your feed collection, including nested folder outlines.

## Make it yours

### Install

Install the plugin from the community pack:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/plugins/rss-reader
```

Then enable **RSS Reader** in Hermes Desktop under **Capabilities → Plugins**. Open the RSS Reader page, add a feed URL, and press Refresh.

The public pack source is [`plugins/rss-reader`](https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/plugins/rss-reader). The plugin includes a Python dashboard API for feed, article, grading-skill, and preference-file operations. Feed and article downloads do not run local PowerShell or shell commands.

### First use

1. Add a direct RSS or Atom feed URL.
2. Press **Refresh** to fetch its entries.
3. Select a story in the middle column.
4. Use the article actions for Open, Save, Capture, Summary, Evidence, or Discuss.
5. Turn on edit mode in the subscriptions panel to create folders, create subfolders, rename folders, delete folders, reorder feeds, or drag feeds into a different folder.

## `/rss` commands

The plugin also registers a `/rss` command family:

```text
/rss refresh
/rss refresh 30m
/rss add https://example.com, Example feed
/rss mute phrase
/rss mark-read all
/rss mark-read folder News
/rss digest unread 7d
/rss digest saved
/rss health
/rss refine 30d
```

Refresh periods, mutes, digests, health reports, and grading refinement use the profile-aware RSS command queue. The desktop reader consumes those requests through the same local library used by the page.

## AI, when you ask

Summaries, discussions, source checks, digests, and optional grading use your configured Hermes model and search providers. Article context is sent for the action you start. Normal reading stays local after the feed or article has been fetched.

Source checks are evidence-gathering conversations. They are not automatic truth scores. AI provider usage follows your configured provider and account.

AI grading is optional. When enabled, it reads the selected grading skill through the Python plugin API, grades article title and feed text in bounded batches, and caches valid results by article identity. The grading prompt treats feed content as untrusted source data and does not follow instructions found inside articles.

## Privacy you can explain in one breath

```text
Your Hermes Desktop → local RSS library → your configured provider when you ask
```

Subscriptions, articles, read state, saved state, summaries, and folder assignments live in the local RSS library. Data is scoped to the active Hermes connection and profile. This plugin does not sync the library to another device.

- **Local reading.** The reader displays feed and captured text without active scripts.
- **Bounded context.** AI actions receive the selected article or the bounded set needed for a digest or grading pass.
- **Safer fetching.** Feed and article URLs use the Python API, which validates public HTTP(S) destinations, rejects embedded credentials, blocks private hosts, follows bounded redirects, and caps response size.
- **Separate storage writes.** Grading skills and preference reports use allowlisted Python API routes. The desktop grading path contains no PowerShell, `-EncodedCommand`, or `shell.exec` transport.
- **Clean removal.** Removing the plugin does not intentionally erase the local library or Hermes conversations.

## Limits and behavior

- RSS Reader accepts RSS 2.0 and Atom feeds.
- Feed downloads and article downloads are bounded by the Python API.
- An RSS entry may contain only an excerpt. Full article capture depends on the original page being readable.
- Small full-article images with an intrinsic or declared largest dimension of 480 px or less stay capped at 320 px and float beside the text. Larger images keep the full reading width.
- Unread selection uses a 1-second read timer. The selected story stays in the unread list until focus moves to another story.
- Saved stories are kept when a feed is unsubscribed. Unsaved history follows the library retention rules.
- Paywall-bypass services are not used as capture fallbacks.

## Development

The desktop implementation is [`desktop/plugin.js`](desktop/plugin.js). The Python API is [`dashboard/plugin_api.py`](dashboard/plugin_api.py). The dashboard manifest is [`dashboard/manifest.json`](dashboard/manifest.json).

Run the local checks from the repository root:

```bash
cp plugins/rss-reader/desktop/plugin.js "$LOCALAPPDATA/Temp/rss-reader-check.mjs"
node --check "$LOCALAPPDATA/Temp/rss-reader-check.mjs"
node plugins/rss-reader/scripts/test-pure.mjs
python plugins/rss-reader/tests_commands.py
python -m py_compile plugins/rss-reader/dashboard/plugin_api.py
```

The plugin is an independent community project inspired by the upstream [`Adolanium/hermes-rss`](https://github.com/Adolanium/hermes-rss) design and implementation. Upstream is the reference for the original catalog plugin. This pack adds the local API transport, profile-aware library workflows, nested folder management, and the reader behavior described above.

## License

MIT. See [`LICENSE`](../../LICENSE).

RSS Reader is an independent community plugin. It is not affiliated with, endorsed by, sponsored by, or officially associated with Nous Research or the Hermes Agent project. Hermes, Hermes Agent, and Nous Research are names and marks belonging to their respective owners.
