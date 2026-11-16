<div align="center">
  <a href="https://github.com/NousResearch/hermes-agent"><img src="https://github.com/user-attachments/assets/ac2f5702-c842-4b2e-9340-737481fa0ece" width="96" height="96" alt="Nous Research Hermes mark" /></a>
  <h1>Radio Plus</h1>
  <strong>Live radio in the status bar, with a station list you own.</strong>
  <p>An extended edition of the bundled Radio plugin: editable stations, three directories, and a station log that says why a stream will not play.</p>
  <p>
    <a href="plugin.yaml"><img src="https://img.shields.io/badge/version-1.0.0-2ea44f" alt="Version 1.2.0" /></a>
    <a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license" /></a>
  </p>
</div>

<div align="center">
  <img src="docs/hero.png" width="100%" alt="Radio Plus" />
</div>

## Screenshot

<div align="center">
  <img src="docs/screenshot.png" width="560" alt="The station picker: a search field, the All, Popular and Shoutcast chips, the add button, seven stored stations and the transport row" />
</div>

## Where this comes from

Radio Plus starts from the **Radio** plugin bundled with Hermes Desktop
(`apps/desktop/src/plugins/radio`, MIT, Nous Research) and keeps what makes it
good: the braille oscilloscope, the status-bar transport, artist links through
Apple Music and MusicBrainz, the dictation-aware pause and resume, and the
one-window playback lock. That plugin is the reason this one exists.

What it extends, in the direction of any station rather than seven fixed ones:

- The seven shipped stations were a fixed array in the source. Here they are a
  seeded starting list that you rename, re-point, delete, or add to.
- The picker searched one directory. It now searches Radio Browser, Radio
  Browser's popular list, and the Shoutcast directory, and it crosses scripts so
  a Bulgarian name typed in Cyrillic finds the Latin spelling the directories
  index.
- HLS stations, which the bundled player skips because a browser cannot open a
  playlist without a demuxer, play here through a vendored `hls.js`.
- A station that will not play now says why, in the panel and in a log line,
  instead of failing silently.

The bundled plugin and this one draw the same status-bar slot. Enable one of
them; both enabled means two players in one bar.

## What You Can Do

- Hover a row and use the pencil to edit a station. The editor carries the name
  and the stream address together, so a station can be renamed and re-pointed at
  a new mount in one place. The bin deletes on a second click and disarms itself
  after four seconds.
- Add a station from any address with the round button at the end of the source
  row. The address is checked before it is saved, so a website URL is refused
  with a reason instead of becoming a station that never plays.
- Search three sources. *All* mixes your stations with a Radio Browser name
  search, *Popular* lists Radio Browser's most-voted stations, and *Shoutcast*
  searches the Shoutcast directory by name, genre, or keyword. With an empty
  search box the Shoutcast chip lists the busy end of the directory.
- Search in Cyrillic or Latin. A Cyrillic query is also sent transliterated, so
  `Хоризонт` reaches `BNR Horizont` and `Христо Ботев` reaches its HLS stream.
  Local matching folds both scripts the same way.
- Play HLS stations. `hls.js` 1.6.15 is vendored into the plugin, so a playlist
  address plays like any other station. This is what makes БНР Христо Ботев, and
  the eleven other Bulgarian HLS stations in Radio Browser, reachable at all.
- Read why a station failed. The panel shows the media error and the host it
  tried, and the plugin route records the failure in
  `radio-plus/station-log.jsonl`. The add form and the failure path both use the
  same probe, which reports what an address actually returns.
- Skip the dead rows. Every resolved Shoutcast address is probed before it
  reaches the list, under a two-second budget, so a directory entry that now
  serves an HTML error page is dropped and counted rather than played.

## Install

The pack:

```bash
hermes plugins pack install https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/main/hermes-pack.yaml
```

This plugin alone:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/radio-plus
hermes plugins enable radio-plus
```

This is the listed edition. It stays inside the plugin SDK (`ctx.register`,
`ctx.storage`, `ctx.rest`, `ctx.os.openExternal`) plus its own dashboard route.
One feature differs: **HLS playback is personal-only.** The listed tree cannot
carry the vendored `hls.js` build, because the admission scanner refuses a
library that defines accessors on its own prototypes, and loading it from a CDN
would run remote code in the renderer. Here an HLS station is hidden from the
results and the panel says how many were hidden; everything else, including the
Shoutcast search, the transliterated queries and the station log, is identical.

Enable it in Capabilities, Plugins. The renderer half loads on that toggle or on
an app restart. The Shoutcast source needs the app restarted once, because the
dashboard mounts plugin routes at startup; until then that chip reports itself
unavailable and everything else works.

The bundled Radio plugin should be disabled while this one is enabled.

## Requirements and Limits

- HLS is bundled, not native: the vendored build adds about 345 KiB to
  `plugin.js`; the plugin loader reads up to 512 KiB, so there is room but not
  much. Replacing the build means replacing it in place.
- Shoutcast search is slower than the other sources, because a search resolves each
  station's tune-in file and probes the result before answering, so the first
  search of a term takes a few seconds and later ones come from cache.
- Waveform analysis needs CORS on the stream itself. A station that refuses
  it plays without a waveform and shows an activity indicator rather than
  invented levels.
- Directory data is theirs: availability, regional restrictions, and
  metadata quality belong to Radio Browser and Shoutcast.
- No accounts, keys, or telemetry. Streams connect directly to broadcasters.
  Searches send the typed term to Radio Browser, or to Shoutcast through the
  plugin's own local route. The route refuses loopback and private addresses, so
  it cannot be turned into a scanner for your network.

## Tests

```bash
py -m pytest tests/test_plugin_api.py -q
RADIO_PLUS_LIVE=1 py -m pytest tests/test_plugin_api.py -q
node tests/desktop.test.mjs
node tests/panel.test.mjs
node tests/hls.electron.test.mjs
```

The last one loads the shipped `plugin.js` in Electron, points `attachHls` at a
real BNR stream, and requires the audio clock to advance, which is the only
honest test of an HLS path.

`docs/screenshot.png` is a capture of the running app: a second Hermes instance
with a copy of the real profile, the picker opened over CDP, the app chrome
hidden so the panel's translucency composites on one colour, then cropped to the
popover. `docs/hero.png` is a stipple illustration with the title overlaid.
`docs/icon.png` is the mark, drawn in code so it stays crisp at 48px.

## License

[MIT](../../LICENSE) © Apostol Apostolov. The vendored `hls.js` build is MIT,
© its contributors; its banner in `desktop/plugin.js` records the version and
digest.
