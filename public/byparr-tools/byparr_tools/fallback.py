"""Auto-fallback middleware.

Wraps tool execution so that a walled ``web_extract`` result can be retried
through the configured solver. Fail-open by design: any error returns the
original result, so this never breaks the tools it observes. The middleware is
opt-in per tool name through Settings and never touches our own solver_* tools,
so it cannot recurse into itself.
"""
from __future__ import annotations

import json
from typing import Any, Dict

from .config import Settings
from . import tools as solver_tools

_settings = Settings()
WALL_MARKERS = ("just a moment", "sec-if-cpt", "checking security", "access denied")
# web_extract takes ``urls``; browser_exec takes ``code``, so a URL never reaches
# this middleware from that tool and it is not a default target.
DEFAULT_TARGETS = ("web_extract",)
URL_ARGUMENTS = ("url", "target_url", "href")
MAX_RESULT_CHARS = 20000


def configure(ctx: Any = None) -> None:
    global _settings
    _settings = Settings(ctx)


def _targets() -> set:
    value = _settings.get("fallback_tool_names")
    if isinstance(value, list) and value:
        return {str(v) for v in value}
    return set(DEFAULT_TARGETS)


def _as_text(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("text", "content", "result", "markdown", "output"):
            value = result.get(key)
            if isinstance(value, str):
                return value
    return ""


def _walled(text: str) -> bool:
    low = text.lower()[:MAX_RESULT_CHARS]
    return any(marker in low for marker in WALL_MARKERS)


def _first_http_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    return ""


def _url(args: Dict[str, Any]) -> str:
    """The first fetchable URL in a tool's arguments.

    ``web_extract`` names its input ``urls`` (a list), and a single-URL call is
    the common case, so ``urls[0]`` is read alongside the singular names. Without
    that read the fallback never fired for the tool it advertises.
    """
    for key in URL_ARGUMENTS:
        found = _first_http_url(args.get(key))
        if found:
            return found
    urls = args.get("urls")
    if isinstance(urls, list):
        for value in urls:
            found = _first_http_url(value)
            if found:
                return found
    return ""


def on_tool_execution(**kwargs: Any) -> Any:
    """Wrap a tool call. Always call next_call exactly once; fail open."""
    next_call = kwargs.get("next_call")
    if not callable(next_call):
        return None
    tool_name = str(kwargs.get("tool_name") or "")
    args = kwargs.get("args") or {}
    result = next_call(args)

    try:
        if tool_name not in _targets():
            return result
        if not _settings.bool_key("auto_fallback"):
            return result
        text = _as_text(result)
        if not text or not _walled(text):
            return result
        url = _url(args)
        if not url:
            return result
        solved = json.loads(solver_tools.solver_get({
            "url": url, "returnHtml": True,
            "maxChars": _settings.int_key("max_text_chars"),
        }))
        if not solved.get("ok") or not solved.get("solved"):
            return result
        solved_text = solved.get("html", "")
        if len(solved_text) <= len(text):
            return result
        return solved_text
    except Exception:  # noqa: BLE001 - middleware must never break the tool
        return result
