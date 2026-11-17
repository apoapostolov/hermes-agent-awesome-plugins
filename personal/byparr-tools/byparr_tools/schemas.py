"""Tool schemas for the Byparr solver tools."""

_BASE = {
    "type": "object",
}

SOLVER_GET = {
    "name": "solver_get",
    "description": (
        "Fetch a Cloudflare/JS-walled public page through the Bedroom Byparr "
        "solver and return solved HTML. Byparr runs under the compatibility name "
        "'flaresolverr' at 192.168.1.217:8191 and is GET-only with no inbound "
        "cookies. Use when web_extract/curl returned a challenge or a walled/short "
        "body. Returns status, byte count, wall markers, and optionally HTML. "
        "For login or clicks, use solver_cookies to bridge into a browser instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "http(s) URL to fetch."},
            "maxTimeout": {
                "type": "integer", "default": 60,
                "description": "Solve timeout: below 1000 = seconds, 1000+ = milliseconds.",
            },
            "blockMedia": {
                "type": "boolean", "default": True,
                "description": "Block images/media/fonts for speed.",
            },
            "returnHtml": {
                "type": "boolean", "default": False,
                "description": "Include HTML in the result (truncated to maxChars).",
            },
            "maxChars": {"type": "integer", "default": 6000, "description": "HTML cap when returnHtml is true."},
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
        "Harvest challenge cookies (e.g. cf_clearance) from the Bedroom Byparr "
        "solver via returnOnlyCookies. Returns a CDP Network.setCookies payload "
        "and the exact user_agent to set on the target browser. cf_clearance is "
        "bound to User-Agent and IP: set the UA from the result and drive a browser "
        "on Bedroom (same egress IP). Never exposes cookie values unless "
        "showValues is true - keep them out of chat and commits."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Landing page that presents the challenge."},
            "maxTimeout": {"type": "integer", "default": 60},
            "showValues": {"type": "boolean", "default": False, "description": "Include cookie values (sensitive)."},
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
        "Batch-fetch public URLs through Byparr's Open WebUI /load endpoint and "
        "return clean text with source metadata for RAG/document capture. Failing "
        "URLs yield empty text so a pipeline degrades gracefully. Text-only: use "
        "solver_get when HTML, status codes or cookies are needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "urls": {"type": "array", "items": {"type": "string"}, "description": "URLs to fetch sequentially."},
            "maxChars": {"type": "integer", "default": 3000, "description": "Characters per page in the result."},
        },
        "required": ["urls"],
    },
}
