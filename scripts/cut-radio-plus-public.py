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
One feature differs: **HLS playback is personal-only.** The listed tree cannot
carry the vendored `hls.js` build, because the admission scanner refuses a
library that defines accessors on its own prototypes, and loading it from a CDN
would run remote code in the renderer. Here an HLS station is hidden from the
results and the panel says how many were hidden; everything else, including the
Shoutcast search, the transliterated queries and the station log, is identical."""
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
  for (const row of Array.isArray(rows) ? rows : []) {
    if (isHlsRow(row)) hls += 1
    stations.push(...browseStation(row))
  }
  return { stations, hls }
}""",
    """function rowsToStations(rows) {
  const stations = []
  let hls = 0
  for (const row of Array.isArray(rows) ? rows : []) {
    if (isHlsRow(row)) { hls += 1; continue }
    stations.push(...browseStation(row))
  }
  return { stations, hls }
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

print("public edition built")
