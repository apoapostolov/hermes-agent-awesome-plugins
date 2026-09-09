# Iteration Budget Meter

A status-bar meter that shows the focused session's per-turn iteration usage (N/60) live while a turn runs.

## What you get

- **Live chip during the turn**: current tool-call count against the session's iteration budget.
- **Hover tooltip**: quick per-request stats.
- **Click popover** with average tool calls per request, the max-hit ratio (how often the session pushed its ceiling), and a ceiling suggestion that reflects how hard the session actually pushes.
- **Per-turn accuracy**: the counter resets per turn; the cumulative-counter leak was fixed in v1.1.0 and the popover redesigned in v1.2.0.

## Install

Install the plugin pack (see the [repo README](../../README.md)) or copy this directory into your Hermes plugins folder and run:

```bash
hermes plugins enable iteration-budget-meter --no-allow-tool-override
```

## License

[MIT](../../LICENSE)
