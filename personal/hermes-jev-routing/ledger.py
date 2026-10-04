"""Best-effort spend ledger. A write failure must not change a route."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def round4(value: float) -> float:
    return round(value * 10000) / 10000


def format_usd(value: float) -> str:
    if value >= 1:
        return f"${value:.2f}"
    if value >= 0.01:
        return f"${value:.3f}"
    return f"${value:.4f}"


def day_key(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")


def month_key(now: Optional[datetime] = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


def empty_ledger() -> dict:
    return {
        "version": 1,
        "days": {},
        "months": {},
        "jev": {"requests": 0, "inputTokens": 0, "outputTokens": 0},
        "updatedAt": datetime.now(timezone.utc).isoformat(),
    }


def load_ledger(path: str | Path) -> dict:
    try:
        parsed = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return empty_ledger()
    if not isinstance(parsed, dict):
        return empty_ledger()
    ledger = empty_ledger()
    ledger.update(parsed)
    ledger["days"] = parsed.get("days") if isinstance(parsed.get("days"), dict) else {}
    ledger["months"] = parsed.get("months") if isinstance(parsed.get("months"), dict) else {}
    jev = parsed.get("jev") if isinstance(parsed.get("jev"), dict) else {}
    ledger["jev"] = {
        "requests": int(jev.get("requests") or 0),
        "inputTokens": int(jev.get("inputTokens") or 0),
        "outputTokens": int(jev.get("outputTokens") or 0),
    }
    return ledger


def save_ledger(path: str | Path, ledger: dict) -> None:
    try:
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        ledger["updatedAt"] = datetime.now(timezone.utc).isoformat()
        file.write_text(json.dumps(ledger, indent=2) + "\n", encoding="utf-8")
    except OSError:
        return


def record_cost(ledger: dict, model_key: str, usd: float, now: Optional[datetime] = None) -> None:
    if not isinstance(usd, (int, float)) or usd <= 0:
        return
    day = day_key(now)
    month = month_key(now)
    ledger["days"].setdefault(day, {"total": 0, "byModel": {}})
    ledger["months"].setdefault(month, {"total": 0, "byModel": {}})
    for bucket in (ledger["days"][day], ledger["months"][month]):
        bucket["total"] = round4(float(bucket.get("total") or 0) + usd)
        by_model = bucket.setdefault("byModel", {})
        by_model[model_key] = round4(float(by_model.get(model_key) or 0) + usd)


def record_jev(ledger: dict, input_tokens: int = 0, output_tokens: int = 0) -> None:
    jev = ledger.setdefault("jev", {"requests": 0, "inputTokens": 0, "outputTokens": 0})
    jev["requests"] = int(jev.get("requests") or 0) + 1
    jev["inputTokens"] = int(jev.get("inputTokens") or 0) + max(int(input_tokens), 0)
    jev["outputTokens"] = int(jev.get("outputTokens") or 0) + max(int(output_tokens), 0)


@dataclass(frozen=True)
class SpendSnapshot:
    today: float
    month: float
    pressure: float
    daily_cap: Optional[float] = None
    monthly_cap: Optional[float] = None


def spend_snapshot(ledger: dict, budget, now: Optional[datetime] = None) -> SpendSnapshot:
    today = float((ledger.get("days") or {}).get(day_key(now), {}).get("total") or 0)
    month = float((ledger.get("months") or {}).get(month_key(now), {}).get("total") or 0)
    ratios = []
    daily = getattr(budget, "daily_usd", None)
    monthly = getattr(budget, "monthly_usd", None)
    if daily and daily > 0:
        ratios.append(today / daily)
    if monthly and monthly > 0:
        ratios.append(month / monthly)
    return SpendSnapshot(
        today=today,
        month=month,
        pressure=max(ratios) if ratios else 0.0,
        daily_cap=daily,
        monthly_cap=monthly,
    )


def usage_cost(usage) -> float:
    """Prefer a reported total. Otherwise ask Hermes to price the tokens. Never raise."""
    if isinstance(usage, dict):
        cost = usage.get("cost")
        if isinstance(cost, dict):
            total = cost.get("total")
            if isinstance(total, (int, float)) and total > 0:
                return float(total)
        reported = usage.get("cost_usd")
        if isinstance(reported, (int, float)) and reported > 0:
            return float(reported)
    try:
        from agent.usage_pricing import estimate_usage_cost, normalize_usage
    except Exception:
        return 0.0
    try:
        canonical = normalize_usage(usage)
        result = estimate_usage_cost("", canonical, api_key="")
        amount = getattr(result, "amount_usd", None)
        return float(amount) if amount is not None and float(amount) > 0 else 0.0
    except Exception:
        return 0.0


def state_path(config_path: str) -> Path:
    source = Path(config_path)
    return source.with_name(source.stem + "-state.json")
