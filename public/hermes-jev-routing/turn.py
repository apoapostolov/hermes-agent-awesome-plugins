"""One routing pass: classify, decide, and name the action Hermes can take."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

try:
    from .config import models_from_config
    from .decide import Analysis, Decision, RouterConfig, decide
    from .jev import JevError
except ImportError:
    from config import models_from_config
    from decide import Analysis, Decision, RouterConfig, decide
    from jev import JevError

Classifier = Callable[[str, str], Analysis]


@dataclass(frozen=True)
class RouteResult:
    action: str
    decision: Optional[Decision] = None
    error: str = ""


def route_turn(
    prompt: str,
    config: RouterConfig,
    *,
    classify: Classifier,
    bound_provider: str,
    mode: str,
    history: str = "",
) -> RouteResult:
    text = (prompt or "").strip()
    if mode == "off" or len(text) < config.min_prompt_chars:
        return RouteResult("skip")
    try:
        analysis = classify(text, history)
    except (JevError, OSError, TimeoutError, ValueError) as exc:
        return RouteResult("fail-open", error=type(exc).__name__)
    decision = decide(analysis, config, models_from_config(config))
    if decision is None:
        return RouteResult("none")
    if mode != "auto" or decision.held:
        return RouteResult("shadow", decision)
    if decision.target.provider == bound_provider:
        return RouteResult("rewrite", decision)
    return RouteResult("switch", decision)
