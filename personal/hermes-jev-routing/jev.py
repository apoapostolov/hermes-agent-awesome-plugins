"""TypeSafe Jev client for the four routing questions.

The transport is injected. This module never reads an API key from disk and
never logs one. A missing key, a timeout, or a bad payload is the caller's
fail-open path.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Callable, Mapping

try:
    from .decide import Analysis
except ImportError:
    from decide import Analysis

Transport = Callable[[str, Mapping[str, str], dict, float], dict]

_COMPLEXITY = [
    "Trivial: one obvious step, no design decisions, answer is known or mechanical",
    "Moderate: a few dependent steps using familiar patterns, little ambiguity",
    "Complex: multiple files or interacting constraints, real tradeoffs to weigh",
    "Architectural: cross-cutting design, high stakes, long horizon, easy to get subtly wrong",
]
_CAPABILITY = [
    "Minimal: any fast small model answers this just as well",
    "Standard: a competent mid-tier model is enough",
    "High: a strong frontier model materially improves the outcome",
    "Maximum: correctness matters more than cost; use the best available",
]


class JevError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def build_questions(task_kinds: Mapping[str, str]) -> dict:
    return {
        "task_kind": {
            "type": "choice",
            "instructions": (
                "Which single kind of work does `request` ask for? Judge the work the user "
                "wants done, not the topic they mention. Read `conversation_excerpt` when the "
                "request is a short follow-up that only makes sense in context. Pick the closest "
                "kind even when the request is ambiguous."
            ),
            "criteria": dict(task_kinds),
        },
        "complexity": {
            "type": "score",
            "instructions": (
                "How hard is `request` to do well, judged only on the work itself? Use the "
                "conversation excerpt and environment to judge scope. Ignore how much any model costs."
            ),
            "criteria": list(_COMPLEXITY),
        },
        "capability_deserved": {
            "type": "score",
            "instructions": (
                "Setting price aside entirely, how much model capability does this request deserve "
                "to get a good outcome? Judge by stakes, difficulty, and how much a stronger model "
                "would measurably improve the result."
            ),
            "criteria": list(_CAPABILITY),
        },
        "needs_deep_reasoning": {
            "type": "noul",
            "instructions": (
                "Does answering `request` well require extended multi-step reasoning (algorithm "
                "design, subtle debugging, proof, careful long-horizon planning) rather than recall, "
                "lookup, or a short direct edit?"
            ),
            "criteria": {
                "true": "The work hinges on reasoning through non-obvious steps or edge cases",
                "false": "The work is recall, lookup, formatting, or a short direct change",
            },
        },
    }


def build_state(prompt: str, history: str = "", active_model: str = "") -> dict:
    excerpt = history[-4000:] if history else None
    return {
        "request": prompt,
        "conversation_excerpt": excerpt,
        "environment": {"active_model": active_model or None},
        "budget": {
            "spent_today_usd": 0,
            "spent_this_month_usd": 0,
            "daily_cap_usd": None,
            "monthly_cap_usd": None,
            "fraction_of_budget_used": 0,
        },
    }


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value:  # NaN
        return None
    return float(value)


def parse_analysis(payload: Mapping[str, object], task_kinds: Mapping[str, str]) -> Analysis:
    answers = payload.get("answers") if isinstance(payload.get("answers"), Mapping) else {}
    kind = answers.get("task_kind") if isinstance(answers.get("task_kind"), Mapping) else {}
    complexity = answers.get("complexity") if isinstance(answers.get("complexity"), Mapping) else {}
    capability = answers.get("capability_deserved") if isinstance(answers.get("capability_deserved"), Mapping) else {}
    reasoning = answers.get("needs_deep_reasoning") if isinstance(answers.get("needs_deep_reasoning"), Mapping) else {}
    chosen = kind.get("choice") if isinstance(kind.get("choice"), str) else "chat"
    if chosen not in task_kinds:
        raise JevError(f"Jev returned an unknown task kind: {chosen}")
    deep = _num(reasoning.get("noul"))
    if deep is None:
        deep = _num(reasoning.get("noul_score")) or 0.0
    probs = kind.get("probabilities") if isinstance(kind.get("probabilities"), Mapping) else {}
    latency = _num(payload.get("latency_ms"))
    if latency is None:
        latency = _num(payload.get("latencyMs")) or 0.0
    return Analysis(
        kind=chosen,
        complexity=_num(complexity.get("score")) if _num(complexity.get("score")) is not None else 1.0,
        budget_intensity=_num(capability.get("score")) if _num(capability.get("score")) is not None else 1.0,
        deep_reasoning=deep,
        kind_confidence=_num(kind.get("confidence")) or 0.0,
        kind_probabilities={str(key): float(value) for key, value in probs.items() if _num(value) is not None},
        complexity_confidence=_num(complexity.get("confidence")) or 0.0,
        capability_confidence=_num(capability.get("confidence")) or 0.0,
        latency_ms=int(latency),
    )


def urllib_transport(url: str, headers: Mapping[str, str], body: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=dict(headers),
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise JevError(f"TypeSafe {exc.code}: {detail}", exc.code) from None


def classify(
    prompt: str,
    *,
    api_key: str,
    endpoint: str,
    jev_model: str,
    task_kinds: Mapping[str, str],
    timeout_ms: int = 3500,
    history: str = "",
    active_model: str = "",
    transport: Transport = urllib_transport,
) -> Analysis:
    if not api_key:
        raise JevError("missing TypeSafe key")
    body = {
        "state": build_state(prompt, history, active_model),
        "model": jev_model,
        "questions": build_questions(task_kinds),
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = transport(endpoint, headers, body, max(timeout_ms, 1) / 1000)
    return parse_analysis(payload, task_kinds)
