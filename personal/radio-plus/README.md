# Radio Plus

Live radio in the Hermes Desktop status bar. Radio Plus forks the bundled Radio
plugin and makes the station list yours: presets can be renamed or deleted, any
stream can be added by name and URL, and the picker searches three directories
instead of one.

Enable it in **Capabilities → Plugins**. Playback starts only when you press
Play.

## What it adds over Radio

- **An editable station list.** The shipped stations are seeded into plugin
  storage on first run. From then on the stored list is what the picker shows, so
  a rename or a delete survives a restart and does not come back.
- **Row controls.** Hover a station and use the pencil to rename it inline, or the
  bin to delete it. Deleting takes two clicks and disarms itself after four
  seconds. Deleting the station that is playing moves playback to the next one;
  deleting the last one stops the player. A pin is removed with its station.
- **Add station.** Enter a name and any `http` or `https` stream address, for
  example a station's `.mp3` or `/;` endpoint from its own site. The name is
  optional: the host is used when it is blank. A duplicate URL reports that it is
  already in the list instead of adding the same stream twice.
- **Three sources** in one row of chips:
  - **All**: your stations plus a name search of [Radio Browser](https://api.radio-browser.info/).
  - **Popular**: Radio Browser's most-voted stations, filtered as you type.
  - **Shoutcast**: the [Shoutcast](https://directory.shoutcast.com/) directory,
    searched by station, genre, or keyword. With an empty search box it lists the
    busy end of the directory, so the chip works as a shortcut into Shoutcast
    without typing anything.

The status bar, the braille waveform, artist links, volume, and next-station
cycling behave as they do in Radio. Next walks pins and the stored list.

## How the Shoutcast source works

The Shoutcast directory sends no CORS headers and rejects `OPTIONS` with 405, so
the renderer cannot call it. Radio Plus ships one backend route for it,
mounted at `/api/plugins/radio-plus/`:

| Route | Purpose |
| --- | --- |
| `GET /shoutcast/search?q=<term>&limit=40` | Keyword search of the directory |
| `GET /shoutcast/top?limit=40` | Popular stations, busiest first |

The route performs the two requests the Shoutcast site performs for itself
(`POST /Search/UpdateSearch`, `POST /Home/Top`). Directory rows carry no stream
address, so each station's PLS tune-in file is resolved server-side, twelve at a
time, and stations whose tune-in file is empty are dropped rather than listed as
rows that cannot play. Resolved addresses and query results are cached in memory
for a few minutes. No key, account, or credential is involved, and nothing is
written to disk.

Because a search resolves its stations before answering, the first Shoutcast
search takes around a second. Later searches of the same term come from cache.

## Install

The plugin has two halves that must both be present:

```
$HERMES_HOME/plugins/radio-plus/          plugin.yaml, __init__.py, dashboard/
$HERMES_HOME/desktop-plugins/radio-plus/plugin.js
```

```
hermes plugins enable radio-plus
```

The renderer half reloads on the in-app toggle or an app restart. **The Shoutcast
source needs the app restarted once after enabling**, because the dashboard mounts
plugin routes at startup; until then the chip reports that Shoutcast is
unavailable. Everything else works without the route.

## Plugin boundary

`desktop/plugin.js` imports only `@hermes/plugin-sdk`, `react`, and
`react/jsx-runtime`. The Python half registers no tools, hooks, or middleware:
`__init__.py` exists because the loader owns the plugin directory, and
`dashboard/plugin_api.py` is mounted by the dashboard web server.

Playback, timers, audio nodes, and the injected stylesheet are released on
disable. Closing the window stops playback; there is no background audio service.
Other windows pause when one window starts playing.

## Audio and privacy

Streams connect directly to broadcasters. Searches send the typed term to Radio
Browser, or to the Shoutcast directory through the local plugin route. There are
no accounts, keys, analytics, recording, or rebroadcasting. Disabled plugins
perform no work; enabling does not autoplay.

Station streams are allowed over plain `http` as well as `https`, because the
Shoutcast directory serves many stations that way. Website and artist links still
require `https`. Streams are loaded by an `<audio>` element and never fetched with
credentials.

## Limitations

- HLS streams are skipped, as in Radio.
- Shoutcast resolution depends on the station's PLS file being populated. A
  station that is listed but has no tune-in address does not appear.
- Waveform analysis needs CORS on the stream itself. A station that refuses it
  plays without a waveform and shows an activity indicator instead of invented
  levels; Shoutcast streams usually take this path.
- Radio Browser and Shoutcast results are shown as found. Availability, regional
  restrictions, and metadata quality are theirs.

## Tests

```
py -m pytest tests/test_plugin_api.py -q            # mapping rules, offline
RADIO_PLUS_LIVE=1 py -m pytest tests/test_plugin_api.py -q   # + live Shoutcast
node tests/desktop.test.mjs                          # renderer logic, live Radio Browser
```

The renderer suite imports `desktop/plugin.js` through generated SDK stubs, then
exercises the real code: URL rules, seeding, rename, delete, add, and the two
source fetchers.

## References

- Forked from the bundled Radio plugin in `apps/desktop/src/plugins/radio` (MIT,
  Nous Research). The waveform, artist-link, and transport code is unchanged.
- [Radio Browser API](https://api.radio-browser.info/)
- [Shoutcast directory](https://directory.shoutcast.com/)

No upstream assets or dependencies are copied.
