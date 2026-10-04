"""Score-file proposals. The hand table still wins wherever it names a chain."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

TIERS = ("quick", "standard", "high", "premium")


@dataclass(frozen=True)
class ScoreEntry:
    score: float
    kinds: Mapping[str, float]
    cost: Optional[Mapping[str, float]] = None


@dataclass(frozen=True)
class Scores:
    models: Mapping[str, ScoreEntry]


def load_scores(path: str | Path) -> tuple[Optional[Scores], str]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"can't read scores file {path}: {exc}"
    except json.JSONDecodeError as exc:
        return None, f"can't read scores file {path}: {exc}"
    models: dict[str, ScoreEntry] = {}
    blob = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(blob, dict):
        return Scores(models={}), ""
    for key, value in blob.items():
        if not isinstance(value, dict) or not isinstance(value.get("score"), (int, float)):
            continue
        kinds = {
            str(kind): float(score)
            for kind, score in (value.get("kinds") or {}).items()
            if isinstance(score, (int, float))
        }
        cost = value.get("cost") if isinstance(value.get("cost"), dict) else None
        if not (
            isinstance(cost, dict)
            and isinstance(cost.get("input"), (int, float))
            and isinstance(cost.get("output"), (int, float))
            and cost["input"] >= 0
            and cost["output"] >= 0
        ):
            cost = None
        models[str(key)] = ScoreEntry(score=float(value["score"]), kinds=kinds, cost=cost)
    return Scores(models=models), ""


def spread_by_provider(chain: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    rest = [dict(item) for item in chain]
    out: list[dict[str, str]] = []

    def arrangeable(left: list[dict[str, str]], prev: str) -> bool:
        counts: dict[str, int] = {}
        for item in left:
            counts[item["provider"]] = counts.get(item["provider"], 0) + 1
        return all(
            count <= (len(left) // 2 if provider == prev else (len(left) + 1) // 2)
            for provider, count in counts.items()
        )

    while rest:
        prev = out[-1]["provider"] if out else ""
        index = next(
            (
                i
                for i, item in enumerate(rest)
                if item["provider"] != prev and arrangeable(rest[:i] + rest[i + 1 :], item["provider"])
            ),
            -1,
        )
        if index < 0:
            index = next((i for i, item in enumerate(rest) if item["provider"] != prev), 0)
        out.append(rest.pop(index))
    return out


def _tier_for(score: float, cutoffs: Mapping[str, float]) -> str:
    if score >= float(cutoffs.get("premium", 0.85)):
        return "premium"
    if score >= float(cutoffs.get("high", 0.7)):
        return "high"
    if score >= float(cutoffs.get("standard", 0.5)):
        return "standard"
    return "quick"


def _by_value(items: list[dict], score) -> list[dict]:
    def value(item: dict):
        price = item.get("price")
        if price is None:
            return None
        if price <= 0:
            return float("inf")
        return score(item) / price

    return sorted(
        items,
        key=lambda item: (
            value(item) is None,
            -(value(item) or 0),
            -score(item),
            item["key"],
        ),
    )


def suggest_routes(
    *,
    task_kinds: Sequence[str],
    models: Sequence[tuple[str, str]],
    scores: Scores,
    cutoffs: Optional[Mapping[str, float]] = None,
    spread: bool = True,
) -> dict:
    cutoffs = cutoffs or {"standard": 0.5, "high": 0.7, "premium": 0.85}
    known = set(models)
    candidates = []
    unmatched = []
    for key, entry in scores.models.items():
        provider, _, model = key.partition("/")
        if not model or (provider, model) not in known:
            unmatched.append(key)
            continue
        cost = entry.cost
        price = None if cost is None else float(cost["input"]) + float(cost["output"])
        candidates.append({"key": key, "provider": provider, "model": model, "entry": entry, "price": price})

    def finish(chain: list[dict]) -> list[dict]:
        return spread_by_provider(chain) if spread else chain

    routes: dict[str, list[dict]] = {}
    for tier in TIERS:
        in_tier = [item for item in candidates if _tier_for(item["entry"].score, cutoffs) == tier]
        if in_tier:
            ordered = _by_value(in_tier, lambda item: item["entry"].score)
            routes[tier] = finish([{"provider": item["provider"], "model": item["model"]} for item in ordered])

    kind_models: dict[str, list[dict]] = {}
    for kind in task_kinds:
        with_kind = [item for item in candidates if kind in item["entry"].kinds]

        def kind_score(item: dict, kind: str = kind) -> float:
            return float(item["entry"].kinds[kind])

        if not with_kind:
            continue
        ordered = finish(
            [
                {
                    "provider": item["provider"],
                    "model": item["model"],
                    "minTier": _tier_for(kind_score(item), cutoffs),
                }
                for item in _by_value(with_kind, kind_score)
            ]
        )
        kind_models[kind] = [
            {**item, "priority": len(ordered) - index} for index, item in enumerate(ordered)
        ]
    return {"routes": routes, "kindModels": kind_models, "unmatched": unmatched}


def suggestion_text(config_path: str, write: bool = False) -> str:
    path = Path(config_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return f"hermes-jev-routing suggest: can't read {path}: {exc}"
    if not isinstance(data, dict):
        return "hermes-jev-routing suggest: config must be a JSON object"
    ranking = data.get("ranking") if isinstance(data.get("ranking"), dict) else {}
    named = ranking.get("scoresFile") or ranking.get("scores_file")
    scores_file = Path(str(named)).expanduser() if named else path.with_name(path.stem + ".scores.json")
    scores, error = load_scores(scores_file)
    if scores is None:
        return f"hermes-jev-routing suggest: {error}"
    models = []
    for bucket in (
        (data.get("routes") or {}).values(),
        (data.get("kindModels") or data.get("kind_models") or {}).values(),
        [(data.get("free") or {}).get("pool") or []],
    ):
        for chain in bucket:
            if not isinstance(chain, list):
                continue
            for item in chain:
                if isinstance(item, dict) and item.get("provider") and item.get("model"):
                    models.append((str(item["provider"]), str(item["model"])))
    cutoffs = ranking.get("cutoffs") if isinstance(ranking.get("cutoffs"), dict) else None
    spread = ranking.get("spreadProviders", ranking.get("spread_providers", True))
    kinds = list((data.get("taskKinds") or data.get("task_kinds") or {}).keys()) or [
        "plan", "implement", "debug", "refactor", "review", "research", "explain", "operate", "write", "chat",
    ]
    result = suggest_routes(
        task_kinds=kinds,
        models=models,
        scores=scores,
        cutoffs=cutoffs,
        spread=bool(spread),
    )
    payload = {"routes": result["routes"], "kindModels": result["kindModels"]}
    body = json.dumps(payload, indent=2)
    if write:
        if not result["routes"] and not result["kindModels"]:
            return "hermes-jev-routing suggest: nothing to write, none of the scored models are in the catalogue"
        target = path.with_name(path.stem + ".generated.json")
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(body + "\n", encoding="utf-8")
        tmp.replace(target)
        saved = f"wrote {target}. The hand table still wins per tier and kind."
    else:
        saved = "preview only. Run /jev-routing suggest --write to save it."
    unmatched = result["unmatched"]
    lines = [
        f"suggested {len(result['routes'])} tier(s) and {len(result['kindModels'])} kind specialist(s) from {len(scores.models) - len(unmatched)} scored model(s)",
        f"not in the catalogue: {', '.join(unmatched)}" if unmatched else "",
        saved,
        body,
    ]
    return "\n".join(line for line in lines if line)
