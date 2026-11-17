<div align="center">
  <img src="https://raw.githubusercontent.com/NousResearch/hermes-agent/main/docs/assets/hermes-mark.png" width="96" alt="Hermes" />
  <h1>byparr-tools</h1>
  <p><strong>First-class solver tools for Hermes, on any machine.</strong></p>
  <p>Hand a Cloudflare-walled page to a FlareSolverr-compatible solver, bridge the cleared cookies into your browser, and pull clean text for RAG, all from tools the agent can call directly.</p>
  <p><a href="../../LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT" /></a> <img src="https://img.shields.io/badge/version-0.2.0-green" alt="0.2.0" /></p>
</div>

## What You Can Do

- Fetch solved HTML from a JS- or Cloudflare-walled page through the solver configured in Settings.
- Harvest challenge cookies such as `cf_clearance`, then inject them into a running browser through CDP so browser-use or computer-use can continue an interactive flow.
- Batch-fetch public pages to clean text for document capture and RAG.
- Extract JSON-LD, meta tags, headings and term/value pairs from solved HTML without site-specific selectors.
- Check solver health, version and latency, with queue counters, before a scheduled job runs.
- Fall back from a direct fetch to the solver automatically when a page is walled or short.

The service you point this at must speak the FlareSolverr `/v1` API. Byparr and FlareSolverr both do. The plugin has no built-in address beyond the standard local default, so any host works after setup.

## Setup

You need a solver reachable over HTTP. On the machine that will run the plugin, start one of these.

**Byparr (recommended, actively maintained):**

```bash
docker run -d --name byparr -p 8191:8191 \
  -e BROWSER_LOCALE=en-US -e BROWSER_TIMEZONE=UTC \
  ghcr.io/thephaseless/byparr:latest
```

**FlareSolverr (compatible alternative):**

```bash
docker run -d --name flaresolverr -p 8191:8191 \
  -e TZ=UTC ghcr.io/flaresolverr/flaresolverr:latest
```

Check the solver with `curl http://127.0.0.1:8191/health`. A Byparr answer usually contains `Byparr is working!`; FlareSolverr reports `FlareSolverr is ready!` at `/`.

Then install and enable the plugin:

```bash
hermes plugins install https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/public/byparr-tools
hermes plugins enable byparr-tools
```

Open **Settings > Plugins > byparr-tools** and set **Solver URL** to your solver's address, for example `http://127.0.0.1:8191` for a local container or `http://<host>:8191` for one on another machine. `FLARESOLVERR_URL` overrides this setting for a single host. The three original tools plus six new ones appear in the next session; the gateway defers tool registration.

For cookie bridging, set **Browser CDP URL** to a Chrome/Chromium DevTools endpoint with a page target, normally `http://127.0.0.1:9222`. `BYPARR_CDP_URL` overrides it. Challenge cookies are commonly bound to User-Agent and IP, so drive a browser that shares the solver's egress IP and set the UA the tool returns.

## Settings

| Setting | Default | What it does |
| --- | --- | --- |
| Solver URL | `http://127.0.0.1:8191` | Base URL of the Byparr or FlareSolverr instance. |
| Default solve timeout | `60` | Seconds for a solve; values `1000+` are milliseconds. |
| Block media during solves | on | Skip images, media and fonts for faster solves. |
| Solver fallback in solver_fetch | on | Retry through the solver when a direct fetch is walled, short or fails. |
| Include HTML by default | off | Return HTML from `solver_get` without asking per call. |
| HTML result cap | `6000` | Maximum HTML characters returned by one call. |
| Text result cap | `3000` | Maximum characters per page for `solver_load` and `solver_fetch`. |
| Browser CDP URL | `http://127.0.0.1:9222` | DevTools endpoint used by `solver_bridge`. |
| Spacing between solves | `0.2` | Delay between solver requests; the solver already serialises solves. |
| Retries per request | `2` | Retries on transient solver errors with short backoff. |
| Cookie jar lifetime | `1800` | Seconds a stored cookie session stays usable. |
| Persist cookie jar to disk | off | Off keeps cookies in memory only; on writes them to the plugin data dir. |
| Cookie jar directory | empty | Optional directory for the persisted jar. |
| Proxy server | empty | Optional `protocol://host:port` for solves that need a different egress region. |
| Proxy username / password | unset | Optional proxy credentials stored in the host credential store. |

`FLARESOLVERR_URL`, `BYPARR_CDP_URL`, `BYPARR_PROXY_USERNAME` and `BYPARR_PROXY_PASSWORD` override their settings for one host. Proxy credentials use the host's secret scope, never `config.yaml`.

## What the agent writes

| Tool | Result |
| --- | --- |
| `solver_get` | Status, byte count, wall flag, `solved` flag and optional truncated HTML for one URL. |
| `solver_cookies` | Cookie names, an optional jar session, a CDP `Network.setCookies` payload and the exact User-Agent. Values stay hidden unless `showValues` is true. |
| `solver_load` | Clean text with source metadata for a list of URLs. |
| `solver_status` | Health body, version, latency, queue counters and a redacted settings summary. |
| `solver_bridge` | Injects a jar session or explicit cookies into the configured CDP target, including the UA. |
| `solver_extract` | JSON-LD, meta, title, headings and term/value pairs from HTML or a URL. |
| `solver_fetch` | Direct fetch text, with a solver fallback; reports which route produced the body. |
| `jar_list` / `jar_clear` | List sessions by name and count, or remove one. Cookie values never appear. |

The tools are transport and extraction primitives. Site-specific interpretation belongs in the calling skill, so a price parser stays in `price-hunting` rather than in this plugin.

## Requirements / Limits

- A reachable FlareSolverr-compatible HTTP solver. The plugin does not install or start one for you.
- The tool handlers open outbound HTTP connections to the configured solver and, for `solver_bridge`, to the configured CDP endpoint. No other network destination is contacted.
- Python standard library only. No pip dependencies.
- The solver is GET-only in this plugin. There is no inbound cookies field, no session parameter and no login flow. Use `solver_cookies` plus `solver_bridge` for an interactive page.
- `solver_load` needs the solver's Open WebUI `/load` endpoint. FlareSolverr builds without it will not answer; `solver_get` still works.
- Cookies are live session state. The jar is in memory unless disk persistence is explicitly enabled, and values are never written to chat output, logs or commits by the tools.
- A cloud-hosted solver is likely to stay blocked by Cloudflare. Run the solver on a machine whose traffic looks like real user traffic.

## License

[MIT](../../LICENSE)
