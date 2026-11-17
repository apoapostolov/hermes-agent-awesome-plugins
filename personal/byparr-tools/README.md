# byparr-tools

First-class Hermes tools for the Bedroom challenge solver. The service is named
`flaresolverr` for compatibility, but the binary is **Byparr 3.1.1** at
`http://192.168.1.217:8191`. The `byparr` skill is the authoritative source for
identity and endpoints; this plugin just exposes three read-only tools.

## Tools

| Tool | What it does |
|------|--------------|
| `solver_get` | solved HTML for a walled public page, with wall detection and optional truncated HTML |
| `solver_cookies` | harvest challenge cookies as a CDP `Network.setCookies` payload, plus the exact UA to set |
| `solver_load` | batch public URLs to clean text via Byparr's Open WebUI `/load` endpoint |

Byparr is GET-only, has no inbound cookies input, and does not log in. For a
logged-in or interactive flow, use `solver_cookies` to bridge into a browser on
Bedroom (same egress IP) and set the reported User-Agent: `cf_clearance` is
bound to both.

## Install and enable

```bash
hermes plugins install C:/git-public/hermes-agent-awesome-plugins/personal/byparr-tools
hermes plugins enable byparr-tools
```

Tools land in the next session; the gateway defers tool registration rather than
hot-loading it. Set `FLARESOLVERR_URL` to override the default solver address.

## Tests

```bash
python -m pytest tests -q
```

Offline tests mock the HTTP call. No network, no credentials, no writes.
