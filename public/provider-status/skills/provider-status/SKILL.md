---
name: provider-status
description: "Read live Hermes session telemetry — tokens/sec, context-window occupancy, and the current provider's remaining quota or credit balance — as a Discord bot presence or on demand via /pulse and the agent_pulse tool."
version: 1.6.2
license: MIT
metadata:
  hermes:
    tags: [discord, gateway, observability, metrics, presence, telemetry, quota]
    homepage: https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/provider-status
---

# Provider Status — live session presence

This plugin turns the numbers the desktop status bar already tracks into a
Discord bot presence for the **provider backing the current session**, plus
two on-demand read surfaces.

## What is published

| Lead emoji (default) | Metric | How it is computed |
|---|---|---|
| ↯ | Tokens/sec | `sum(output tokens) / sum(request durations)` over a 12-request rolling window |
| ◎ | Cache hit rate | `cache_read / prompt`, **off by default** |
| ▤ | Context usage | last request's `prompt_tokens` / the model's context length (the bar follows the emoji) |
| ◍ | Quota remaining | the current session provider's remaining window, from the desktop quota poll |
| ◈ | Credit balance | dollar leftover when that provider reports credits (DeepSeek, OpenRouter) |
| ⧉ | Running tool | the tool currently executing, **off by default** |
| ☤ | Model | the active route, last path segment only, **off by default** |
| ◷ | Latency | mean request duration, **off by default** |
| Σ | Lifetime tokens | session token total, **off by default** |

Every emoji here is a default; each line has its own setting. The headline three
(tokens/sec, context, quota) ship enabled. Discord caps a custom status at 128
characters, so extra segments compete with those.

The quota line is **this session's provider**, not every chip in the bar.
`xai-oauth` maps to Grok, `openai-codex` to Codex, `zai` to GLM. If the
desktop half has not polled that provider yet, the quota segment stays hidden
rather than showing a fake 0%.

Presence **status dot**:

* `online` while a turn or tool is live
* `idle` after `discord_idle_after_seconds` of quiet (default 180s)
* `dnd` once context occupancy reaches `discord_context_warn_percent` (default 80%) **or** remaining quota drops to `discord_quota_warn_remaining` (default 20%)

## Reading it on demand

* `/pulse` — a formatted report in any gateway session. `/pulse full` adds the raw config; `/pulse config` prints just the settings.
* `agent_pulse` tool — pass `detail: "full"` for raw counters.
* `hermes session-pulse` (or `json`) from a shell.

## Tuning

Settings live at `plugins.entries.provider-status.settings` in `config.yaml`,
or in Desktop under Settings → Plugins → Provider Quota Status. Every setting
below is a checkbox or field in that form.

### The three headline parts

| Setting | Default | What it turns off |
| --- | --- | --- |
| `discord_show_tokens_per_second` | on | `84 tok/s` |
| `discord_show_context` | on | `▰▰▱▱▱▱▱▱▱▱ · 6% ctx · 12.0K/200.0K` |
| `discord_show_quota` | on | `▰▰▱▱▱▱▱▱▱▱ · 61% Grok` |
| `discord_show_balance` | on | `DeepSeek $12.40` (credit providers only) |

Each bar also has its own switch so you can keep the number and drop the art:

| Setting | Default | What it does |
| --- | --- | --- |
| `discord_show_context_bar` | on | draw the context bar |
| `discord_show_quota_bar` | on | draw the quota bar |
| `discord_bar_width` | 10 | cells per bar (3-20); both bars share it |

Opt-in extras, off because they eat the status length: `discord_show_cache_hit`,
`discord_show_tool`, `discord_show_model`, `discord_show_latency`,
`discord_show_totals`.

### One emoji per line

Each metric line wears its own emoji, and its settings entry sits immediately
before that line's switches. The default layout reads:

```
↯ 84 tok/s · ▤ ▰▰▱▱▱▱▱▱▱▱ · 6% ctx · 12.0K/200.0K · ◍ ▰▰▱▱▱▱▱▱▱▱ · 61% Grok
```

| Line | Emoji setting | Default |
| --- | --- | --- |
| tokens/sec | `discord_emoji_tokens_per_second` | `↯` |
| cache hit | `discord_emoji_cache` | `◎` |
| context | `discord_emoji_context` | `▤` |
| quota | `discord_emoji_quota` | `◍` |
| credits | `discord_emoji_balance` | `◈` |
| running tool | `discord_emoji_tool` | `⧉` |
| model | `discord_emoji_model` | `☤` |
| latency | `discord_emoji_latency` | `◷` |
| lifetime tokens | `discord_emoji_totals` | `Σ` |

An explicitly empty value removes that line's emoji (no leftover space); only an
unset key falls back to the default. A per-line emoji matters most in `rotate`
mode, where one line shows at a time and the emoji is what identifies it.

Every line's shipped default lives in two places: the `plugin.yaml` schema, which
is what the settings form shows, and the `GLYPH_*` / `_DEFAULT_EMOJI` constants in
`presence_config.py`, which is what the presence renders. Move both, and the
assertions in `tests_presence.py` that pin them. Pick a glyph with text
presentation (no color emoji) so the family stays monochrome.

`discord_status_emoji` (default `▥`) covers the states that are not a metric
line: idle and thinking. Metric lines no longer wear it in front of their own
emoji.

```yaml
plugins:
  entries:
    provider-status:
      settings:
        discord_presence_enabled: true
        discord_presence_mode: compact
        discord_show_quota: true
        discord_show_balance: true
        discord_show_tokens_per_second: false
```

`compact` (the default) joins every enabled segment and trims from the right
to fit Discord's 128-character limit. `rotate` shows one segment per update,
so turning a part off removes it from the rotation too.

Disable the standalone `discord-presence` plugin while this one is publishing.
Two publishers on the same bot will fight over the status.

Settings are read once at `register()`, so a checkbox change needs a Save and
Reconnect before the presence picks it up.

## Rate limits and safety

Discord allows roughly five presence updates per 20 seconds per session. The
default 20s interval is inside that, and the publisher skips the REST call
when neither the text nor the status dot changed.

Every hook is observer-only. A presence failure is logged and swallowed; it
cannot take the gateway down. The on-disk quota cache holds numbers and
labels only — no keys, tokens, or emails.
