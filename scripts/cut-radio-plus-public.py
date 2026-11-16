#!/usr/bin/env python3
"""Build `public/radio-plus` from `personal/radio-plus`.

The listed edition differs in three places, and every one is anchored: a missing
anchor stops the script rather than shipping a half-cut tree.

1. `plugin.yaml` homepage points at the public path.
2. The README install block names the public path and states the one feature the
   listed edition drops.
3. HLS playback is removed. The admission scanner refuses a library that defines
   accessors on its own prototypes (rule-8), and hls.js does exactly that, so the
   listed tree cannot carry it; loading it from a CDN would run remote code in
   the renderer. `personal/radio-plus/LIMITATIONS.md` records the blocker.

Run from the repository root:

    python scripts/cut-radio-plus-public.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent.parent
personal = repo / "personal" / "radio-plus"
public = repo / "public" / "radio-plus"

if not (personal / "desktop" / "plugin.js").exists():
    print("MISS personal tree")
    sys.exit(1)

if public.exists():
    shutil.rmtree(public)
# LIMITATIONS.md stays in the personal tree: the listed edition does not ship it
# and must not link it.
shutil.copytree(personal, public, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", "LIMITATIONS.md"))
print("ok copied personal to public")

# --------------------------------------------------------------- edition files
yaml_path = public / "plugin.yaml"
body = yaml_path.read_text(encoding="utf-8")
old_home = "homepage: https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/personal/radio-plus"
new_home = "homepage: https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/radio-plus"
if body.count(old_home) != 1:
    print("MISS public homepage anchor")
    sys.exit(1)
yaml_path.write_text(body.replace(old_home, new_home), encoding="utf-8")
print("ok public homepage")

readme = public / "README.md"
body = readme.read_text(encoding="utf-8")
old_install = """This plugin alone:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/personal/radio-plus
hermes plugins enable radio-plus
```"""
new_install = """This plugin alone:

```bash
hermes plugins install apoapostolov/hermes-agent-awesome-plugins/public/radio-plus
hermes plugins enable radio-plus
```

This is the listed edition. It stays inside the plugin SDK (`ctx.register`,
`ctx.storage`, `ctx.rest`, `ctx.os.openExternal`) plus its own dashboard route.
Two features are personal-only: **HLS playback** and **TuneIn**. The listed tree
cannot carry the vendored `hls.js` build, because the admission scanner refuses a
library that defines accessors on its own prototypes, and loading it from a CDN
would run remote code in the renderer; here an HLS station is hidden from the
results and the panel says how many were hidden. TuneIn is an undocumented
endpoint whose terms describe personal listening, so a listing does not call it;
the picker carries three sources instead of four. Everything else, including the
Shoutcast search, the transliterated queries, the track line and the station log,
is identical."""
if body.count(old_install) != 1:
    print("MISS public install anchor")
    sys.exit(1)
readme.write_text(body.replace(old_install, new_install), encoding="utf-8")
print("ok public readme")

# ------------------------------------------------------------------- code cut
plugin = public / "desktop" / "plugin.js"
text = plugin.read_text(encoding="utf-8").replace("\r\n", "\n")


def exact(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        print(f"MISS {label}: {count} matches")
        sys.exit(1)
    text = text.replace(old, new)
    print(f"ok {label}")


marker = "\n\n// ---------------------------------------------------------------------------\n// hls.js 1.6.15"
index = text.find(marker)
if index < 0:
    print("MISS vendored block")
    sys.exit(1)
text = text[:index].rstrip("\n") + "\n"
print("ok vendored block removed")

start = text.find("function streamHost(url) {")
end = text.find("function mediaFailure(element, station) {")
if start < 0 or end < 0 or end < start:
    print("MISS hls helpers")
    sys.exit(1)
text = text[:start] + text[end:]
print("ok hls helpers removed")

exact(
    """function browseStation(row) {
  const url = streamUrl(row.url_resolved)
  if (!url || !row.stationuuid || !row.name) return []
  return [{
    id: row.stationuuid,
    name: row.name.trim(),
    url,
    provider: 'Radio Browser',
    description: row.tags?.split(',').slice(0, 2).join(' · ') || '',
    homepage: httpsUrl(row.homepage),
    hls: isHlsRow(row)
  }]
}""",
    """function browseStation(row) {
  const url = streamUrl(row.url_resolved)
  if (!url || !row.stationuuid || !row.name || row.hls) return []
  return [{
    id: row.stationuuid,
    name: row.name.trim(),
    url,
    provider: 'Radio Browser',
    description: row.tags?.split(',').slice(0, 2).join(' · ') || '',
    homepage: httpsUrl(row.homepage)
  }]
}""",
    "browseStation",
)

exact(
    """function rowsToStations(rows) {
  const stations = []
  let hls = 0
  const list = Array.isArray(rows) ? rows : []
  for (const row of list) {
    if (isHlsRow(row)) hls += 1
    stations.push(...browseStation(row))
  }
  // The raw count, not the station count: a full page of rows means there is
  // probably another page behind it, even when some rows mapped to nothing.
  return { stations, hls, count: list.length }
}""",
    """function rowsToStations(rows) {
  const stations = []
  let hls = 0
  const list = Array.isArray(rows) ? rows : []
  for (const row of list) {
    if (isHlsRow(row)) { hls += 1; continue }
    stations.push(...browseStation(row))
  }
  // The raw count, not the station count: a full page of rows means there is
  // probably another page behind it, even when some rows mapped to nothing.
  return { stations, hls, count: list.length }
}""",
    "rowsToStations",
)

exact("  let audio = null\n  let hls = null\n", "  let audio = null\n", "hls slot")
exact("    hls?.destroy()\n    hls = null\n    source?.disconnect()", "    source?.disconnect()", "hls destroy")
exact(
    """    if (next.hls || isHlsUrl(next.url)) {
      hls = attachHls(element, next, reason => {
        if (!current()) return
        clearTimeout(timeout)
        lastError.set(reason)
        reportFailure(ctx, next, reason)
        stop('error')
      })
      // A build without Media Source support cannot open a playlist; say so
      // rather than leaving the element silent.
      if (!hls) fail()
    }
    if (!hls) element.src = next.url""",
    "    element.src = next.url",
    "play hls branch",
)
exact(
    "      hls > 0 && !HLS && jsx('div', { className: 'hermes-radio-plus-error', children: `${hls} ${t('hlsNote')}` }),",
    "      hls > 0 && jsx('div', { className: 'hermes-radio-plus-error', children: `${hls} ${t('hlsNote')}` }),",
    "hls note",
)
exact(
    "  hlsNote: 'HLS streams need Media Source support this build does not have.',",
    "  hlsNote: 'HLS streams are not supported in this edition.',",
    "hls note text",
)
exact(
    "    if (verdict && verdict.ok === false && verdict.kind !== 'unreachable') {\n      setAddNote(t('notAudio'))\n      return\n    }",
    "    if (verdict && verdict.ok === false && verdict.kind !== 'unreachable' && verdict.kind !== 'hls') {\n      setAddNote(t('notAudio'))\n      return\n    }",
    "add hls address",
)

# --------------------------------------------------------------- tunein cut
# The listed edition carries three sources. TuneIn stays in the personal tree:
# it is an undocumented endpoint whose terms describe personal listening, and a
# listing is a statement that the plugin is safe to recommend.
def cut_block(start_marker: str, end_marker: str, label: str) -> None:
    global text
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        print(f"MISS {label}")
        sys.exit(1)
    text = text[:start] + text[end:]
    print(f"ok {label}")


exact(
    "  sourceAll: 'All', sourcePopular: 'Popular', sourceShoutcast: 'Shoutcast', sourceTunein: 'TuneIn',",
    "  sourceAll: 'All', sourcePopular: 'Popular', sourceShoutcast: 'Shoutcast',",
    "tunein chip label",
)
exact(
    "  tuneinHint: 'Type a station name. TuneIn has no top list, but genre:jazz works.',\n"
    "  tuneinError: 'TuneIn is unavailable. Try again, or restart Hermes if you just enabled Radio Plus.',\n",
    "",
    "tunein english strings",
)
exact(
    ", sourceTunein: 'TuneIn', tuneinEmpty: 'TuneIn に見つかりませんでした', "
    "tuneinHint: 'ステーション名を入力してください。genre:jazz も使えます。', "
    "tuneinError: 'TuneIn を利用できません。もう一度お試しください。'",
    "",
    "tunein japanese strings",
)
exact(
    ", sourceTunein: 'TuneIn', tuneinEmpty: '没有找到 TuneIn 电台', "
    "tuneinHint: '输入电台名称，也可以使用 genre:jazz。', "
    "tuneinError: '暂时无法访问 TuneIn，请重试。'",
    "",
    "tunein chinese strings",
)
exact(
    "// TuneIn resolves a playlist per row before it can play, so it pages by thirty\n"
    "// too.\nconst TUNEIN_PAGE = 30\n",
    "",
    "tunein page size",
)
cut_block(
    "async function tuneinQuery(ctx, text, { offset = 0, limit = TUNEIN_PAGE } = {}) {",
    "// Which rows the picker shows.",
    "tunein query",
)
exact(
    "const SOURCE_LABELS = { all: 'sourceAll', popular: 'sourcePopular', shoutcast: 'sourceShoutcast', tunein: 'sourceTunein' }",
    "const SOURCE_LABELS = { all: 'sourceAll', popular: 'sourcePopular', shoutcast: 'sourceShoutcast' }",
    "source labels",
)
exact(
    "const SOURCE_PAGE = { all: PAGE_SIZE, popular: PAGE_SIZE, shoutcast: SHOUTCAST_PAGE, tunein: TUNEIN_PAGE }",
    "const SOURCE_PAGE = { all: PAGE_SIZE, popular: PAGE_SIZE, shoutcast: SHOUTCAST_PAGE }",
    "source page sizes",
)
exact(
    "const EMPTY_LABELS = { shoutcast: 'shoutcastEmpty', tunein: 'tuneinEmpty' }",
    "const EMPTY_LABELS = { shoutcast: 'shoutcastEmpty' }",
    "empty labels",
)
exact(
    "  const tunein = useQuery({\n"
    "    queryKey: [ID, 'tunein', query], queryFn: () => tuneinStations(ctx, query),\n"
    "    enabled: source === 'tunein' && text === query, staleTime: 300000, retry: false\n"
    "  })\n",
    "",
    "tunein query hook",
)
exact(
    "  // One place that says which source answers which question, so a fourth source\n"
    "  // is a row in these maps rather than another branch in five ternaries.\n"
    "  const sourceQuery = { all: browser, popular, shoutcast, tunein }",
    "  // One place that says which source answers which question, so a source is a\n"
    "  // row in these maps rather than another branch in five ternaries.\n"
    "  const sourceQuery = { all: browser, popular, shoutcast }",
    "source query map",
)
exact(
    "    shoutcast: (token, offset) => shoutcastStations(ctx, token, { offset }),\n"
    "    tunein: (token, offset) => tuneinStations(ctx, token, { offset })",
    "    shoutcast: (token, offset) => shoutcastStations(ctx, token, { offset })",
    "fetch page map",
)
exact(
    "{ popular: 'popularError', shoutcast: 'shoutcastError', tunein: 'tuneinError' }",
    "{ popular: 'popularError', shoutcast: 'shoutcastError' }",
    "error text map",
)
exact(
    "children: source === 'tunein' && !text ? t('tuneinHint') : t(EMPTY_LABELS[source] ?? 'noResults')",
    "children: t(EMPTY_LABELS[source] ?? 'noResults')",
    "empty hint",
)
exact(
    "  tuneinEmpty: 'No TuneIn stations found',\n",
    "",
    "tunein empty string",
)
exact(
    "// Shoutcast and TuneIn answer from their own directory, and a station carried",
    "// Shoutcast answers from its own directory, and a station carried",
    "listRows comment",
)
exact(
    "  // A directory row already knows what was on air when it was fetched: TuneIn\n"
    "  // sends the show or the track, Shoutcast sends CurrentTrack. Keep it for the",
    "  // A Shoutcast row already knows what was on air when it was fetched: it sends\n"
    "  // CurrentTrack. Keep it for the",
    "track comment",
)
exact(
    "description: 'Live radio with an editable station list, Radio Browser, Shoutcast and TuneIn search, and an audio-reactive waveform.'",
    "description: 'Live radio with an editable station list, Radio Browser and Shoutcast search, and an audio-reactive waveform.'",
    "plugin description",
)

plugin.write_text(text, encoding="utf-8")
print(f"ok public plugin.js {len(text.encode('utf-8')) / 1024:.0f} KiB")

# ------------------------------------------------------------------ public tests
tests = public / "tests" / "desktop.test.mjs"
body = tests.read_text(encoding="utf-8").replace("\r\n", "\n")
body = body.replace(
    "  transliterate, fold, searchTerms, mediaFailure, isHlsUrl, attachHls, rowsToStations,\n  matchScore, HLS\n",
    "  transliterate, fold, searchTerms, mediaFailure, isHlsUrl, rowsToStations, matchScore\n",
)
for name in (
    "the vendored hls.js build loads with its events and version",
    "a Cyrillic query for an HLS-only station returns it",
    "a Bulgarian name typed in Cyrillic returns the station itself first",
):
    start = body.find(f"await test('{name}'")
    if start < 0:
        print(f"MISS test {name}")
        sys.exit(1)
    end = body.find("await test(", start + 10)
    if end < 0:
        end = body.find("const failed =", start)
    body = body[:start] + body[end:]
    print(f"ok removed test: {name}")

old_hls_row_test = """await test('an HLS row survives the directory mapping and is marked', () => {
  const rows = [
    { stationuuid: 'a', name: 'BNR - Hristo Botev', url_resolved: 'https://lb-hls.cdn.bg/2032/fls/HrBotev.stream/playlist.m3u8', hls: true, tags: 'public radio' },
    { stationuuid: 'b', name: 'BNR Horizont', url_resolved: 'https://play.global.audio/testb.aac', hls: false, tags: 'news' }
  ]
  const { stations, hls } = plugin.rowsToStations(rows)
  assert.equal(stations.length, 2, 'an HLS station must not be dropped any more')
  assert.equal(hls, 1)
  assert.equal(stations[0].hls, true)
  assert.equal(stations[1].hls, false)
})"""
new_hls_row_test = """await test('an HLS row is hidden and counted in this edition', () => {
  const rows = [
    { stationuuid: 'a', name: 'BNR - Hristo Botev', url_resolved: 'https://lb-hls.cdn.bg/2032/fls/HrBotev.stream/playlist.m3u8', hls: true, tags: 'public radio' },
    { stationuuid: 'b', name: 'BNR Horizont', url_resolved: 'https://play.global.audio/testb.aac', hls: false, tags: 'news' }
  ]
  const { stations, hls } = plugin.rowsToStations(rows)
  assert.equal(stations.length, 1, 'the listed edition cannot play an HLS playlist')
  assert.equal(hls, 1, 'the hidden HLS row must still be counted for the panel note')
})"""
if body.count(old_hls_row_test) != 1:
    print("MISS hls row test anchor")
    sys.exit(1)
body = body.replace(old_hls_row_test, new_hls_row_test)
tests.write_text(body, encoding="utf-8")
print("ok public desktop tests adjusted")

hls_test = public / "tests" / "hls.electron.test.mjs"
if hls_test.exists():
    hls_test.unlink()
    print("ok removed public hls.electron.test.mjs")

# ------------------------------------------------------ tunein cut: backend
api = public / "dashboard" / "plugin_api.py"
body = api.read_text(encoding="utf-8")


def api_exact(old: str, new: str, label: str) -> None:
    global body
    count = body.count(old)
    if count != 1:
        print(f"MISS {label}: {count} matches")
        sys.exit(1)
    body = body.replace(old, new)
    print(f"ok {label}")


def api_cut(start_marker: str, end_marker: str, label: str) -> None:
    global body
    start = body.find(start_marker)
    end = body.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        print(f"MISS {label}")
        sys.exit(1)
    body = body[:start] + body[end:]
    print(f"ok {label}")


api_exact(
    "TuneIn answers over OPML instead: ``Search.ashx`` returns JSON when asked for\n"
    "it, but each station points at a ``Tune.ashx`` tune-in address that answers an\n"
    "M3U playlist rather than audio, so the stream address is read out of that\n"
    "playlist here. TuneIn also ignores ``offset``, so a page is a slice of the list\n"
    "its search already returned.\n\n",
    "",
    "tunein docstring",
)
api_exact("_tunein_stream_cache: dict[str, tuple[float, str]] = {}\n", "", "tunein cache")
api_exact('_TUNEIN_SEARCH = "https://opml.radiotime.com/Search.ashx"\n', "", "tunein search constant")
api_cut(
    "def _tunein_rows(query: str) -> list[dict[str, Any]]:",
    "_PRIVATE_HOST = re.compile(",
    "tunein rows and stream",
)
api_cut(
    "def _tunein_page(rows: list[dict[str, Any]], limit: int, offset: int = 0) -> dict[str, Any]:",
    '@router.get("/shoutcast/search")',
    "tunein page helper",
)
api_cut(
    '@router.get("/tunein/search")',
    '@router.get("/probe")',
    "tunein route",
)
api_exact(
    "    A Shoutcast tune-in file is PLS (``File1=http://...``). A TuneIn tune-in\n"
    "    address answers an M3U whose body is often one bare address and no header at\n"
    "    all, so both shapes are read here instead of in two places.\n",
    "    A Shoutcast tune-in file is PLS (``File1=http://...``), and some mounts answer\n"
    "    a bare address instead, so both shapes are read here.\n",
    "tunein first stream note",
)
api.write_text(body, encoding="utf-8")
print("ok public plugin_api.py")

# -------------------------------------------------------- tunein cut: README
readme = public / "README.md"
body = readme.read_text(encoding="utf-8")


def readme_exact(old: str, new: str, label: str) -> None:
    global body
    count = body.count(old)
    if count != 1:
        print(f"MISS {label}: {count} matches")
        sys.exit(1)
    body = body.replace(old, new)
    print(f"ok {label}")


readme_exact(
    "- The picker searched one directory. It now searches Radio Browser, Radio\n"
    "  Browser's popular list, the Shoutcast directory and TuneIn, and it crosses\n"
    "  scripts so a Bulgarian name typed in Cyrillic finds the Latin spelling the\n"
    "  directories index.",
    "- The picker searched one directory. It now searches Radio Browser, Radio\n"
    "  Browser's popular list and the Shoutcast directory, and it crosses scripts so\n"
    "  a Bulgarian name typed in Cyrillic finds the Latin spelling the directories\n"
    "  index.",
    "readme extends bullet",
)
readme_exact(
    "- HLS stations, which the bundled player skips because a browser cannot open a\n"
    "  playlist without a demuxer, play here through a vendored `hls.js`.\n",
    "",
    "readme hls extends bullet",
)
readme_exact(
    "- Search four sources. *All* mixes your stations with a Radio Browser name\n"
    "  search, *Popular* lists Radio Browser's most-voted stations, *Shoutcast*\n"
    "  searches the Shoutcast directory by name, genre, or keyword, and *TuneIn*\n"
    "  searches TuneIn, which carries many stations the other directories do not\n"
    "  index. With an empty search box the Shoutcast chip lists the busy end of the\n"
    "  directory; TuneIn has no top list, so it asks for a name instead.",
    "- Search three sources. *All* mixes your stations with a Radio Browser name\n"
    "  search, *Popular* lists Radio Browser's most-voted stations, and *Shoutcast*\n"
    "  searches the Shoutcast directory by name, genre, or keyword. With an empty\n"
    "  search box the Shoutcast chip lists the busy end of the directory.",
    "readme search bullet",
)
readme_exact(
    "results; the Shoutcast and TuneIn sources understand a genre tag but have no\n"
    "  country index.",
    "results; the Shoutcast source understands a genre tag but has no country\n"
    "  index.",
    "readme tag bullet",
)
readme_exact(
    "- Scroll for more, on all four sources. A search and the Popular list arrive\n"
    "  forty at a time and ask for the next page when you reach the bottom, so a broad\n"
    "  query like `genre:jazz` costs one page up front instead of every row the\n"
    "  directory holds. Shoutcast and TuneIn page thirty at a time, because every row\n"
    "  there costs a resolve and a probe before it can play. The list says when it is\n"
    "  loading, and it stops asking once a page comes back short or adds nothing new.",
    "- Scroll for more, on all three sources. A search and the Popular list arrive\n"
    "  forty at a time and ask for the next page when you reach the bottom, so a broad\n"
    "  query like `genre:jazz` costs one page up front instead of every row the\n"
    "  directory holds. Shoutcast pages thirty at a time, because every row there\n"
    "  costs a resolve and a probe before it can play. The list says when it is\n"
    "  loading, and it stops asking once a page comes back short or adds nothing new.",
    "readme paging bullet",
)
readme_exact(
    "`Хоризонт` reaches `BNR Horizont` and `Христо Ботев` reaches its HLS stream.",
    "`Хоризонт` reaches `BNR Horizont` and `Христо Ботев` reaches its entry.",
    "readme cyrillic bullet",
)
readme_exact(
    "- Play HLS stations. `hls.js` 1.6.15 is vendored into the plugin, so a playlist\n"
    "  address plays like any other station. This is what makes БНР Христо Ботев, and\n"
    "  the eleven other Bulgarian HLS stations in Radio Browser, reachable at all.\n",
    "- HLS stations are hidden here and counted. A playlist address needs a demuxer\n"
    "  this edition does not carry, so those rows are left out of the results and the\n"
    "  panel says how many were left out.\n",
    "readme hls bullet",
)
readme_exact(
    "- Skip the dead rows. Every resolved Shoutcast and TuneIn address is probed",
    "- Skip the dead rows. Every resolved Shoutcast address is probed",
    "readme probe bullet",
)
readme_exact(
    "cannot. A directory row that already knows what was playing, as TuneIn and\n"
    "  Shoutcast both do, fills the line until the stream's first announcement.",
    "cannot. A Shoutcast row that already knows what was playing fills the line\n"
    "  until the stream's first announcement.",
    "readme track bullet",
)
readme_exact(
    "an app restart. The Shoutcast, TuneIn and now-playing routes need the app",
    "an app restart. The Shoutcast and now-playing routes need the app",
    "readme routes note",
)
readme_exact(
    "- HLS is bundled, not native: the vendored build adds about 345 KiB to\n"
    "  `plugin.js`; the plugin loader reads up to 512 KiB, so there is room but not\n"
    "  much. Replacing the build means replacing it in place.\n",
    "",
    "readme hls limits",
)
readme_exact(
    "- TuneIn is searched through its public OPML endpoint, which is not a documented\n"
    "  API with a support contract and whose terms describe personal listening rather\n"
    "  than redistribution. It can change or refuse without notice. Radio Browser and\n"
    "  Shoutcast carry most of the same stations, so a TuneIn failure costs coverage\n"
    "  rather than the plugin.\n",
    "",
    "readme tunein limits",
)
readme_exact(
    "- No accounts, keys, or telemetry. Streams connect directly to broadcasters.\n"
    "  Searches send the typed term to Radio Browser, or to Shoutcast and TuneIn\n"
    "  through the plugin's own local route, which also reads the track a playing\n"
    "  station announces. Three hosts are contacted and no others: Radio Browser, the\n"
    "  Shoutcast directory with its tune-in files, and TuneIn's OPML endpoint, plus\n"
    "  whichever station you are playing when the panel asks what is on air. The route\n"
    "  refuses loopback and private addresses, so it cannot be turned into a scanner\n"
    "  for your network, and nothing is sent anywhere except the term you typed.",
    "- No accounts, keys, or telemetry. Streams connect directly to broadcasters.\n"
    "  Searches send the typed term to Radio Browser, or to Shoutcast through the\n"
    "  plugin's own local route, which also reads the track a playing station\n"
    "  announces. Two hosts are contacted and no others: Radio Browser and the\n"
    "  Shoutcast directory with its tune-in files, plus whichever station you are\n"
    "  playing when the panel asks what is on air. The route refuses loopback and\n"
    "  private addresses, so it cannot be turned into a scanner for your network, and\n"
    "  nothing is sent anywhere except the term you typed.",
    "readme network bullet",
)
readme.write_text(body, encoding="utf-8")
print("ok public README")

# ----------------------------------------------------- tunein cut: manifest
yaml_path = public / "plugin.yaml"
body = yaml_path.read_text(encoding="utf-8")
old_description = (
    'description: "Live radio in the status bar, an extended edition of the bundled Radio plugin: '
    "editable stations with a name and a stream address, search across Radio Browser, its popular "
    "list, the Shoutcast directory and TuneIn, the track each stream announces, cross-script search "
    'for Bulgarian names, HLS playback through a bundled hls.js, and a station log that explains why '
    'a stream will not play."'
)
new_description = (
    'description: "Live radio in the status bar, an extended edition of the bundled Radio plugin: '
    "editable stations with a name and a stream address, search across Radio Browser, its popular "
    "list and the Shoutcast directory, the track each stream announces, cross-script search for "
    'Bulgarian names, and a station log that explains why a stream will not play."'
)
if body.count(old_description) != 1:
    print("MISS public description")
    sys.exit(1)
body = body.replace(old_description, new_description)
if body.count("  - tunein\n") != 1:
    print("MISS public tunein tag")
    sys.exit(1)
body = body.replace("  - tunein\n", "")
yaml_path.write_text(body, encoding="utf-8")
print("ok public plugin.yaml")

# -------------------------------------------------------- tunein cut: tests
panel = public / "tests" / "panel.test.mjs"
body = panel.read_text(encoding="utf-8")
old_chips = "  assert.deepEqual(labels, ['sourceAll', 'sourcePopular', 'sourceShoutcast', 'sourceTunein'])"
new_chips = "  assert.deepEqual(labels, ['sourceAll', 'sourcePopular', 'sourceShoutcast'])"
if body.count(old_chips) != 1:
    print("MISS panel chip labels")
    sys.exit(1)
panel.write_text(body.replace(old_chips, new_chips), encoding="utf-8")
print("ok public panel test")

desktop_tests = public / "tests" / "desktop.test.mjs"
body = desktop_tests.read_text(encoding="utf-8")
old_import = "  createPlayer, popularStations, sameStation, searchStations, shoutcastStations, tuneinStations, nowPlaying,"
new_import = "  createPlayer, popularStations, sameStation, searchStations, shoutcastStations, nowPlaying,"
if body.count(old_import) != 1:
    print("MISS desktop test import")
    sys.exit(1)
body = body.replace(old_import, new_import)
start = body.find("await test('tuneinStations maps the plugin route and drops unusable rows'")
end = body.find("await test('a directory tab shows its own rows, not the station carried over from All'")
if start < 0 or end < 0 or end <= start:
    print("MISS desktop tunein tests")
    sys.exit(1)
body = body[:start] + body[end:]
old_claim = "'the TuneIn tab lists what TuneIn answered'"
new_claim = "'the directory tab lists what its directory answered'"
if body.count(old_claim) != 1:
    print("MISS desktop listRows claim")
    sys.exit(1)
body = body.replace(old_claim, new_claim)
old_sources = "  assert.deepEqual(Object.keys(plugin.SOURCE_LABELS), ['all', 'popular', 'shoutcast', 'tunein'])"
old_title = "await test('source labels cover the four picker tabs'"
new_title = "await test('source labels cover the three picker tabs'"
new_sources = "  assert.deepEqual(Object.keys(plugin.SOURCE_LABELS), ['all', 'popular', 'shoutcast'])"
if body.count(old_sources) != 1:
    print("MISS desktop source labels claim")
    sys.exit(1)
body = body.replace(old_sources, new_sources)
if body.count(old_title) != 1:
    print("MISS desktop source labels title")
    sys.exit(1)
desktop_tests.write_text(body.replace(old_title, new_title), encoding="utf-8")
print("ok public desktop tests tunein removed")

pytest_file = public / "tests" / "test_plugin_api.py"
body = pytest_file.read_text(encoding="utf-8")
start = body.find("def test_tunein_station_prefers_the_announced_track():")
end = body.find(
    '@pytest.mark.skipif(not LIVE, reason="set RADIO_PLUS_LIVE=1 to query Shoutcast")',
    start + 1 if start >= 0 else 0,
)
if start < 0 or end < 0 or end <= start:
    print("MISS pytest tunein block")
    sys.exit(1)
pytest_file.write_text(body[:start] + body[end:], encoding="utf-8")
print("ok public pytest tunein tests removed")

print("public edition built")
