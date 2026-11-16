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
  an edit or a delete survives a restart and does not come back.
- **Row controls.** Hover a station and use the pencil to edit it, or the bin to
  delete it. The editor carries both fields, the name and the stream address, so
  a station can be renamed and re-pointed at a new mount in one place. Deleting
  takes two clicks and disarms itself after four seconds. Deleting the station
  that is playing moves playback to the next one; deleting the last one stops the
  player. A pin follows its station.
- **Add station**, a round button on the same row as the source chips. Enter a
  name and any `http` or `https` stream address; the name is optional and falls
  back to the host. Before saving, the address is checked by the plugin route, so
  a website URL is refused with "that address is not an audio stream" instead of
  being saved as a station that will never play. A duplicate URL reports that it
  is already in the list.
- **Three sources** in one row of chips, one of them always visibly selected:
  - **All**: your stations plus a name search of [Radio Browser](https://api.radio-browser.info/).
  - **Popular**: Radio Browser's most-voted stations, filtered as you type.
  - **Shoutcast**: the [Shoutcast](https://directory.shoutcast.com/) directory,
    searched by station, genre, or keyword. With an empty search box it lists the
    busy end of the directory, so the chip works as a shortcut into Shoutcast
    without typing anything.

  Popular and Shoutcast show that source alone; only All mixes in your own
  stations. When results are dropped, the panel says how many and why: HLS
  streams the player cannot decode, and directory rows whose stream address no
  longer answers with audio.
- **Cross-script search.** Station names are indexed in the Latin spelling while
  Bulgarian names are written in Cyrillic, so a Cyrillic query is sent twice, as
  typed and transliterated. "Хоризонт" finds "BNR Horizont".

The status bar, the braille waveform, artist links, and next-station cycling
behave as they do in Radio. In the panel the waveform is a filler between the
transport controls and the volume slider, not a line of its own.


## How the Shoutcast source works

The Shoutcast directory sends no CORS headers and rejects `OPTIONS` with 405, so
the renderer cannot call it. Radio Plus ships one backend route for it,
mounted at `/api/plugins/radio-plus/`:

| Route | Purpose |
| --- | --- |
| `GET /shoutcast/search?q=<term>&limit=40` | Keyword search of the directory |
| `GET /shoutcast/top?limit=40` | Popular stations, busiest first |
| `GET /probe?url=<address>` | What a stream address actually returns |
| `POST /log` | Record one station failure |

The route performs the two requests the Shoutcast site performs for itself
(`POST /Search/UpdateSearch`, `POST /Home/Top`). Directory rows carry no stream
address, so each station's PLS tune-in file is resolved server-side, twelve at a
time. Every resolved address is then probed: a row whose address answers with an
HTML error page, a closed mount, or an HLS playlist is dropped instead of being
listed as a station that cannot play, and the panel reports how many were
skipped. Probes run under a two-second wall-clock budget, so one dead station
cannot hold a search; its verdict is cached when it finally arrives. Resolved
addresses, verdicts, and query results are cached in memory for a few minutes. No
key, account, or credential is involved, and nothing leaves the machine except the
query you typed.

Because a search resolves and probes its stations before answering, the first
Shoutcast search takes a few seconds. Later searches of the same term come from
cache.

## Station diagnostics

When a station will not play, three things happen:

- The panel shows the reason in place of the track line, taken from the browser's
  media error (`network error`, `decode error`, `unsupported stream format`)
  plus the host it tried.
- `console.error` gets one `[radio-plus]` line. That is the renderer channel that
  reaches the desktop log.
- The plugin route writes one JSON line to
  `$HERMES_HOME/radio-plus/station-log.jsonl`, rotating at 1 MB. It also records
  the directory rows it dropped while resolving a Shoutcast search, so a station
  that quietly disappeared can be explained later.

`GET /probe?url=` is the same check the add form uses: it reports `kind`
(`audio`, `hls`, `html`, `playlist`, `http-error`, `unreachable`), the HTTP
status, the content type, and the station's `icy-name` when it sends one. It
refuses loopback and private addresses, so it cannot be turned into a scanner for
the local network.


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

- **HLS streams cannot play.** Chromium has no HLS demuxer, so a `.m3u8` station
  needs `hls.js`, which this plugin does not ship. The panel counts the HLS
  results it hid instead of leaving a search mysteriously empty. This is why
  БНР Христо Ботев, whose only public address is
  `lb-hls.cdn.bg/.../HrBotev.stream/playlist.m3u8`, cannot be added as a working
  station yet. БНР Хоризонт does play: Radio Browser lists a non-HLS mount
  (`play.global.audio/testb.aac`, `icy-name: BNR Horizont`), which the
  transliterated search reaches.
- Shoutcast resolution depends on the station's PLS file being populated, and on
  the resolved mount still answering with audio. Belisimo.BG is the example: the
  directory lists two entries, one answers with an HTML page and the other times
  out, so both are dropped and the panel says how many were skipped.
- Waveform analysis needs CORS on the stream itself. A station that refuses it
  plays without a waveform and shows an activity indicator instead of invented
  levels; Shoutcast streams usually take this path.
- Radio Browser and Shoutcast results are shown as found. Availability, regional
  restrictions, and metadata quality are theirs.

## Tests

```
py -m pytest tests/test_plugin_api.py -q                      # routes, mapping, probe, log
RADIO_PLUS_LIVE=1 py -m pytest tests/test_plugin_api.py -q    # + live Shoutcast and probes
node tests/desktop.test.mjs                                    # player state and fetchers
node tests/panel.test.mjs                                      # rendered panel and clicks
```

The renderer suites import `desktop/plugin.js` through generated SDK stubs. The
panel suite renders the real component tree with the React and jsdom from the
installed Hermes desktop app, then clicks the chips, the add button, and a row
editor, which is how the selected state and the list swap are covered.


## References

- Forked from the bundled Radio plugin in `apps/desktop/src/plugins/radio` (MIT,
  Nous Research). The waveform, artist-link, and transport code is unchanged.
- [Radio Browser API](https://api.radio-browser.info/)
- [Shoutcast directory](https://directory.shoutcast.com/)

No upstream assets or dependencies are copied.
