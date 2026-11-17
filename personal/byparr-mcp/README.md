# byparr-mcp

MCP server for a FlareSolverr-compatible challenge solver (Byparr, FlareSolverr).
It exposes four read-only tools to any MCP client, so Codex, mcporter, Claude
Desktop or another Hermes can use the same solver the native `byparr-tools`
plugin uses. Dependency-free: only Python 3.10+ standard library is required.


<div align="center">
  <img src="docs/hero.png" width="100%" alt="byparr-mcp" />
</div>

## What's New in 0.2.0

- First public release. Four tools: `solver_get`, `solver_cookies`, `solver_load` and `solver_status`.
- The stdio server is dependency-free Python 3.10+ and reads its solver address from `BYPAAR_BASE_URL`, forwarded from the Settings page.
- No machine-specific address is baked in, and cookie values stay hidden unless `showValues` is true.

## Setup

1. Run a solver reachable over HTTP. For example:

   ```bash
   docker run -d --name byparr -p 8191:8191 ghcr.io/thephaseless/byparr:latest
   ```

2. Install and enable this package:

   ```bash
   hermes plugins install https://github.com/apoapostolov/hermes-agent-awesome-plugins/tree/main/personal/byparr-mcp
   hermes plugins enable byparr-mcp
   ```

3. Open **Settings > Plugins > byparr-mcp** and set **Solver URL**. It is
   forwarded to the server as `BYPAAR_BASE_URL`. When unset, the server uses
   `http://127.0.0.1:8191`. A plugin-declared MCP server binds at session start,
   so the tools appear in a new chat, not the installing one.

## Tools

- `solver_get(url, maxTimeout, blockMedia, returnHtml, maxChars)`: solved HTML
  and wall detection for one URL.
- `solver_cookies(url, maxTimeout, showValues)`: challenge cookies plus a CDP
  payload and the exact user agent. Values stay hidden unless asked.
- `solver_load(urls, maxChars)`: batch clean text for RAG. Needs the solver's
  `/load` endpoint.
- `solver_status()`: health, version and the configured solver URL.

## Direct use with mcporter

Without installing as a Hermes plugin:

```bash
BYPAAR_BASE_URL=http://127.0.0.1:8191 \
  mcporter call --stdio "python server.py" --tool solver_status
```

## Limits

- GET-only. No inbound cookies, sessions or login flows.
- No local address is baked in: the solver URL is always configurable.
- Cookie values are never printed unless `showValues` is true.

## License

MIT
