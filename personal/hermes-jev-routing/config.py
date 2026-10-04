"""Load a hermes-jev-routing JSON file.

CamelCase keys are accepted. A tier the file leaves empty stays empty. The
loader does not invent a default model list.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

try:
    from .decide import (
        AvailableModel,
        Budget,
        Cache,
        FreePool,
        RouteTarget,
        RouterConfig,
    )
except ImportError:
    from decide import (
        AvailableModel,
        Budget,
        Cache,
        FreePool,
        RouteTarget,
        RouterConfig,
    )

TASK_KINDS = {
    "plan": "Deciding what to build, sequencing work, or designing an approach before editing",
    "implement": "Writing or changing code, scripts, or configuration to produce a concrete result",
    "write": "Producing prose, documentation, comments, or other non-code content from scratch",
    "debug": "Diagnosing a failure, error, or unexpected behavior and finding its root cause",
    "refactor": "Restructuring existing code without changing intended behavior",
    "review": "Auditing code, a diff, a document, or a plan for problems and risks",
    "research": "Searching, reading, and synthesizing external information or unfamiliar APIs",
    "explain": "Answering a question or explaining how something works",
    "operate": "Running commands, tooling, git, deploys, or environment setup",
    "chat": "Small talk, acknowledgements, or a request with no real work attached",
}


@dataclass
class JevSettings:
    endpoint: str = "https://api.typesafe.ai/v1/systemone"
    endpoint_env: str = "TYPESAFE_API_URL"
    api_key_env: str = "TYPESAFE_API_KEY"
    jev_model: str = "jev-latest"
    timeout_ms: int = 3500
    history_turns: int = 4
    task_kinds: dict[str, str] = field(default_factory=lambda: dict(TASK_KINDS))


def _optional_float(value):
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _floors(raw: Any) -> dict[str, float]:
    if not isinstance(raw, Mapping):
        return {}
    floors: dict[str, float] = {}
    for key, value in raw.items():
        try:
            floors[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return floors


def _target(raw: Mapping[str, Any]) -> RouteTarget:
    return RouteTarget(
        provider=str(raw.get("provider") or ""),
        model=str(raw.get("model") or ""),
        thinking_level=raw.get("thinkingLevel") or raw.get("thinking_level"),
        min_tier=raw.get("minTier") or raw.get("min_tier"),
        priority=int(raw.get("priority") or 0),
        min_quota=_floors(raw.get("minQuota") or raw.get("min_quota")) or None,
    )


def _chain(raw: Any) -> tuple[RouteTarget, ...]:
    if not isinstance(raw, list):
        return ()
    return tuple(_target(item) for item in raw if isinstance(item, Mapping) and item.get("model"))


def fill_from_generated(data: dict, path: str | Path) -> dict:
    """A missing tier or kind may come from the generated file. A named hand chain wins."""
    source = Path(path).with_name(Path(path).stem + ".generated.json")
    if not source.is_file():
        return data
    try:
        generated = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return data
    if not isinstance(generated, dict):
        return data
    routes = dict(data.get("routes") or {})
    for tier, chain in (generated.get("routes") or {}).items():
        if tier == "xpremium" or tier in routes:
            continue
        routes[tier] = chain
    kinds = dict(data.get("kindModels") or data.get("kind_models") or {})
    for kind, chain in (generated.get("kindModels") or {}).items():
        if kind not in kinds:
            kinds[kind] = chain
    merged = dict(data)
    merged["routes"] = routes
    merged["kindModels"] = kinds
    return merged


def load_router_config(path: str | Path) -> tuple[RouterConfig, JevSettings]:
    hand = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(hand, dict):
        raise ValueError("router config must be a JSON object")
    data = fill_from_generated(hand, path)
    routes = data.get("routes") or {}
    kinds = data.get("kindModels") or data.get("kind_models") or {}
    floors = data.get("kindMinimumTier") or data.get("kind_minimum_tier") or {}
    free = data.get("free") or {}
    cache = data.get("cache") or {}
    budget = data.get("budget") or {}
    ranking = data.get("ranking") or {}
    config = RouterConfig(
        routes={tier: _chain(routes.get(tier)) for tier in ("quick", "standard", "high", "premium", "xpremium")},
        kind_models={str(kind): _chain(chain) for kind, chain in kinds.items() if isinstance(chain, list)},
        kind_minimum_tier={str(kind): str(tier) for kind, tier in floors.items()},
        confidence_threshold=float(data.get("confidenceThreshold", data.get("confidence_threshold", 0.34))),
        min_prompt_chars=int(data.get("minPromptChars", data.get("min_prompt_chars", 12))),
        budget=Budget(
            soft_ratio=float(budget.get("softRatio", budget.get("soft_ratio", 0.7))),
            hard_ratio=float(budget.get("hardRatio", budget.get("hard_ratio", 0.9))),
            daily_usd=_optional_float(budget.get("dailyUsd", budget.get("daily_usd"))),
            monthly_usd=_optional_float(budget.get("monthlyUsd", budget.get("monthly_usd"))),
        ),
        cache=Cache(
            aware=bool(cache.get("aware", True)),
            deadband=float(cache.get("deadband", 0.25)),
            max_penalty_usd=float(cache.get("maxPenaltyUsd", cache.get("max_penalty_usd", 0.05))),
            bypass_tier_delta=int(cache.get("bypassTierDelta", cache.get("bypass_tier_delta", 2))),
        ),
        free=FreePool(
            enabled=bool(free.get("enabled", False)),
            policy=str(free.get("policy") or "fallback-only"),
            pool=_chain(free.get("pool")),
        ),
        confirm_tiers=tuple(
            str(tier) for tier in ((data.get("confirm") or {}).get("tiers") or []) if tier
        ),
        confirm_on_timeout=str((data.get("confirm") or {}).get("onTimeout") or (data.get("confirm") or {}).get("on_timeout") or "reject"),
        quota_floors={
            str(provider): _floors((block or {}).get("minQuota") or (block or {}).get("min_quota"))
            for provider, block in (data.get("quota") or {}).items()
            if isinstance(block, Mapping)
        },
        quota_on_unknown={
            str(provider): str((block or {}).get("onUnknown") or (block or {}).get("on_unknown") or "use")
            for provider, block in (data.get("quota") or {}).items()
            if isinstance(block, Mapping)
        },
        quota_enabled={
            str(provider): bool((block or {}).get("enabled", True))
            for provider, block in (data.get("quota") or {}).items()
            if isinstance(block, Mapping)
        },
        quota_ttl_sec={
            str(provider): int((block or {}).get("cacheTtlSec") or (block or {}).get("cache_ttl_sec") or 120)
            for provider, block in (data.get("quota") or {}).items()
            if isinstance(block, Mapping)
        },
        ranking_cutoffs={
            str(name): float(value)
            for name, value in (ranking.get("cutoffs") or {}).items()
            if isinstance(value, (int, float))
        },
        ranking_spread=bool(ranking.get("spreadProviders", ranking.get("spread_providers", True))),
        ranking_scores_file=str(ranking.get("scoresFile") or ranking.get("scores_file") or ""),
    )
    kinds_raw = data.get("taskKinds") or data.get("task_kinds") or {}
    task_kinds = dict(TASK_KINDS)
    task_kinds.update({str(key): str(value) for key, value in kinds_raw.items() if value})
    settings = JevSettings(
        endpoint=str(data.get("endpoint") or JevSettings.endpoint),
        endpoint_env=str(data.get("endpointEnv") or data.get("endpoint_env") or "TYPESAFE_API_URL"),
        api_key_env=str(data.get("apiKeyEnv") or data.get("api_key_env") or "TYPESAFE_API_KEY"),
        jev_model=str(data.get("jevModel") or data.get("jev_model") or "jev-latest"),
        timeout_ms=int(data.get("timeoutMs", data.get("timeout_ms", 3500))),
        history_turns=int(data.get("historyTurns", data.get("history_turns", 4))),
        task_kinds=task_kinds,
    )
    return config, settings


def models_from_config(config: RouterConfig) -> tuple[AvailableModel, ...]:
    """Treat every configured target as available.

    Hermes does not hand the plugin a priced catalogue. Unknown cost makes the
    cache-penalty estimate return 0, so the hold gate does not block on a guess.
    """
    seen: set[tuple[str, str]] = set()
    models: list[AvailableModel] = []
    chains = [config.free.pool, *config.routes.values(), *config.kind_models.values()]
    for chain in chains:
        for target in chain:
            key = (target.provider, target.model)
            if not target.model or key in seen:
                continue
            seen.add(key)
            models.append(AvailableModel(provider=target.provider, id=target.model))
    return tuple(models)
