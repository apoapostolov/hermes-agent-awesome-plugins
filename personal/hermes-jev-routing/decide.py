"""Decide a capability tier from a typed judgment, then apply budget, availability, and cache hold."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional, Sequence

TIERS = ("quick", "standard", "high", "premium", "xpremium")
PREMIUM = TIERS.index("premium")


def js_round(value: float) -> int:
    """Match JS Math.round for the demand scale (half away from zero)."""
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def tier_index(tier: Optional[str]) -> int:
    name = tier or "standard"
    try:
        return TIERS.index(name)
    except ValueError:
        return 1


@dataclass(frozen=True)
class RouteTarget:
    provider: str
    model: str
    thinking_level: Optional[str] = None
    min_tier: Optional[str] = None
    priority: int = 0
    min_quota: Optional[Mapping[str, float]] = None


@dataclass(frozen=True)
class AvailableModel:
    provider: str
    id: str
    cost: Optional[Mapping[str, float]] = None


@dataclass(frozen=True)
class Analysis:
    kind: str
    complexity: float
    budget_intensity: float
    deep_reasoning: float
    kind_confidence: float = 1.0
    kind_probabilities: dict = field(default_factory=dict)
    complexity_confidence: float = 0.0
    capability_confidence: float = 0.0
    latency_ms: int = 0


@dataclass(frozen=True)
class Spend:
    pressure: float = 0.0
    today: float = 0.0


@dataclass(frozen=True)
class Budget:
    soft_ratio: float = 0.7
    hard_ratio: float = 0.9
    daily_usd: float | None = None
    monthly_usd: float | None = None


@dataclass(frozen=True)
class Cache:
    aware: bool = True
    deadband: float = 0.25
    max_penalty_usd: float = 0.05
    bypass_tier_delta: int = 2


@dataclass(frozen=True)
class FreePool:
    enabled: bool = False
    policy: str = "fallback-only"
    pool: Sequence[RouteTarget] = field(default_factory=tuple)


@dataclass
class RouterConfig:
    routes: Mapping[str, Sequence[RouteTarget]]
    enabled: bool = True
    stickiness: bool = True
    kind_models: Mapping[str, Sequence[RouteTarget]] = field(default_factory=dict)
    kind_minimum_tier: Mapping[str, str] = field(default_factory=dict)
    confidence_threshold: float = 0.34
    min_prompt_chars: int = 12
    budget: Budget = field(default_factory=Budget)
    cache: Cache = field(default_factory=Cache)
    free: FreePool = field(default_factory=FreePool)
    confirm_tiers: tuple[str, ...] = ()
    confirm_on_timeout: str = "reject"
    quota_floors: Mapping[str, Mapping[str, float]] = field(default_factory=dict)
    quota_on_unknown: Mapping[str, str] = field(default_factory=dict)
    quota_enabled: Mapping[str, bool] = field(default_factory=dict)
    quota_ttl_sec: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    desired_tier: str
    tier: str
    target: RouteTarget
    model: Optional[AvailableModel]
    tier_index: int
    demand_score: float
    budget_pressure: float
    downgraded: bool
    low_confidence_fallback: bool
    kind_specialised: bool
    held: bool
    reason: str
    notes: tuple[str, ...]


Eligibility = Callable[[RouteTarget, AvailableModel], bool]


def find_model(
    models: Sequence[AvailableModel], target: RouteTarget
) -> Optional[AvailableModel]:
    for model in models:
        if model.provider == target.provider and model.id == target.model:
            return model
    for model in models:
        if model.id == target.model:
            return model
    return None


def first_available(
    models: Sequence[AvailableModel],
    chain: Sequence[RouteTarget],
    eligibility: Optional[Eligibility] = None,
    notes: Optional[list[str]] = None,
) -> Optional[tuple[RouteTarget, AvailableModel]]:
    for target in chain:
        model = find_model(models, target)
        if model is None:
            continue
        if eligibility is not None and not eligibility(target, model):
            if notes is not None:
                note = f"{target.model} skipped"
                if note not in notes:
                    notes.append(note)
            continue
        return target, model
    return None


def kind_candidates(config: RouterConfig, kind: str, index: int) -> list[RouteTarget]:
    chain = list(config.kind_models.get(kind) or ())
    eligible = [target for target in chain if tier_index(target.min_tier) <= index]
    eligible.sort(
        key=lambda target: (
            -(target.priority or 0),
            -tier_index(target.min_tier),
        )
    )
    return eligible


def estimate_cache_penalty_usd(
    context_tokens: float,
    current: AvailableModel,
    target: AvailableModel,
) -> float:
    if not math.isfinite(context_tokens) or context_tokens <= 0:
        return 0.0
    if target.cost is None or target.cost.get("input") is None:
        return 0.0
    target_input = float(target.cost["input"])
    cache_write = float(target.cost.get("cache_write") or 0)
    cache_read = float((current.cost or {}).get("cache_read") or 0)
    cold = (target_input + cache_write) / 1_000_000
    warm = cache_read / 1_000_000
    return max(0.0, context_tokens * (cold - warm))


def _route(config: RouterConfig, tier: str) -> Sequence[RouteTarget]:
    return config.routes.get(tier) or ()


def decide(
    analysis: Analysis,
    config: RouterConfig,
    models: Sequence[AvailableModel],
    spend: Optional[Spend] = None,
    *,
    context_tokens: float = 0,
    current_index: Optional[int] = None,
    current_model: Optional[AvailableModel] = None,
    current_target: Optional[RouteTarget] = None,
    eligibility: Optional[Eligibility] = None,
) -> Optional[Decision]:
    """Compose Jev scores into a tier, then apply budget, availability, and cache hold."""
    notes: list[str] = []
    spend = spend or Spend()

    demand = 0.55 * analysis.complexity + 0.45 * analysis.budget_intensity
    if analysis.deep_reasoning >= 0.65:
        demand += 0.75
    elif analysis.deep_reasoning <= 0.2:
        demand -= 0.25
    demand = clamp(demand, 0, 3)
    demand_reaches_premium = js_round(demand) >= PREMIUM

    kind_floor = min(tier_index(config.kind_minimum_tier.get(analysis.kind, "quick")), PREMIUM)
    if demand < kind_floor:
        notes.append(f"{analysis.kind} floors at {TIERS[kind_floor]}")
        demand = kind_floor

    desired_index = clamp(js_round(demand), 0, PREMIUM)
    index = int(desired_index)
    low_confidence = False

    if (
        config.confidence_threshold > 0
        and analysis.kind_confidence > 0
        and analysis.kind_confidence < config.confidence_threshold
        and index > 1
    ):
        notes.append(f"low kind confidence {analysis.kind_confidence:.2f} -> standard")
        index = 1
        low_confidence = True

    xpremium_eligible = (
        len(_route(config, "xpremium")) > 0
        and demand_reaches_premium
        and analysis.kind_confidence > 0
        and analysis.kind_confidence >= config.confidence_threshold
    )
    if xpremium_eligible:
        desired_index = PREMIUM + 1
        index = int(desired_index)
    tier_count = len(TIERS) if xpremium_eligible else PREMIUM + 1

    downgraded = False
    if spend.pressure >= config.budget.hard_ratio and spend.pressure > 0:
        forced = 1 if demand >= 2.5 else 0
        if forced < index:
            notes.append(f"budget {spend.pressure * 100:.0f}% of cap -> capped at {TIERS[forced]}")
            index = forced
            downgraded = True
    elif spend.pressure >= config.budget.soft_ratio and spend.pressure > 0:
        if index > 0:
            notes.append(f"budget {spend.pressure * 100:.0f}% of cap -> one tier down")
            index -= 1
            downgraded = True

    free_pool = []
    if config.free.enabled:
        free_pool = [
            target
            for target in config.free.pool
            if any(model.provider == target.provider and model.id == target.model for model in models)
        ]

    kind_chain = kind_candidates(config, analysis.kind, index)
    ordered: list[RouteTarget] = []
    if config.free.policy == "prefer":
        ordered.extend(free_pool)
    ordered.extend(kind_chain)
    ordered.extend(_route(config, TIERS[index]))
    for offset in range(1, tier_count):
        if index - offset >= 0:
            ordered.extend(_route(config, TIERS[index - offset]))
        if index + offset < tier_count:
            ordered.extend(_route(config, TIERS[index + offset]))
    if config.free.policy == "fallback-only":
        ordered.extend(free_pool)

    available = first_available(models, ordered, eligibility, notes)
    if available is None:
        return None
    target, model = available

    if current_model is not None and current_target is None:
        current_target = target_for_model(config, current_model)
    current_eligible = (
        current_model is None
        or current_target is None
        or eligibility is None
        or eligibility(current_target, current_model)
    )

    used_kind = any(
        item.provider == target.provider and item.model == target.model for item in kind_chain
    )
    if any(item.provider == target.provider and item.model == target.model for item in free_pool):
        notes.append(f"free pool -> {model.id}")

    serving = []
    if not used_kind:
        for i in range(tier_count):
            if any(
                item.provider == target.provider and item.model == target.model
                for item in _route(config, TIERS[i])
            ):
                serving.append(i)
    serving.sort(key=lambda i: (abs(i - index), i))
    effective_index = serving[0] if serving else index
    if effective_index != index:
        notes.append(f"{TIERS[index]} chain unavailable -> {TIERS[effective_index]}")
        downgraded = effective_index < index or downgraded
        index = effective_index

    if (
        config.cache.aware
        and current_eligible
        and current_index is not None
        and current_model is not None
        and (current_index <= PREMIUM or index > PREMIUM)
        and (model.provider != current_model.provider or model.id != current_model.id)
    ):
        delta = index - current_index
        penalty = estimate_cache_penalty_usd(context_tokens, current_model, model)
        band_demand = desired_index if xpremium_eligible else demand
        outside = (
            band_demand < current_index - 0.5 - config.cache.deadband
            or band_demand > current_index + 0.5 + config.cache.deadband
        )
        big_upgrade = delta >= config.cache.bypass_tier_delta
        affordable = penalty <= config.cache.max_penalty_usd
        hold_reason = None
        if delta == 0 and not affordable:
            hold_reason = f"same-tier swap to {model.id} would miss the cache"
        elif delta != 0 and not outside:
            hold_reason = f"demand {demand:.2f} sits inside the {TIERS[current_index]} band"
        elif delta != 0 and not big_upgrade and not affordable:
            hold_reason = "cache penalty keeps the warm cache"
        if hold_reason and current_target is not None:
            notes.append(hold_reason)
            return Decision(
                desired_tier=TIERS[int(desired_index)],
                tier=TIERS[current_index],
                target=current_target,
                model=current_model,
                tier_index=current_index,
                demand_score=demand,
                budget_pressure=spend.pressure,
                downgraded=False,
                low_confidence_fallback=low_confidence,
                kind_specialised=False,
                held=True,
                reason=(
                    f"{analysis.kind} -> {TIERS[int(desired_index)]}, "
                    f"held on {TIERS[current_index]} to keep the cache"
                ),
                notes=tuple(notes),
            )

    used = "" if index == int(desired_index) else f" (used {TIERS[index]})"
    return Decision(
        desired_tier=TIERS[int(desired_index)],
        tier=TIERS[index],
        target=target,
        model=model,
        tier_index=index,
        demand_score=demand,
        budget_pressure=spend.pressure,
        downgraded=downgraded,
        low_confidence_fallback=low_confidence,
        kind_specialised=used_kind,
        held=False,
        reason=f"{analysis.kind} -> {TIERS[int(desired_index)]}{used}",
        notes=tuple(notes),
    )


def target_for_model(config: RouterConfig, model: AvailableModel) -> RouteTarget:
    def match(chain: Sequence[RouteTarget]) -> Optional[RouteTarget]:
        for target in chain:
            if target.provider == model.provider and target.model == model.id:
                return target
        return None

    if config.free.enabled:
        hit = match(config.free.pool)
        if hit:
            return hit
    for tier in TIERS:
        hit = match(_route(config, tier))
        if hit:
            return hit
    for chain in config.kind_models.values():
        hit = match(chain)
        if hit:
            return hit
    return RouteTarget(provider=model.provider, model=model.id)


def same_provider_rewrite(
    request: Mapping[str, object],
    decision: Optional[Decision],
    bound_provider: str,
    mode: str,
) -> Optional[dict]:
    """Return a rewritten request only when Hermes can actually send it.

    llm_request can change the model id on the client already bound to this
    turn. It cannot open a different provider. A cross-provider pick is a
    decision, not a switch.
    """
    if mode != "auto" or decision is None or decision.held or decision.model is None:
        return None
    if decision.target.provider != bound_provider:
        return None
    updated = dict(request)
    updated["model"] = decision.target.model
    return updated
