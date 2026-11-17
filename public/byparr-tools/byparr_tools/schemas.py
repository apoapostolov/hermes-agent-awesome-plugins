"""Tool schemas for the portable solver tools."""

SOLVER_GET = {
    "name": "solver_get",
    "description": (
        "Fetch a Cloudflare/JS-walled public page through a FlareSolverr-compatible "
        "solver (Byparr or FlareSolverr) and return solved HTML. The solver address "
        "comes from plugin Settings or FLARESOLVERR_URL. GET-only, no inbound cookies. "
        "Use when web_extract/curl returned a challenge or a walled/short body. "
        "Returns status, byte count, wall markers and optionally HTML. For login or "
        "clicks, use solver_cookies to bridge into a browser instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "http(s) URL to fetch."},
            "maxTimeout": {"type": "integer", "description": "Solve timeout. Below 1000 = seconds, 1000+ = milliseconds."},
            "blockMedia": {"type": "boolean", "description": "Block images/media/fonts for speed."},
            "returnHtml": {"type": "boolean", "description": "Include HTML in the result."},
            "maxChars": {"type": "integer", "description": "HTML cap when returnHtml is true."},
            "proxyServer": {"type": "string", "description": "Optional protocol://host:port for one request."},
            "proxyUsername": {"type": "string"},
            "proxyPassword": {"type": "string"},
        },
        "required": ["url"],
    },
}

SOLVER_COOKIES = {
    "name": "solver_cookies",
    "description": (
        "Harvest challenge cookies such as cf_clearance through returnOnlyCookies. "
        "Returns a CDP Network.setCookies payload and the exact user_agent to set. "
        "Challenge cookies are commonly bound to User-Agent and IP: match the UA and "
        "use a browser sharing the solver's egress IP. Cookie values stay hidden "
        "unless showValues is true. An optional session stores the payload in a "
        "session-scoped in-memory jar for solver_bridge."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Landing page that presents the challenge."},
            "maxTimeout": {"type": "integer"},
            "showValues": {"type": "boolean", "description": "Include cookie values (sensitive)."},
            "session": {"type": "string", "description": "Optional jar key for a later solver_bridge call."},
            "proxyServer": {"type": "string"},
            "proxyUsername": {"type": "string"},
            "proxyPassword": {"type": "string"},
        },
        "required": ["url"],
    },
}

SOLVER_LOAD = {
    "name": "solver_load",
    "description": (
        "Batch-fetch public URLs through the solver's Open WebUI /load endpoint and "
        "return clean text with source metadata for RAG/document capture. Failing "
        "URLs yield empty text so a pipeline degrades gracefully. Text-only: use "
        "solver_get when HTML, status codes or cookies are needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch sequentially."},
            "maxChars": {"type": "integer", "description": "Characters per page in the result."},
        },
        "required": ["urls"],
    },
}

SOLVER_STATUS = {
    "name": "solver_status",
    "description": (
        "Check solver health at the configured address. Reports reachability, "
        "latency, version string, request queue counters and a redacted settings "
        "summary. Use before scheduled jobs or after a suspected outage."
    ),
    "parameters": {"type": "object", "properties": {}},
}

SOLVER_BRIDGE = {
    "name": "solver_bridge",
    "description": (
        "Inject a solver_cookies payload into a running browser through the CDP "
        "endpoint configured in Settings (BYPARR_CDP_URL). Accepts a jar session "
        "or an explicit cookies array, sets Network cookies and optionally the "
        "matching User-Agent. Use before driving a walled page in browser-use or "
        "computer-use. Cookie values are never printed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session": {"type": "string", "description": "Jar session saved by solver_cookies."},
            "cookies": {"type": "array", "items": {"type": "object"}, "description": "Explicit CDP cookie objects."},
            "user_agent": {"type": "string", "description": "User-Agent to set on the browser target."},
        },
    },
}

SOLVER_EXTRACT = {
    "name": "solver_extract",
    "description": (
        "Extract structured data from solved HTML or a URL: JSON-LD blocks, meta "
        "tags, title, headings and term/value pairs. Domain-agnostic, so it does "
        "not encode site-specific selectors. Returns raw structured data for the "
        "calling skill to interpret."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "html": {"type": "string", "description": "Solved HTML to parse."},
            "url": {"type": "string", "description": "Optional URL to solve first when html is absent."},
            "maxPairs": {"type": "integer", "description": "Term/value pairs to keep."},
        },
    },
}

SOLVER_FETCH = {
    "name": "solver_fetch",
    "description": (
        "Fetch a public URL directly first, then fall back to the solver when the "
        "body is walled, short or the direct request fails. Reports which route "
        "was used. The fallback is controlled by the auto_fallback setting."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "maxTimeout": {"type": "integer"},
            "maxChars": {"type": "integer"},
        },
        "required": ["url"],
    },
}

JAR_LIST = {
    "name": "jar_list",
    "description": "List session-scoped cookie jar entries by name and count, never values.",
    "parameters": {"type": "object", "properties": {}},
}

JAR_CLEAR = {
    "name": "jar_clear",
    "description": "Remove one session's cookies from the in-memory jar.",
    "parameters": {
        "type": "object",
        "properties": {"session": {"type": "string"}},
        "required": ["session"],
    },
}

TOOLS = (
    ("solver_get", SOLVER_GET),
    ("solver_cookies", SOLVER_COOKIES),
    ("solver_load", SOLVER_LOAD),
    ("solver_status", SOLVER_STATUS),
    ("solver_bridge", SOLVER_BRIDGE),
    ("solver_extract", SOLVER_EXTRACT),
    ("solver_fetch", SOLVER_FETCH),
    ("jar_list", JAR_LIST),
    ("jar_clear", JAR_CLEAR),
)
