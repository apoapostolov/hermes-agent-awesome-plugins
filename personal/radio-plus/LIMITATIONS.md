# Listing limitations

What the personal edition does that the listed edition does not, and why. Both
editions are built from one source; `scripts/cut-radio-plus-public.py` produces
the public tree and stops on any anchor it cannot find.

## 1. HLS playback is personal-only

**Personal:** `desktop/plugin.js` vendors `hls.js` 1.6.15 (light build, MIT) and
plays a `.m3u8` station through Media Source Extensions. That is what makes БНР
Христо Ботев and the eleven other Bulgarian HLS stations in Radio Browser
reachable at all.

**Why it fails the catalog bar:** `scripts/admission_check.py` refuses the
`defineProperty` call form anywhere in a listed tree (rule-8, "prototype
patching is refused"), and every published hls.js build contains it: it defines
accessors on its own classes. The personal tree routes that call through a local
alias inside the vendored block, which the scanner accepts, and the block carries
a banner saying so. The remaining finding is a WARN, not a FAIL: the bundle calls
`appendChild` once, and the scanner cannot tell a library's own element from an
app-owned node.

The alternative the scanner would accept, importing the library from a CDN, puts
third-party code in the renderer at runtime and breaks offline, so it is refused
here.

**The hook that would clear it:** an SDK surface for a media pipeline (or an
admission exemption for a digest-pinned vendored library with no host reach-in),
after which HLS ships in both editions.

**Listed edition:** HLS rows are hidden from search results and counted. The
panel says how many were hidden, so a search is never mysteriously short. Every
other behaviour is identical, including the Shoutcast route, the transliterated
queries, the probe and the station log.

## 2. TuneIn is personal-only

**Personal:** the picker carries four sources, TuneIn among them. It adds
stations the other directories do not index, and a genre tag finds a whole shelf
of them.

**Why it fails the catalog bar:** not the code. TuneIn answers over an
undocumented OPML endpoint whose terms describe personal listening rather than
redistribution, so a listed plugin that calls it makes a promise the endpoint
does not support. The plugin repository's owner asked for the listed edition to
carry three sources instead, and the cut removes the chip, the query, the route
and every string that named it.

**The hook that would clear it:** a documented TuneIn API with terms that allow
redistribution, or a licensing arrangement. Nothing in the plugin needs to
change beyond restoring the cut block.

**Listed edition:** All, Popular and Shoutcast. A query that would have reached
TuneIn answers from the other three, and nothing in the panel refers to it.

## 3. The vendored build trips one WARN

**Personal:** `desktop/plugin.js` carries the aliased hls.js bundle, whose single
`appendChild` call the scanner reports as "node injection; confirm the parent is
your own".

**Why it is acceptable here:** the parent is hls.js's own media element, created
by the plugin, and nothing in the block queries or mutates app markup. The
finding is a WARN, which the review bar allows on the personal tree and which the
listed edition does not carry at all, since it has no bundle.

**The hook that would clear it:** the same media-pipeline surface as above.

## Before a future pin

- Run `python scripts/admission_check.py public/radio-plus` and expect 0 FAIL.
- Confirm `public/radio-plus` still hides and counts HLS rows, and that the panel
  note reads "HLS streams are not supported in this edition."
- Keep `desktop/plugin.js`, `dashboard/plugin_api.py`, `__init__.py` and
  `dashboard/manifest.json` identical between the editions except for the cut
  above; the script does that, so re-run it instead of editing public by hand.
