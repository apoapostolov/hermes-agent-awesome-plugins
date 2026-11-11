# Changelog

The pack and its plugins have separate version numbers. Entries below name
the component that changed; a plugin patch does not imply a new pack release.

## [cdp-manager 1.0.3] - 2026-11-11

The dialog could not start a port. Every launch and every profile switch sent a
`profile` field in its request body, and the desktop's native-HTTP guard reads a
body key of that name as a Hermes profile selector. `hermes` is a reserved
profile name and a `chrome:<dir>` id is not a valid one, so the guard refused the
whole request with `403 profile_scope_mismatch` before the plugin's own route
ran. Launch, restart and profile changes now send `browserProfile`; the old key
still parses for callers that carry no ticket.

Probes only asked `127.0.0.1`. A Chrome that loses the IPv4 bind race serves
CDP on `[::1]` alone, so the port read dead while a browser was up: the
supervisor relaunched, the running instance swallowed each new launch through
its profile singleton and exited, and the port stayed dead with the fail streak
climbing. Probes now try both families and remember the one that answered, so
such an instance is visible and can be closed. The clean `Browser.close` sends
a bracketed `Host` header, because an IPv6 endpoint rejects `Host: ::1:9333`.

Launch also refuses to spawn a second Chrome when a running one already holds
that port's profile directory, naming the pid instead of reporting
`no listener after 8s`, and stop names the same orphan rather than claiming the
port was already down. A launch without an explicit mode reads the remembered
`mode_<port>`; it used to read a bare `mode` key that never existed, so
launching a headless port from chat flipped it back to a window and remembered
that instead.

Restart Hermes Desktop after updating: the Python half of a plugin does not
reload in place.

## [reddit 1.1.0] - 2026-11-05

Reddit adds a local library of saved posts and comments, searchable source excerpts, summaries, context, notes and tags, and a Desktop browser with unread filtering and annotation editing. Bounded sync/refresh, source expiry and identifier-only bookmark transfer keep retrieval tied to current source access. A summary queue checks source hashes before attaching annotations. Background cleanup runs while Hermes is loaded; online revalidation is optional. Processes coordinate rate budgets and token refresh, and credential files use authenticated encryption, with DPAPI-protected keys on Windows.

Nine added tools bring the total to 22, including account/content/community workflows, moderator queues and actions, message read state, wiki revisions and custom feeds. Subscription fields, API error reporting, long rate-limit handling and OAuth callback/state handling are corrected. Complete manual login with its full redirect URL and restart Hermes after updating.

Both standalone editions carry these features. Catalog admission remains blocked by missing host-managed OAuth capabilities; Reddit's announced public API transition also limits long-term personal-data access. See the plugin's LIMITATIONS.md and API audit.

## [Unreleased]

### Added

- Every plugin in this repository now carries its product name in the manifest, so Capabilities and the Settings page read the same words as the README instead of a slug: Better Capabilities, Better Session Appearance, CDP Manager, Drag to Pin Session, Jev Routing, Intelligent Tool Break, Iteration Budget Meter, Memory Review, Opaque Composer, Prompt Enhance, Provider Status, Reasoning Switch, Reddit, RSS Reader, Scroll on Switch, Session Retitler, Sidebar Manager and Vercel Agent Desktop Support. The manifest name is the plugin id, so `plugins.entries.<id>`, `plugins.enabled` and the settings route move with it; existing installs keep their settings after the key is moved, and the four plugins that store state in `ctx.storage` carry a one-time copy from the old namespace in their personal edition. Directories, catalog entries and install commands keep their slugs, which the catalog matches through its install sidecar. `hermes plugins doctor` wants the path for any of them.
- **better-capabilities:** version `1.1.0`. Replaces the 1.0.0 design that painted delete and package controls into the Capabilities page. The plugin now owns a page under Settings ▸ Plugins with an overview, **Skills** and **Presets**: filter skills, flip them on or off, read the other markdown files in a skill folder, package a folder as a zip, reveal it, delete it to the Recycle Bin (or to a moved-aside folder when the bin is unavailable), and save, apply, overwrite, rename, reorder or delete on/off presets for skills, toolsets and agent plugins, per profile. Presets are snapshotted and applied through `host.skills`, `host.toolsets` and the `plugins.manage` RPC instead of core modules. The personal edition also carries two glyphs on the Capabilities nav row — this profile's Skills editor, and a picker that splits profiles by Skills and by Plugins — plus the `/preset` chat command. The listed edition now exists at `public/better-capabilities` and drops both of those: the command needs core capability-state modules, and the glyphs inject app markup. `LIMITATIONS.md` records each cut and why.
- hermes-jev-routing. Every model carries a reasoning flag from the host's capability table, so a row asking for a thinking level on a model without one is visible rather than silently clamped.

### Changed

- **vercel-agent-desktop-support:** version `1.2.0`. The plugin pins upstream agent-desktop 1.2.0 for both Windows targets alongside 1.0.2, so `desktop_install` fetches that release, matches its archive against the digest published in the release's `checksums.txt`, and proves the result by running `version` and `status` against the installed binary. The 1.2.0 release brings an `mcp` subcommand that serves every command as an MCP tool over stdio, `--stdin` for `type` (up to 10,000 bytes of UTF-8 from a pipe or file), and envelope version 2.6. The settings default, the manifest's config description, the README and the install tests read the target version from one place, so the next bump is a one-line change plus a digest.
- **vercel-agent-desktop-support:** renamed from `hermes-agent-desktop`, at the same version `1.0.2` because no behaviour changed. In the plugin catalog the old name read as Nous's own Hermes Desktop app, so it is named for the upstream `agent-desktop` binary it wraps instead. The directory, `plugin.yaml` name, README, install commands, root screenshot and pack pin follow. The plugin id changed, so an existing install is reinstalled rather than renamed in place, and settings saved under the old id are not read; the nine tools, the `pre_tool_call` hook and the config keys are unchanged.
- vercel-agent-desktop-support. Three tool descriptions named the author ("interrupts Apo's work", "away from Apo", "what Apo copied"), and every user's model reads those descriptions. They say "the user" now. Same 1.0.2.

### Fixed

- **provider-status.** The public edition stopped showing GLM's weekly window on the status-bar chip at the 1.7.0 rework: the multi-window allowlist dropped back to OpenCode Go and Codex, and `fetch_glm` went back to a bare `5h` detail. The chip therefore showed the 5-hour headline alone, and the allowance most likely to run out was visible only in the Providers dialog. `fetch_glm` sends the remaining-percent arrow detail `fetch_opencode` uses again, GLM is back on the multi-window renderer, and `tests_glm_quota.py` pins six z.ai payload shapes plus that convention. A window the API does not report contributes no segment, so a two-row response cannot draw a phantom month. Personal keeps its single-value GLM chip by design.
- hermes-jev-routing. The listed edition's desktop half mounted a strip under the user message with app DOM, so `hermes plugins validate` failed the desktop surface check and the plugin could not be catalogued. The line and its approve row now render as a React contribution at `COMPOSER_AREAS.underside`, with no app-owned nodes, no injected style tag and no line cache in `localStorage`. 1.0.2.
- hermes-jev-routing. `/jev-routing on|off|mode` wrote one process-wide `_LAST`, so an override in one chat changed routing for every session and its "for this session" wording was false. Overrides now live per session and survive the config read that reset the mode on every turn; `why` and `status` read that session's own prompt and decision, and `on_session_delete` drops a deleted session's state.
- better-capabilities. Zipping or deleting a skill resolved the name through a private `tools.skill_manager_tool._find_skill` plus a directory walk of its own. It uses the public `tools.skills_tool` helpers now, so a name resolves with the host's tier precedence and an ambiguous name is refused instead of guessed, while the result stays inside the user skills tree this panel may change.
- hermes-jev-routing. The cache guard had no prices to work with, so its penalty was always zero and the "would miss the cache" holds could never fire. Every configured model is now priced from the host rate card, and the context size comes from the anchored usage anchor rather than a guess at attribute names.
- The three cache-guard branches were a boolean arrangement whose fast path only worked by accident. They are written explicitly now. A same-tier swap needs an affordable miss, a move inside the current band always holds, and a move out of the band holds unless it is a big upgrade or cheap.
- A confirm tier held the tier but still let the turn send on the model you had not approved. It now interrupts the in-flight send and owes your prompt back, so the strip waits and the approved model answers the request you actually sent.
- The confirm strip led with a bold "Yes". It now reads `Approve:` in bold, with `Yes, <tier>`, `No`, `Free`, the other tier names, and `X` all plain.
- **voice-gate.** A markdown heading's first spaced em dash is title punctuation, the same structural role a bullet's label separator plays, so `## Better capabilities — skills and presets` stopped counting as prose; a second dash inside the heading still does, and bullets read as before.
- **hermes-jev-routing.** A cron run has no human to approve a held turn, so a routing hold interrupted the job before it could do its work. `pre_llm_call` now returns no decision on the `cron` platform, leaving the turn on the configured model; every other platform routes as before.

## [voice-gate 1.4.4] - 2026-11-05

### Fixed

- Vale started with the host's whole environment, so the binary the plugin downloads could read every provider key the gateway held. Both `subprocess.run` calls now pass a short list of non-secret variables: `PATH`, `HOME` or `USERPROFILE`, `LANG`, `LC_ALL`, the temp variables, `SYSTEMROOT`, `WINDIR` and `PATHEXT`.
- Plugin data and voice-profile lookup read `HERMES_HOME` and then probed `%LOCALAPPDATA%` and `~/.hermes`. A process that serves several profiles holds the launch profile in that variable, so Vale data could land in one profile's tree while a writing profile came from another. Both resolve the home the host reports for the turn through `hermes_constants.get_hermes_home()`, with the old probe kept as a fallback for a host where core cannot be imported.
- Turn-time findings ran the resolved Vale binary on changed files with no approval while `vale_mode` was `advisory`, although the README and the description said checks request approval before starting a program. The advisory pass now runs only a binary approved once through `voice_gate_vale`, and the approval is stored by digest, so a replaced executable asks again. Approving `status` or `install` is enough to enable the advisory pass; nothing runs before that.

### Changed

- The settings page no longer claims that Hermes Desktop 0.22.8 hides the autogenerated Agent settings page. `hideAgentSettings` does not exist in Hermes yet, so both pages still appear together and the sentence was untrue. The declaration stays in the desktop entry for the build that implements it.

## [voice-gate 1.4.3] - 2026-11-05

### Added

- The personal edition records correlated gate and tool events, document skip reasons, rule counts, profile reloads, preservation results, Vale and model review outcomes, errors, and timings. Backend JSON Lines logs rotate at 2 MiB with four backups, capped at 10 MiB per Hermes home. A shared file lock protects rotation across bot processes. Settings timing is stored separately in Desktop local storage, capped at 128 events and 64 KiB. Records exclude prose, assessments, setting values, full document paths, and exception messages; logging failures do not interrupt the plugin.
- Regression checks cover rotation under competing processes, record size limits, failure isolation, tool correlation and privacy, and bounded settings history with corrupt or unavailable storage.

The public edition receives version metadata only. This release updates the community index to the personal edition; the upstream catalog remains pinned to public 1.4.2. Restart Hermes Desktop to load the new backend and renderer.

## [voice-gate 1.4.2] - 2026-11-05

### Fixed

- Hermes 0.22.8 and newer no longer add an autogenerated Agent settings page beside Voice Gate's custom page. The manifest schema still supplies the fields used to load and save settings. Older Hermes builds keep showing the generated page alongside the custom page.

## [voice-gate 1.4.1] - 2026-11-05

### Fixed

- The new settings page used the SDK's default 30-second deadline for the complete installed-plugin inventory. On a large installation the request could time out before controls appeared. Loading and saving now allow up to two minutes, with an outer deadline covering a stalled dial, and failed loads offer Try again. Repeated mounts share a pending inventory request instead of adding another one.
- Everyday review settings and the exceptions editor remain visible. Vale, bot switches, and the individual checks now start collapsed, with the checks grouped inside Advanced rules.
- The settings test covers the request deadline, repeated mounts, a rejected load, retry, delayed recovery, collapsed controls, and scoped saving. The user confirmed the updated page loads. Inventory loading itself can still be slow.

## [voice-gate 1.4.0] - 2026-11-05

Voice Gate now gives a passage a bounded editorial review, with clearer settings and a complete comparison against the humanizer skill and all nine references.

### Added

- 75 mechanical families, up from 46, with separate vocabulary bands and paragraph-local clustering. The shipped comparison maps all 110 humanizer patterns, including their contextual review requirements.
- Optional review through the selected Hermes model for claims, coherence, narrative, voice, and over-correction. Findings must quote the supplied document; model judgment remains fallible and sends documents to the configured provider.
- `voice_gate_review` for a review plan, contextual analysis, and content-specific assessments. Revision requests allow at most two opportunities and compare protected spans and quantities before accepting completion.
- A plugin-owned settings page with grouped controls, rewritten labels and hints, a full-width five-row exceptions editor with a dim placeholder, and two-line Vale guidance linked to GitHub. Older hosts retain the generated form.

### Fixed

- Word-boundary and overlapping phrase matches, lost paragraph boundaries, malformed or mixed code fences, absolute-path exception matching, nonfinite profile thresholds, partial bot switches, and stale review assessments.
- Prose em dashes are flagged by default while bullet label separators and standalone empty table values remain allowed. Prose inside bullets and tables still follows the prose policy.
- Turn-time Vale findings now respect disabled families and file exceptions. Generated styles use valid Unicode YAML. Vale status, check, and install paths request process approval; approval directives require Hermes v2026.7.7 (semver 0.18.1), below this plugin's 0.22.0 minimum.
- Profile learning no longer infers prohibitions from absence, escapes its destination through a profile name, or overwrites an existing profile. Personal and public share the fixes; profile learning remains personal-only.

## [voice-gate 1.3.5] - 2026-11-05

The exceptions setting is a box now, not a line.

### Changed

- `Exceptions` asks for a five-line field with a dim example, so a list of entries can be read and edited as a list. Manifests can only ask for this with `type: text`, a field type added to Hermes in the companion change; on a build without it the field stays a single-line string and saves exactly as before, so nothing breaks while the two arrive at different times.
- The Vale pack and the rules are unchanged in this release.

## [voice-gate 1.3.4] - 2026-11-05

Coverage of the humanizer references, a switch per family, and the plan for what
still needs a reader.

### Added

- Rule families went from 19 to 46. The additions cover the catalog patterns a text can be judged on without guessing: narrated candor, shadowboxed objections, rhetorical setup, emphasis crutches, dev slogans, template phrases, copula avoidance, wh- openers, stacked hedges, parenthetical hedges, future-narrative closers, negative listings, numbered-list bait, hashtag blocks, over-compression, rule-of-three padding, same-opener runs, staccato runs, stacked questions, bare noun-phrase bullets, vague attribution, real/actual inflation, endorsement closers, launch copy, assistant residue, template residue and tool fingerprints in a URL.
- One switch per family in Settings, on by default, so a family that does not fit a project can be turned off without editing a profile.
- A register per document: README, AGENTS, CHANGELOG, LIMITATIONS, AUDIT, SKILL and `docs/` paths are judged as documentation, where bold field labels, arrows and short labelled lines are conventions rather than tells. Chat text and ordinary prose keep the strict rules. A profile's `context` overrides the inference.
- `docs/HUMANIZER-COVERAGE.md`: every catalog pattern mapped to the family that carries it, or to the capability that would be needed. The plan names clause parsing, paragraph statistics, cross-document memory, house style, claim comparison and the fiction register, with a phase for each.

### Changed

- Shape families ignore lists. A block of bullet lines is no longer read as a paragraph, so a checklist of short lines does not count as staccato prose, and a repeated article is not a repeated opener.
- The Vale pack grew from 9 rules to 25: seven new phrase families and nine regex rules for the shapes Vale can express.
- Settings descriptions are one line each, so the page reads without wrapping.

## [voice-gate 1.3.3] - 2026-11-04

What the plugin says about itself. No rule, hook or tool behaviour changed.

### Fixed

- Two manifest descriptions and four tool descriptions still called Voice Gate a Markdown checker, which it stopped being in 1.3.1. The manifest description is what Capabilities, the settings form and the catalog card show, and tool descriptions shape the action forms, so the stale lines reached everyone who read what they were about to install or run. They now name the formats the gate actually reads.

## [voice-gate 1.3.2] - 2026-11-04

Exceptions, and two fixes the last release needed. A rule can now be silenced for the files a glob matches while it stays in force everywhere else, which is what lets a generated page or a template keep its own shape without weakening the gate. Fenced code stops reaching the rules as prose, and the profile is found in a host that starts without `HERMES_HOME`.

### Added

- An `exceptions` block, in the profile or in the plugin's own Exceptions setting. Each entry names a family and the globs it does not apply to, written as `tell: glob, glob` or as a mapping, and every source merges. A glob matches the file name and the whole path, so `README.md` matches in any directory and `docs/**` matches one tree. A check on bare text carries no path, so an exception never applies to it and chat stays judged by the plain rules.

### Fixed

- A fenced region now leaves the prose whole, delimiters included. The line filter dropped the fence markers and kept what was inside them, so a YAML example in a README reached the rules as a paragraph and a profile that lists the phrases it refuses was flagged for listing them.
- The profile is found in a host that starts without `HERMES_HOME`, which the desktop backend does. The plugin fell back to `~/.hermes`, found no `voice-profiles` there, and ran the generic rules while reporting `(base)`; the settings were read correctly, so the failure looked like a missing profile rather than a path. Both halves now resolve `HERMES_HOME`, then `%LOCALAPPDATA%\hermes`, then `~/.hermes`, taking the first with a `voice-profiles` folder.

## [voice-gate 1.3.1] - 2026-11-04

### Added

- Version `1.3.1`. The gate reads the prose in plain text, reStructuredText, AsciiDoc, Org, LaTeX, HTML and PDF, not only Markdown, and the commit gate reads the same set through the plugin's own extractor. PDFs are decoded with the standard library, Flate and uncompressed content streams through the `Tj` and `TJ` operators, because the backend interpreter carries no PDF package. Code is removed before counting for every format, and a file that is mainly source code carries no prose and is skipped instead of judged. The Vale pack declares the new extensions it can parse, so `.txt`, `.rst` and `.html` files reach the same rules.

## [voice-gate 1.3.0] - 2026-11-04

Version `1.3.0` shipped the work 1.1.0 and 1.2.0 had carried, so those numbers never released on their own.

### Added

- **voice-gate.** The manifest name is `Voice Gate`, so Settings ▸ Plugins and the plugin list show the product name instead of the slug; the catalog entry, the index entry and the install commands keep `voice-gate` as the key, which the catalog matches through its install sidecar, and existing settings moved to the new `plugins.entries` key in every profile. The generic rule set grew from eight families to seventeen: significance inflation, copula avoidance, promotional adjectives, hedge stacking, signposting, wordy constructions, chained transitions, trailing qualifiers, gerund openings and the negation-then-positive frame, alongside the existing verdict openers, closing offers, cliché openers, conclusion signposts, AI vocabulary, bold pseudo-headings and bold lead-in bullets. Thresholds sit at the density where a pattern starts rather than where a single word lands; four real documents, including an 8,390-word changelog, report nothing at the new settings.
- **voice-gate:** The five per-bot switches are back in Settings, one checkbox per bot, read from the default profile's config because a page opened on the Herald scope writes Herald's own file; untick one and that profile stops being gated, and a fresh install ticks all five. The public edition gained `voice_gate_check`, so a turn can ask what the rules see without waiting for the nudge. An explicit `min_words: 0` now turns the word floor off instead of silently becoming 200, and both editions answer the check tool with the same `checks` payload. Vale reports are cached by file stamp and config stamp, so a second pass over an untouched file does not spawn the binary again. Each edition ships `tests/test_voice_gate.py`: twenty-one checks over the rule families, the code-span exemption, the bot switches, the floor, the tool registrations and the turn path, runnable with no dependencies because the host has neither PyYAML nor pytest for plugin code.
- **voice-gate:** Vale is now part of the turn. New tool `voice_gate_vale` installs Vale 3.26.0 from a pinned release whose sha256 is checked before anything is unpacked, keeps the copy under `HERMES_HOME/plugin-data/voice-gate/`, and routes the download through the `pre_tool_call` approval prompt; an existing binary from the setting or from `PATH` is used as-is. The plugin ships a style pack in `styles/VoiceGate` generated from `rules.py` by `scripts/gen_style_pack.py`, with `scripts/check_style_pack.py` failing when the two drift. The new `Vale second opinion` setting adds one line to the nudge with a per-rule breakdown and the first position, and speaks only above `Vale minimum alerts`, three by default. A missing binary, an unreachable release or fewer alerts than the threshold leave the nudge as the engine wrote it.

## [voice-gate 1.0.0] - 2026-11-04

First release. Voice Gate reads the Markdown a turn changed and reports the AI tells that make writing sound machine made, then asks for one more pass before the turn finishes. Two editions ship in one release: the public build carries one rule set and needs nothing else installed, and the personal build loads a writing profile so the same checks are measured against one person's habits.

### Added

- **voice-gate (public).** A `pre_verify` hook that lints changed `.md`, `.markdown` and `.mdx` files against eight families of tell: verdict openers, closing offers, cliché openers, conclusion signposts, negation triads, bold pseudo-headings, bold lead-in bullets, and a vocabulary list. Thresholds sit where a pattern starts, so one bold heading is not a finding. Modes are `warn` (ask once), `improve` (keep asking inside the host's nudge budget) and `skip`. `min_words` ignores short documents. Every path is fail-open: a missing file or a broken rule returns nothing and never blocks a turn.
- **voice-gate (personal).** The same engine, parameterised by a profile document in `HERMES_HOME/voice-profiles` (YAML or JSON). A profile replaces any rule list, adjusts thresholds, sets `applies_to` for named Hermes profiles, and can flag em dashes. With no profile it behaves exactly like the public build.
- Three tools in the personal edition: `voice_gate_check` reports findings on text or files, `voice_gate_profile` shows, lists or validates profiles, and `voice_gate_learn` builds a draft profile from a corpus of chat exports, mail or documents, with measured habits and candidate openings and closings.
- A bundled `voice-profile-builder` skill covering what to collect, how to read the measurements, and how to check a finished profile against writing the person is happy with.
- Both editions share one `rules.py`, byte-identical, and code fences and inline spans are stripped before counting, so documentation about a banned phrase never trips that phrase.

## [hermes-agent-desktop 1.0.2] - 2026-11-02

### Fixed

- hermes-agent-desktop. `desktop_window` launch could start any executable with any arguments, and `desktop_install` took a model-chosen `version` and trusted that release's own `checksums.txt` when no digest was pinned. Launch/close (also inside `desktop_batch`), install, and the first call that auto-installs a missing binary now go through Hermes's approval prompt via a `pre_tool_call` hook, the `version` tool argument is gone, and only releases with a digest pinned in the plugin install. The prompt needs Hermes Agent v2026.7.7 (0.18.1) or newer; an older host ignores an `approve` hook return and runs the call.

## [reddit 1.0.1] - 2026-11-02

Reads work before a login now. With only the Reddit app saved, the plugin asks for an app-only `client_credentials` token and reads public subreddits, search, threads and user history. Writes and private data still require the account login. `reddit_thread` keeps each comment's reply depth, reports how many comments Reddit still holds back and where, and fetches them from `/api/morechildren` when `expand_more` is on. New `reddit_user` tool reads a user's overview, submitted posts or comments. A `429` waits out `Retry-After` / `X-Ratelimit-Reset` once instead of failing the call, and a thread with more replies than the first page no longer returns an empty `more` stub with no count and no ids.

## [reddit 1.0.0] - 2026-10-31

### Added

- **reddit:** version `1.0.0`. First stable release. Runs on your own Reddit app. Save the client id and secret in the plugin config, and log in with the published-app code flow against a loopback catcher on `http://localhost:8080`; the permanent refresh token is stored per profile and renewed automatically. Twelve tools cover the account: `reddit_setup`, `reddit_login`, `reddit_status`, `reddit_subreddit`, `reddit_search`, `reddit_thread`, `reddit_submit`, `reddit_comment`, `reddit_vote`, `reddit_manage`, `reddit_inbox`, and `reddit_api` for any endpoint the curated set does not wrap (moderation, modmail, wiki, flair, prefs). Writes publish under the logged-in account. Reads use that token too, so private subreddits, saved items and mod queues work. The Desktop settings page saves and verifies credentials, starts and finishes the login, checks the account and logs out, through `/api/plugins/reddit/`. The page takes its fields, buttons and tags from the plugin SDK, so it follows the active theme instead of painting a light-mode form. `hermes reddit setup|login|complete|status|logout|smoke|api` does the same from a terminal. No third-party dependencies; requests share one cached session per process, and config/token writes are atomic and safe under concurrent tool calls.

## [provider-status 1.6.9] - 2026-11-05

### Fixed

- The checkbox theme fix restyled every checkbox in the app, not only the provider rows it belongs to. `[data-slot="checkbox"]` matched the sidebar, dialogs and settings controls while any provider dialog was open. Both rules now sit under `[data-ps-row]`, the marker on this plugin's own provider row, and the select rule stays under `[data-ps-select]`. This was item 1 of the catalog review at `1264a8e1`; the entry shipped at 1.6.8 with the reach-in still in the tree. `scripts/admission_check.py` now reports this plugin clean.

## [provider-status 1.6.8] - 2026-11-01

The renewal-day and add-provider dropdowns paint outside the setup dialog instead of stopping at its edge.

### Fixed

- The renewal-day menu and the add-provider picker were absolutely positioned
  inside the setup dialog's scroll body, and the provider rows sit inside a
  second clipping box, so an open list was cut off at the dialog edge: the day
  menu measured 266px tall with 123px visible. Both are house `Popover`s now,
  portalled into the dialog shell that `DialogContent` deliberately leaves
  unclipped, so they paint past the edge and flip upward when the row is near
  the bottom. The old workaround that lifted the inline overflow of every
  scroll ancestor is gone, and Radix owns the outside press and Escape.
  `tests_popover_clip.mjs` guards the structure and fails against the previous
  markup.
## [cdp-manager 1.0.2] - 2026-11-01

### Added

- **cdp-manager:** version `1.0.2`. First public release; the `1.0.1` tag was retired before it shipped, so the version reads `1.0.2`. The status-bar chip and its dialog show every local Chrome DevTools Protocol port's health (normal when down, bold when up, amber on issues, red when a port needs a reboot) and launch, stop or recheck each one, windowed or headless per port, restarting a live port when its mode changes. Each port remembers a profile: Hermes (isolated), a personal Chrome profile when that Chrome is closed, or Guest. One port can be marked managed, and a backend supervisor keeps it up, auto-starting it when down and force-rebooting it after repeated launch failures. The `cdp` agent tool does all of it from chat - `status`, `launch`, `stop`, `recheck`, `prefer`, `wedged`, `unwedge` - targeting the managed port when none is named. Launches always pass a startup URL and pin `--profile-directory=Default` on isolated dirs, so a fresh instance never boots into Chrome's profile picker, a browser_ui-only state where every CDP client fails with `Failed to open a new tab`; `wedged` detects that state on a live port and `unwedge` stops and relaunches. State lives in the plugin's own `config.json` inside the plugin directory.
## [hermes-jev-routing 1.1.1] - 2026-11-01

### Changed

- hermes-jev-routing 1.1.1. The listed edition routed by reaching into the running agent: it walked the caller stack and the `gc` objects to find the cached agent, called `switch_model` mid-turn, rebound `_interruptible_api_call` to hold a send, and priced rows from private usage modules. Catalog review at `ef98501c` rejected that, so the listed edition now routes only through the middleware it already registers. It rewrites the model and the reasoning effort on the provider the turn is already bound to, reports a cross-provider pick as `blocked: cross-provider` instead of sending it, prices rows from a `pricing` block written into the routing JSON, estimates context as characters over four, and reads the Jev key through the host secret scope with `TYPESAFE_API_KEY` declared in `requires_env`. The confirm row no longer holds a send, because a plugin cannot stop one. It offers the pick, the turn answers on its current model, and approving moves the session for the following sends. Personal keeps every reach-in. `LIMITATIONS.md`, identical in both editions, records each blocker and the core hook it needs.

### Fixed

- hermes-jev-routing. Auto mode wrote the thinking level straight into whichever of `reasoning_effort` / `reasoning` the request carried, so on a Responses-style request (`openai-codex`) the `{"effort", "summary"}` object was replaced by a plain string and `summary` was dropped, changing the wire shape Hermes builds. The "effort already matches" check compared `str(dict)` with the level, so it could never match. `route.set_thinking_level` now copies the object and replaces only `effort`, keeps the plain-string behaviour for `reasoning_effort`, and both the routing rewrite and the `/jev-routing revert` pin use it.

## [hermes-agent-desktop 1.0.1] - 2026-10-31

### Fixed

- hermes-agent-desktop. `desktop_apps` reported a failed `list-apps` as an empty list under `ok: true`, so a broken enumeration read as nothing running. A failed half now returns its own error envelope. `desktop_install` with `action: "verify"` probed only the plugin's own copy, so a host that already had the binary on PATH was reported as broken; it now probes the binary the tools actually use, and `status` reports that path.

## [hermes-agent-desktop 1.0.0] - 2026-10-31

### Added

- **hermes-agent-desktop:** new plugin, version `1.0.0`. Nine tools that let Hermes read and operate Windows apps through the accessibility tree instead of the screen: `desktop_status`, `desktop_apps`, `desktop_snapshot`, `desktop_find`, `desktop_act`, `desktop_window`, `desktop_clipboard`, `desktop_batch`, `desktop_install`. Actions are semantic and headless by default, so a click or a field write does not take focus, move the cursor or synthesize keystrokes, and every call returns the tool's own JSON envelope with a retry disposition. It wraps the Vercel Labs `agent-desktop` binary and does not bundle it: `desktop_install` downloads the official release for the running Windows target, verifies the archive against a sha256 pinned in the plugin, extracts only the expected executable, and proves the install by running `version` and `status`. No other tool uses the network and none stores credentials. Windows only. The public edition is identical to personal, because every capability is registered through `ctx.register_tool`, so no listing cut was needed.

## [better-session-appearance 1.2.4] - 2026-10-31

The status dots can wear the session's own colour while a turn is running, if
you ask for it.

### Added

- **Settings ▸ Plugins ▸ Better Session Appearance** and the one switch on it,
  **In-Progress Status Dots use Session Color**. Off, as shipped: working, needs
  input, stalled and unread keep the app's blue, amber and green. On: those four
  take the colour set for that session, and the icon shape still carries the
  state. Background and draft dots follow the session colour either way, and a
  session with no colour always keeps the app's state colours.

The listed edition has no status dots to colour, so it takes the version line
and nothing else this time.

## [better-session-appearance 1.2.3] - 2026-10-31

Every status dot can carry its own icon, not only the idle one.

### Added

- **Status Dots** in the Appearance panel. Working, needs input, stalled, background, unread and draft each take a Codicon, picked from the same searchable grid as the idle icon. The link opens its own panel beside the Appearance menu, one state is selected at a time, and the grid below edits that state. The icon rides on the state's own colour rather than replacing it, so amber still reads as a prompt waiting for you. **Suggest** fills the six with a starting set, **Clear** returns them to plain dots. The panel takes the Appearance popup's width, so its grid lands on the same columns as the icon grid next to it.
- Background and draft dots take the session's own colour when the session has one, instead of the app's grey.

### Fixed

- The listed edition's README described bold titles and Auto Rules, and its screenshot was the personal UI with both on show. The page now documents the color and idle icon that the edition actually installs, and the mismatched image is gone.

## [provider-status 1.6.7] - 2026-10-31

One login can no longer fill the account pool with copies of itself.

### Fixed

- Grok and Codex rotate the refresh token on every use, and the pool matched an
  account by that token. Every refresh therefore looked like a fresh login and
  appended a duplicate: one Grok account reached 338 entries (336 of them
  already expired) and one Codex account reached six, which grew `config.json`
  to 416 KB that every poll parsed. Accounts now match on the token's subject
  claim, then email, then a digest of an opaque token.
- Every pool write collapses the pool to one entry per identity, keeps the
  newest expiry and points `account_index` at it, and caps the pool at 24
  accounts. A pool that already holds duplicates heals itself at plugin load,
  so an existing `config.json` shrinks on the first start after the update.

## [provider-status 1.6.6] - 2026-10-31

The trash glyph on a provider row deletes one key instead of the whole provider.

### Changed

- A provider that holds two or more keys keeps its row when you press the trash
  glyph. The press deletes KEY #1 and the row stays with the remaining keys, so
  one click cannot throw away accounts you still have; the last key still deletes
  the provider. The active-key mark follows the cut: a key after the removed one
  shifts up, and an active first key becomes the new first key. The glyph's
  tooltip names the action it will take.
- The removed key travels with the save. In the personal edition its library slot
  and its Hermes `.env` carrier are purged and the value is tombstoned, so the
  next poll cannot put it back into the pool.

## [provider-status 1.6.5] - 2026-10-27

The Discord presence draws a ten-cell bar, and the listed edition stays inside
the catalog's credential rules.

### Changed

- Both bars in the Discord presence draw ten cells instead of five, so a quota or
  context reading is a gauge rather than a stub. `discord_bar_width` sets the
  width anywhere from 3 to 20 cells, and its default is now ten; a status that
  shares the row with Discord's member list keeps the shorter look by dropping
  it back to five. The presence picks the new default up on the next gateway
  restart, because it reads its settings once at registration.
- The listed edition reads no vendor CLI auth file, refreshes and writes back no
  Grok or Codex token, writes no Hermes `.env` on exhaustion, and keeps no copy
  of a key in a plugin-owned `library.env`. Exhaustion and renewal-day rotation
  record the pool index, and an expired OAuth token asks for a new login. Key
  pools stay in the plugin's own `config.json`. This is the 1.6.4 credential
  work, which had no release of its own.

## [provider-status 1.6.3] - 2026-10-20

The pet bubble follows a settings save at once.

### Fixed

- The pet bubble's settings query polls every 60s, so a save in Settings > Plugins
  took up to a minute to show, and the quota chips kept their old values until
  the next poll. The Desktop half now refreshes the pet settings and the quota
  chips as soon as the backend broadcasts
  `plugin.provider-status.settings.changed`.

## [intelligent-tool-break 1.3.6] - 2026-10-27

Hermes fires `on_session_end` after every turn, not at the end of a session, so
the session lifecycle hooks were acting on the whole process.

### Fixed

- intelligent-tool-break. A turn ending in one chat dropped another chat's in-flight calls. `on_session_start` and `on_session_end` cleared every session's tracked calls and `/again` budget for the whole process, so `/break` reported "Nothing in flight" for a tool still running in another session. Both hooks act on the session they are given now, and `on_session_end` no longer drops calls at all, because a call can still be running for the same session across a turn boundary. A surface with no session id keeps the process-wide reset, and a deleted session takes its rows and budget with it.
- intelligent-tool-break. Two sessions running an identical command shared one `/again` budget, because the key was the tool name and args alone. The budget is keyed by session as well now, so each session gets its own two uses.

## [intelligent-tool-break 1.3.5] - 2026-10-20

The break commands belong to the chat you type them in.

### Fixed

- intelligent-tool-break. `/break`, `/again` and `/break-status` acted on the whole gateway process, so a break in one chat could kill a tool running in another. Each command now scopes to the session that invoked it, an explicit `--session-id` still wins, and a row with no recorded owner stays visible everywhere. A deleted session's rows are dropped by `on_session_delete`, which fires on Desktop deletes that never reach `on_session_end`.

## [provider-status 1.6.2] - 2026-10-16

The two presence lines that wore color emoji wear monochrome glyphs now, so the settings form and the Discord presence read as one family.

### Changed

- Tokens/sec and the idle/thinking state were the only two lead characters that rendered as color emoji (U+26A1, U+1F4CA) beside a monochrome glyph family. Tokens/sec uses U+21AF and the state line uses U+25A5. The settings form takes the new defaults on load; the presence needs a plugin reload (Save and Reconnect, then toggle Provider Quota Status off and on under Capabilities, Plugins).

## [memory-review 1.2.6] - 2026-10-16

The chrome-menu row is placed by proof now, not by elimination.

### Fixed

- Personal edition: the row landed in the profile switcher as well, because that menu carries the same `add` + `cloud-download` + `settings-gear` glyphs as the shell menu. A menu counts as the shell menu only when it also carries a chrome verb no other menu renders (`layout-statusbar`, `layout-menubar`, `multiple-windows`), which is one rule instead of one exception per menu. The composer model catalog from 1.2.5 and the profile switcher are both refused by it, and the status-bar chip stays the primary door.

## [provider-status 1.6.1] - 2026-10-15

The current session's speed, context, and remaining quota now speak from Discord, with a configurable pet bubble and an emoji per line.

### Added

- Both editions: Discord bot presence for the provider backing the current session. Tokens/sec, context occupancy, and remaining quota (or credit balance) rotate or sit on one line. `/pulse`, `agent_pulse`, and `hermes session-pulse` report the same numbers. Bar width defaults to 5 cells so it fits Discord's member list, and is configurable.
- Both editions: every presence line carries its own configurable emoji, with the emoji entry sitting directly above that line's switches. `discord_status_emoji` now covers only idle and thinking, since a metric line wearing both was redundant.
- Both editions: pet-bubble settings sit above the Discord ones. Master switch on by default. Pick current vs worst provider, remaining / used / balance / auto, rewrite the line (name, percent sign, unit word), allowlist providers, and set wait / error thresholds plus bubble TTL.

### Changed

- The presence release was renumbered to 1.6.1 before it was announced, and 1.7.0 is retired with its tag removed. A copy still reporting 1.7.0 will not self-update, because the version compare sees nothing newer. Reinstall from `main` to realign it.

## [iteration-budget-meter 1.4.0] - 2026-10-14

The live N/60 count can speak from the pet bubble while a turn runs.

### Added

- Both editions: while a turn runs, the pet bubble shows the live N/60 iteration count, id-replaced in place. Idle stays silent. The status-bar chip is unchanged.

## [provider-status 1.6.0] - 2026-10-14

Quota numbers can speak from the pet bubble now.

### Added

- Both editions: when a pet is on screen, one quota line goes in its speech bubble. The active model's remaining balance when it has a number, otherwise the worst enabled provider. Wait tone near a ceiling, error at exhaustion. Status-bar chips stay the fallback on older hosts and when no pet is adopted.

## [memory-review 1.2.5] - 2026-10-14

The chrome-menu row no longer lands in the model picker.

### Fixed

- Personal edition: glyph matching for the shell menu also matched the composer model picker (`add` plus `settings-gear`). Menus with a search field or `data-model-menu-row-badge` are refused now. The status-bar chip was already the working door.

## [sessionretitler 1.1.1] - 2026-10-14

Renames no longer need a trust flag in config.yaml.

### Changed

- Both editions: the plugin registers its own `sessionretitler_title` auxiliary slot (inherits the host `title_generation` route) and routes the rename call through that key. Pin a cheap fast model for it under Settings, Models, Auxiliary. The old `allow_task_override` config line is no longer required.
- Public edition: listed copy of the same rename path. The title write through `agent.title_generator` and `hermes_state.SessionDB` is disclosed because Hermes has no plugin SDK title-write seam yet.

## [rss-reader 1.2.0] - 2026-10-14

Digests leave the reader page and arrive where you already talk to Hermes.

### Added

- Both editions: the `rss-reader:daily-digest` Automation Blueprint. `/blueprint rss-reader:daily-digest` fills in the time, which days, and which articles, and the scheduled job builds the digest through the rss tool. It also shows up in the dashboard Blueprints tab and the Desktop Cron page, and the cron job it creates keeps running even if the plugin is later disabled.
- Both editions: `/rss digest-post [unread|saved|all]` posts the digest straight into the Telegram or Discord chat you ran it from, with inline Save, Open, and Mute feed buttons per story. Buttons are pattern-scoped and never touch core button flows. In the desktop app and CLI, where there is no gateway chat to post to, the command prints the digest instead.
- Public edition: one disclosed read of `gateway.session_context` to learn the chat a `/rss digest-post` command came from, the same read the core's own `/blueprint` command uses for its delivery origin. The import is guarded and the command degrades to a text digest without it.

## [iteration-budget-meter 1.3.1] - 2026-10-14

The step count holds up mid-turn, and the chip stays plain.

### Fixed

- A totals fetch that lands while a turn is running anchors the live step count at the turn's start, so the chip never reads 0 steps for a turn that is already underway (cold retries, catch-up, and queued pending fetches all land mid-turn).

### Changed

- The chip no longer carries the per-turn warning color; the warnings and the accent ceiling-suggestion line live in the popover.

## [iteration-budget-meter 1.3.0] - 2026-10-13

The chip shows the session's cumulative totals; the per-turn readout stays in the popover.

### Added

- Both editions: the chip shows `N turns · M steps` for the focused session — user rows and assistant rows in the durable display transcript, the same counters the CLI bar keeps. Totals load lazily via `session.resume`, survive app restarts and compaction rotations, and the step count animates live while a turn runs.
- The popover carries the session totals above the existing per-turn readout and request stats.

### Changed

- Chip chrome (tone, weight, icon) now matches the native statusbar items; the accent color stays only on the ceiling-suggestion line.
- Cold sessions and fresh drafts stay hidden until their totals land; failed loads retry on a timer, and session switches never show another session's totals.

## [memory-review 1.2.4] - 2026-10-11

The status-bar chip shows how many writes are waiting.

### Added

- Both editions: the chip label is `Memory · 3` when writes are pending, and plain `Memory` when the queue is empty. Re-registering the same declarative item keeps the bar's show/hide checkbox.

## [memory-review 1.2.3] - 2026-10-11

The status bar has a native Memory chip. The chrome-menu row sits next to New chat.

### Added

- Both editions: a native status-bar chip with the app's Brain glyph. Right-click the bar to show or hide it.

### Fixed

- Personal edition. The chrome-menu row was appended after the menu was sized, so it sat below the box and React could wipe it. It now inserts next to New chat.

### Changed

- Both editions: the dialog's memory store meter uses the Brain glyph at 0.65rem, matching Settings → Memory.

## [memory-review 1.2.2] - 2026-10-11

The review dialog and palette follow the app language. The chrome-menu row no longer depends on English labels.

### Added

- Both editions. Dialog, palette, and status copy ship an `es` bundle through `ctx.i18n.register`. English is unchanged.

### Fixed

- Personal edition: the shell-menu row used English labels (`New session`, `Settings`) to find the app chrome menu, so it never appeared in Spanish or any other UI language. It now matches that menu by the locale-stable Codicon classes on New chat, Settings, and Update Hermes.

## [prompt-enhance 1.2.0] - 2026-10-11

The edit dialog can rename a saved prompt and format its body with a markdown toolbar.

### Added

- Both editions: the prompt name is an editable field in the edit dialog. Save writes the name with the body.
- Both editions: a markdown toolbar sits above the prompt body (headings, emphasis, lists, link, table, code, block, rule).

## [provider-status 1.5.14] - 2026-10-09

Log out signs the provider off in one click, Connect opens the system browser, and the chip line stays up when Grok has a large account pool.

### Fixed

- Log out dropped only the active OAuth account, then rematerialized the next one, so the row still said Log out. One click now clears the whole pool and the email.
- Connect and the Codex authorize page used `window.open`, which Hermes Desktop denies. Both now go through `ctx.os.openExternal`.
- `/active` imported yaml outside its error handler. The dashboard backend has no yaml module, so the active-model marker never resolved. The small `model:` block is parsed without yaml.
- An exhausted Grok account scanned the whole OAuth pool in one poll and cold `/status` passed the 30s gateway timeout, so the chips vanished. Rotation now scans at most 8 accounts per poll.

### Changed

- Personal edition: extra accounts live in plugin `library.env`. The plugin does not read or write lifestyle `.env`. Hermes `.env` still gets the active runtime key, and numbered siblings for native providers when Apply Changes is on. Tavily extras stay in the library; only the active Tavily key is written to Hermes `.env`.

The pack remains at 1.22.0. Restart Hermes Desktop after updating; the Python half does not hot-reload.

## [hermes-jev-routing 1.0.0] - 2026-10-04

Per-turn model routing from TypeSafe Jev. The full feature set ships here; there is no earlier release for this plugin, and it is not in the pack.

### Added

- Jev reads the current message, a short history excerpt, the cwd, the live context size, and the spend snapshot, then answers four typed questions: task kind, complexity, capability deserved, and deep reasoning.
- The demand score picks a tier: `0.55·complexity + 0.45·capability` plus a reasoning nudge, floored per task kind, then clamped by a confidence guard, a budget guard, and a cache-penalty hold. `xpremium` only fires when the demand already rounds to `premium` and the kind confidence clears the threshold.
- Five tiers with candidate chains, ten kind specialists with `minTier` and `priority`, and a zero-cost free pool that can be tried before the chains or only after them.
- Codex quota gates the Sol family on remaining account quota. The stricter of the provider floor and the row floor wins, equality passes, and a missing, stale, or reset reading follows `onUnknown`.
- The live session moves onto the pick before the provider client is built, and the row's thinking level lands with it.
- A spend ledger records real cost beside the routing file and feeds budget pressure, so soft and hard caps downgrade a tier instead of overspending.
- The judgment line appears under the prompt that was just sent, before the model works, one row at subline size, with the kind and each score against its range.
- A thin confirm strip under that line, in the same subline, offering Yes, No, Free, and each tier name. Yes and X are the only bold words.
- `/jev-routing` with `why`, `route`, `revert`, `budget`, `suggest`, and `on`, `off`, and `mode`. The `jev_route` tool classifies a request without switching.
- Plugin settings override the JSON file only when they are actually set. An unset key leaves the tuned file value alone.
- `suggest` ranks a scores file into proposed chains, and `--write` saves a generated layer that the hand table always overrides.

### Fixed

- The in-place switch reused the current provider's credential, so a cross-provider pick raised and the session stayed on the old model. The destination key, base URL, and API mode are resolved before the client is rebuilt.
- The session chip update used the agent session id, which the gateway rejects. It now uses the focused runtime session.
- The desktop half failed to load with `Unexpected token 'export'` because a helper function was missing its closing brace.
- The judgment line rendered white because the colour mixed against an undefined token, and it wrapped onto a second row. It now uses the theme's muted token at 60 percent and stays on one row.

### Notes

- Not in `hermes-pack.yaml`. Install it separately.
- A prompt that is empty, a slash command, an acknowledgement, or a short continuation in a live conversation does not re-route.
- A model the provider no longer serves loses the chain, while an unreadable catalogue keeps every row so a degraded probe cannot strand routing.
- An ineligible turn sets the interrupt both API paths check, so the prompt is not sent on a model under its quota floor.
- The judgment line is a page memory, not a durable transcript entry, and there is no status-bar surface in the plugin SDK. Those two Pi surfaces have no Hermes equivalent.

## [reasoning-switch 1.1.4] - 2026-10-03

Two more defects from a live report.

### Fixed

- The chip is inert on a brand-new chat, before its first send. A draft has no runtime session id until then and `config.set reasoning` is session-scoped, so there is nothing to scope the write to. See Unreleased for the honest behavior that replaced a pending-pick mechanism which could not land.



## [reasoning-switch 1.1.3] - 2026-10-03

Two defects from a live report.

### Fixed

- Clicking the chip on a session running a level outside the rotation no longer does nothing. The session's level comes from the gateway, so an external pick (`/reasoning`, the composer menu) or a row unchecked in the dialog left `displayed` absent from the rotation; the old code bailed out and the chip was dead until the dialog was reopened. It now steps up to the nearest rotation entry, or to the bottom when the session sits above every entry, so there is always a way off.
- The chip label no longer wraps on `Extra High`. The statusbar reuses the app's own compact spellings (`XHigh`, `Med`, `Min`, `Off`) and the label and counter carry `whitespace-nowrap`. The dialog keeps the full names.

## [reasoning-switch 1.1.2] - 2026-10-03

The chip now reads the level the session is actually running, instead of guessing it from a read it could not trust.

### Fixed

- Clicking the chip no longer looks like it worked when the gateway refused the write. `config.set` answers the value it accepted, so a refusal leaves the chip on the real level.
- The 4-second reconciler no longer paints the profile default back over a pick the user just made. It cannot tell a pinned session override from an inherited default, so `session.info` is now the signal that repaints the chip.
- A pick changed elsewhere (the composer reasoning menu, `/reasoning`) updates the chip and the dialog's current marker, so the prompt-limit bookkeeping follows the session.
- Switching sessions clears the previous chat's level while the new read is in flight, so the chip never shows the other session's effort.
- A clamped pick reads as both ends (`Ultra→Max`) and the tooltip names the wire level, so a Hermes-internal step is never presented as a wire level the route does not have.
- Overlapping reads share one promise per session, so a slow read started before a click cannot repaint a level the user rotated away from.

The auto-demote path settles on the accepted level for the same reason.

### Removed

- **compact-reasoning-label:** removed from personal and public. The Desktop model pill no longer includes the reasoning effort. That word lives on the reasoning pill, so the plugin's strip did nothing on current builds. The old trees stay in git history.

## [intelligent-tool-break 1.3.4] - 2026-10-03

The public edition keeps its settings in `ctx.storage` instead of `window.localStorage`, so it stays inside the plugin SDK.

### Changed

- Public edition. Color grades and the hidden-tools list read and write through `ctx.storage`, captured in `register(ctx)` and released in `ctx.onDispose`.
- Public edition: the settings dialog subscribes to a store version counter, so a change made in one surface re-renders the others. `better-session-appearance` already used this pattern.
- Personal edition is unchanged and keeps its `localStorage` behavior.

Stored values are treated as untrusted: a wrong type, a null, an out-of-range number, or a storage backend that throws all fall back to the defaults instead of breaking the strip. If `ctx.storage` is unavailable, the change stays session-local.

Verified against the migrated helpers with a fake storage backend: defaults with no backend, round-trips for both keys, values stored as objects rather than JSON strings, five corrupt-input cases, the 3600-second clamp, a throwing backend, and the React subscriber notification. 18 checks, all passing.

## [provider-status 1.5.12] - 2026-10-03

z.ai renamed the quota limit type to `CREDIT_LIMIT`, so the GLM fetcher stopped matching any window and the chip reported a full quota while the account was close to its weekly cap.

### Fixed

- Both editions: `CREDIT_LIMIT` is accepted next to `TOKENS_LIMIT`, and `unit` still decides the window (3 = 5h, 6/4 = weekly, 5/7 = monthly).
- Both editions: quota windows are emitted only when the API actually reported them. The `0.0` defaults used to append a phantom monthly row reading 100% remaining.
- Both editions: the headline percentage is omitted when no burst window was reported. Sending `null` was the wrong fix, because the desktop fallback reads `Number(null)` as `0` and would have drawn a full 5h window.
- Public edition: the weekly window reaches the status-bar chip. GLM now uses the multi-window renderer already used by OpenCode Go and Codex, so both the burst and the weekly allowance are visible.
- Personal and public versions are aligned at 1.5.12. They had drifted (personal 1.5.10, public 1.5.11).

Personal keeps its single-value GLM chip, so its chip still shows the 5-hour headline and the weekly allowance stays in the Providers dialog.

## [prompt-enhance 1.1.1] - 2026-10-01

The listed edition reads and writes the composer through the draft API, so enhance, undo, and replace keep working when the Desktop markup moves.

### Changed

- Public edition. Enhance, undo, and replace use the composer draft API.
- Public edition: Add on a saved prompt appends to the draft. Personal Add still inserts at the caret.

## [prompt-enhance 1.1.0] - 2026-09-22

The library header can set a thinking level for the enhance call. The session model stays as it is.

## [better-session-appearance 1.2.2] - 2026-10-01

Saved Auto Rules now reach the sessions they were written for.

### Fixed

- Personal edition: a rule applied only when a session's title changed, so it
  never reached the sessions already in the list. The applied-state check now
  tracks the matched rule instead of a title diff, and a rule lands as soon as
  its row exists. Saving or removing a rule in the panel applies it right away
  instead of waiting for the title to change.
- A session that already carried a rule is left alone on further observer
  passes, so the sidebar list does not rewrite stored state while idle.

## [sidebar-manager 1.0.1] - 2026-10-01

Sidebar Manager keeps working after a Hermes desktop update changed how the sidebar nav buttons are marked.

### Fixed

- Personal edition: the editor glyph reappears next to New session and nav rows become clickable again. Every nav row now wraps its button in a context-menu trigger, which replaced the button's own `data-slot` value, so the editor's selector matched nothing and the plugin did nothing at all. Nav buttons are now matched on the attribute that survives.
- Personal edition: the README's nav row list named a row the app does not have.

### Changed

- Public edition: its README described the personal editor, including session-section hiding, drag grips and the edit-mode glyph. None of that is in the listed edition, which drives core nav rows through the SDK's sidebar prefs area from a statusbar dialog. The README now matches the shipped behavior and states the section limit.

## [provider-status 1.5.10] - 2026-09-30

Deleting a saved key in the personal Providers dialog now stays deleted. The
next status poll no longer restores it from the local credential files.

### Fixed

- Personal edition: a removed key is cleared from the library and Hermes
  carriers. A fingerprint prevents a stale file from importing it again,
  without storing the raw key in the removal record.
- The active key and numbered slots stay valid after a deletion, including
  after a middle key is removed.
- Public edition: the per-key delete control is gone because this build cannot
  update the personal credential files. Removing a whole provider row remains
  available.

Restart Hermes Desktop after updating; the Python component does not hot-reload.

## [rss-reader 1.1.0] - 2026-09-24

RSS Reader moves browser frames and ticker events onto the desktop SDK, restores the headline ticker at launch, and tightens YouTube cookie handling.

### Changed

- **rss-reader.** Use the desktop plugin event bridge instead of a commands-file poll, and the sandboxed frame API for the browser and YouTube player.

### Fixed

- **rss-reader:** Restore the marquee class on the ticker track when reduced motion is off, so headlines scroll at launch.

### Security

- **rss-reader:** YouTube cookie settings accept pasted header or Netscape export text. Unix-rooted and Windows drive-rooted paths are rejected, so the dashboard no longer reads local files or forwards their contents to YouTube.

## [provider-status 1.5.9] - 2026-09-24

DeepSeek's pricing period and GLM's peak/off-peak schedule now appear beside their status values, each with a countdown to the next change.

### Added

- **provider-status:** A color-coded speedometer shows whether DeepSeek is in peak hours. Its native hover shows the time until the next period change. Peak hours are 01:00–04:00 and 06:00–10:00 UTC on weekdays. Weekends and listed 2025 and 2026 Chinese public holidays are off-peak. The built-in holiday calendar ends on 2026-12-31.
- **provider-status:** GLM chips show a peak/off-peak speedometer and countdown based on Z.AI's documented Coding Plan schedule, even when the quota response omits a weekly window. Peak hours are Monday-Friday 14:00-18:00 Singapore time (UTC+8); off-peak model use consumes half the standard credit rate.

### Changed

- **provider-status.** Personal, public, and pack overview documentation now lists all 17 registered providers.

## [rss-reader 1.0.9] - 2026-09-23

Tighter grading calibration, a reader-interests skill block, and a `reclassify` action that re-judges up to 720 articles per run.

### Added

- **rss-reader:** version `1.0.9` (both editions). The grading skill gains a Reader interests block: an editable ```interests fence where the reader lists their own topics, one per line. Grading treats a strong interest match carrying something usable (product, tool, opportunity, resource) as interesting; bare topic mentions stay normal and interests never escalate to important. The in-plugin scaffold that seeds a missing skill includes the same block.
- **rss-reader:** `reclassify` Hermes tool action (both editions). Re-runs classification across up to 720 articles, including already-tagged ones, so rubric changes apply retroactively. It processes distinct batches and reports when more articles remain for a later run.
- **rss-reader:** the duplicate `mute` tool action is removed (both editions); `add_filter` is the single rule-creation path for keyword and tag mutes. The `/rss mute <keyword>` slash command is unchanged.
- **sessionretitler** (formerly `session-retitler`): version `1.1.0`. Retitles the session every N titleable user messages from the latest exchanges (llm-rank rewrites, user titles untouchable). Now pinned in the pack (pack `1.16.0`).

### Changed

- **rss-reader:** tightened grading calibration against over-flagging. Important now requires a fact that changes the reader's own decision or action within days (direct security, privacy, legal, or financial threat, or first-party news about products they use); general money, law, and politics news without that tie is explicitly excluded. Interesting requires durable insight; ordinary coverage, opinion takes, and trend roundups excluded. New scarcity rule: roughly 1-2 important and 4-6 interesting per day, more than 2 or 6 in a batch means re-judge the weakest flags as normal. Applies to the skill, the scaffold, and the fallback rubric in both editions.

### Fixed

- **rss-reader:** Unread or Starred can now be combined with a feed or folder. Switching views keeps the selected scope, and selecting a feed or folder keeps the current view. Feed and folder changes return the article list to the top.
- **cdp-manager:** version `1.0.0` (the pre-release `1.0.1` tag is retired, never shipped). `config.json` now writes inside the plugin directory instead of the shared `$HERMES_HOME/plugins/` folder, and the default Chrome profile path derives from `%LOCALAPPDATA%` instead of a hardcoded personal path. The public edition's repo link points at `public/cdp-manager`. Pack re-pinned to the fix commit (pack `1.17.0`); catalog entry updated with `platforms: [windows]` and corrected profile-path wording.

## [rss-reader 1.0.8] - 2026-09-22

YouTube videos play in the reader, playlists run oldest first, Reddit chips subscribe, and Settings Advanced covers User-Agent plus YouTube cookies.

### Added

- **rss-reader:** version `1.0.8`. YouTube posts play in a 16:9 pane with chapter timestamps when the feed description lists them. Playlist feeds list oldest first. Settings Advanced adds a User-Agent preset and a YouTube cookie field used on YouTube HTTP fetches. Subscribe chips include YouTube and Substack rows, plus Google AI in Popular starters.

### Fixed

- **rss-reader:** Reddit community chips subscribe through the subreddit Atom feed. VentureBeat AI 429'd on the default User-Agent and is replaced by Google AI.

### Changed

- **rss-reader:** the public listing edition keeps the 1.0.8 YouTube player, playlists, User-Agent, cookies, Reddit Atom, and starter chips. Self-improvement, paywall mirrors, webview, layout-store reads, and the private gateway preview import stay personal-only.

## [rss-reader 1.0.7] - 2026-09-20

Subscribe accepts YouTube and Substack pages, a folder view includes nested feeds, and each feed has its own capture and ticker settings.

### Added

- **rss-reader:** version `1.0.7`. Paste a YouTube channel, `@handle`, `/user/`, playlist, or a Substack page into Subscribe. Opening a folder shows that folder and its children. Edit mode adds a pencil per feed: name, full-article download, paywall checks, ticker visibility, and an optional refresh override.

### Changed

- **rss-reader:** Settings Main **Default View** sits in Reading, above Mark Articles Read When Opened. The Subscribe hint is two lines, with Folder and New folder lined up to the URL field.

## [rss-reader 1.0.6] - 2026-09-20

Folder order is yours to set, and old posts leave when the feed no longer lists them.

### Added

- **rss-reader:** version `1.0.6`. Edit mode adds a gripper on named folders so you can drag them into a new order. That order is saved and used after reload. Ungrouped stays first. Feeds inside a folder keep their own order. Settings Main **Keep Articles** (7 to 365 days, default 14) drops posts older than that limit when the live feed no longer lists them, and deletes their full-article cache. Starred posts stay. Slow feeds that still list an old item keep it.

## [1.14.0] - 2026-09-18

### Added

- **better-session-appearance:** version `1.2.0`. Auto Rules on the Icon header save the current color, bold, and idle icon against title keywords (comma or space, all words must match, case-insensitive). Each rule row has Edit and Remove. Future sessions whose titles contain those words pick up that look. The Appearance submenu grows so the icon grid is no longer trapped behind the old 320px cap.

## [1.13.1] - 2026-09-17

### Added

- **rss-reader:** version `1.0.3`. Optional Register Hermes Tools adds one `rss` tool so Hermes can read and find posts, tag or untag them, manage keyword and tag filters, and change subscriptions. `/rss find` returns matching titles and post text. `/rss tag`, `/rss untag`, `/rss mute tag`, and `/rss unmute` cover the same library from chat.

## [1.12.1] - 2026-09-17

### Fixed

- **better-capabilities:** version `1.0.1`. Package (zip) uses the skill title currently shown in the detail pane, so switching from one learned skill to another no longer downloads the first skill the row was painted with.

## [1.12.0] - 2026-09-17

### Added

- **better-capabilities:** version `1.0.0`. Adds a delete control next to the Capabilities folder icon, a Package (zip) button between Edit and Archive on a learned skill, Recycle Bin delete, and a zip of the skill folder including references.

## [1.11.0] - 2026-09-17

### Added

- **compact-reasoning-label:** version `1.0.0`. The composer's model pill shows only the model name; the duplicated thinking-level word is stripped so it lives only in the reasoning pill beside it. Idempotent re-strip survives every React repaint without an observer loop.

## [1.10.3] - 2026-09-16

### Added

- **rss-reader:** version `1.0.0` → `1.0.1`. Adds `/rss refresh`, refresh-period settings, feed-wide mute commands, session-based grading refinement using the `rss-reader-plugin` skill, website/feed discovery for subscriptions, scoped unread triage, grouped digest sessions, and read-only feed health diagnostics. The legacy `rss-reader-grading` and `rss-importance-grading` skill slugs map to the new name.

## [1.10.2] - 2026-09-13

### Changed

- **memory-review:** 1.2.1. Approve skips dead replace/remove ops. An over-budget error shows Consolidate above Reject/Approve. Store meters refresh from `/state` without waiting on slash.

## [1.10.1] - 2026-09-13

### Changed

- **memory-review:** 1.1.0. Memory and User meters share one row. User sits on the right. A small bar follows the percent.

## [1.10.0] - 2026-09-13

### Changed

- **memory-review:** renamed from `memory-review-command`. Opens a review dialog instead of sending `/memory pending`. Rows show store and action glyphs, plus dim fill bars for each store.

## [1.9.0] - 2026-09-12

### Added

- **memory-review-command:** a native shell-menu command that sends `/memory pending` through the composer when a staged memory write is waiting or a store is full. The row stays grayed out when memory is clean and never approves or discards entries.

## [1.8.0] - 2026-09-08

### Added

- **iteration-budget-meter:** status-bar chip that shows the focused session's per-turn iteration usage (N/60) while a turn runs. Amber near the cap, red at cap. The popover shows average tool calls per request, the ratio of requests hitting the max, and a suggested new ceiling when the data supports raising it. Counts only the current turn, so the number can never exceed the cap.

## [1.7.0] - 2026-09-01

### Fixed

- **scroll-on-switch:** restore explicit activation tracking after removing transcript observers. Hidden-to-visible and newly mounted session switches now scroll correctly without reacting to new messages.

## [1.5.0] - 2026-09-01

### Fixed

- **scroll-on-switch:** only scrolls when switching to a session. New messages and AI streaming no longer interrupt manual scrolling.

## [1.4.0] - 2026-09-01

### Added

- **scroll-on-switch:** keeps active session transcripts at the newest message after switching sessions or receiving a new message. It handles newly mounted sessions and late-rendered message nodes without preventing manual scrolling after the update settles. Desktop-only.

## [1.3.0] - 2026-09-01

### Added

- **opaque-composer:** keeps the desktop composer solid while scrolling so conversation text stays readable. Desktop-only and upgrade-safe through a small reversible stylesheet plugin.

## [1.2.3] - 2026-09-01

### Fixed

- **tool-break:** version `1.2.1` → `1.2.2`. The backend pid watcher snapshotted the whole system process table every 200ms for the entire life of every tool call (~12ms of locked work per snapshot on Windows), which stalled tool start and made typing lag. The watcher now runs only for the first 2.5 seconds of a call, then stops; late spawns are still caught at `/break` time. Combined with the 1.2.1 desktop backoff, an idle session now does near-zero plugin work.

## [1.2.2] - 2026-09-01

### Changed

- **tool-break:** version `1.2.0` → `1.2.1`. Desktop bar no longer polls `/break-status` every second and re-renders 4x/second while idle: the poll backs off to 5s when nothing is in flight, and the elapsed-time clock runs only while tools are visible. Behavior while a tool is in flight is unchanged.

## [1.2.1] - 2026-09-01

### Changed

- **provider-status:** version `0.1.0` → `1.0.0`.

## [1.2.0] - 2026-09-01

`hermes-break` is now `tool-break`. The pack requires Hermes Agent 0.21.0.

### Changed

- **tool-break:** renamed from `hermes-break`. Commands stay `/break`, `/break {message}`, and `/again`.
- Plugin descriptions match the community-index copy.
- Manifests declare `manifest_version: 2`, `api_version: 1`, homepage, and tags.
- Install docs require Hermes Agent `>= 0.21.0` (shareable plugin packs).

### Upgrade notes

- Reinstall from the pack, or disable `hermes-break` and enable `tool-break`.
- Desktop strip settings live under `localStorage` keys `tool-break.grades` and `tool-break.hide` (old `hermes-break.*` keys are not read).

## [1.1.0] - 2026-08-30

Adds `drag-to-pin-session` to the pack.

### Added

- **drag-to-pin-session:** the Pinned section of the Sessions sidebar becomes a drag container. Drag a session row in to pin it, drag a pinned row out into Sessions to unpin it. Desktop-only, hot-reloads, no rebuild.

### Changed

- Pack description and README now cover four plugins.
- `hermes-awesome-plugins-sync` mirrors `drag-to-pin-session`, and relocates a root `plugin.js` to `desktop/plugin.js` for any plugin rather than only `better-colors`.

## [1.0.0] - 2026-08-30

First pack. Three Hermes Agent plugins, pinned to exact SHAs.

### Added

- **provider-status:** quota chips across providers, Grok/Codex OAuth, key-pool rotation, and per-key reset-day rotation.
- **hermes-break:** `/break` and `/again` kill a hung spawn without aborting the turn. `/again` reissues that call once.
- **better-colors:** session list appearance. Color and bold titles, extra Appearance colors, idle-bullet glyphs.

### Upgrade notes

- Hermes Agent `>= 0.3`.
- Install with `hermes plugins pack install` of the raw `hermes-pack.yaml` URL. There is no GitHub Release for this pack.
