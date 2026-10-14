"""Secret-free quota snapshot shared by the desktop backend and Discord presence.

The dashboard process writes; the gateway process reads. Nothing in this file
stores keys, tokens, emails, or pool values.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

CACHE_NAME = "quota-cache.json"

# Hermes config.yaml provider id -> plugin chip id.
PROVIDER_TO_PID: dict[str, str] = {
    "zai": "glm",
    "z_ai": "glm",
    "glm": "glm",
    "deepseek": "deepseek",
    "xai": "grok",
    "grok": "grok",
    "xai-oauth": "grok",
    "openai": "codex",
    "codex": "codex",
    "openai-codex": "codex",
    "opencode": "opencode",
    "opencode-go": "opencode",
    "openrouter": "openrouter",
    "tavily": "tavily",
    "anthropic": "anthropic",
    "groq": "groq",
    "cerebras": "cerebras",
    "moonshot": "moonshot",
    "kimi": "moonshot",
    "kimi-coding": "moonshot",
    "minimax": "minimax",
    "gemini": "gemini",
    "google": "gemini",
    "huggingface": "huggingface",
    "hf": "huggingface",
    "mistral": "mistral",
    "qwen": "qwen",
    "dashscope": "qwen",
}

_SHORT = {
    "deepseek": "DeepSeek",
    "glm": "GLM",
    "tavily": "Tavily",
    "grok": "Grok",
    "codex": "Codex",
    "opencode": "Go",
    "openrouter": "OR",
    "openai": "OA",
    "anthropic": "AN",
    "groq": "GQ",
    "cerebras": "CB",
    "moonshot": "Kimi",
    "minimax": "MX",
    "gemini": "Gemini",
    "huggingface": "HF",
    "mistral": "MI",
    "qwen": "Qwen",
}

_CREDIT = {"deepseek", "openrouter"}
_INCREASE = {"glm"}


def provider_to_pid(provider: str | None) -> str | None:
    if not provider:
        return None
    key = str(provider).strip().lower()
    if not key:
        return None
    if key in PROVIDER_TO_PID:
        return PROVIDER_TO_PID[key]
    return key if key in _SHORT else None


def quota_kind(pid: str) -> str:
    if pid in _CREDIT:
        return "credit"
    if pid in _INCREASE:
        return "increase"
    return "exhaust"


def short_name(pid: str, fallback: str = "") -> str:
    return _SHORT.get(pid) or fallback or pid


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def sanitize_status(pid: str, data: dict[str, Any]) -> dict[str, Any]:
    """Keep only numbers and labels the presence can print."""
    kind = quota_kind(pid)
    remaining = _num(data.get("remaining"))
    percent = _num(data.get("percent") if data.get("percent") is not None else data.get("pct"))
    exhaust = _num(data.get("exhaust_percent"))
    balance = _num(data.get("balance"))
    granted = _num(data.get("granted"))
    if remaining is None and percent is not None:
        remaining = max(0.0, 100.0 - percent)
    if remaining is None and exhaust is not None:
        remaining = max(0.0, 100.0 - exhaust)
    quotas: list[dict[str, Any]] = []
    raw_quotas = data.get("quotas")
    if isinstance(raw_quotas, list):
        for row in raw_quotas:
            if not isinstance(row, dict):
                continue
            label = str(row.get("label") or "").strip()[:24]
            if not label:
                continue
            item: dict[str, Any] = {"label": label}
            pct = _num(row.get("percent"))
            if pct is not None:
                item["percent"] = round(max(0.0, min(100.0, pct)), 1)
            display = row.get("display")
            if isinstance(display, str) and display.strip():
                item["display"] = display.strip()[:24]
            quotas.append(item)
    out: dict[str, Any] = {
        "id": pid,
        "name": short_name(pid, str(data.get("name") or pid)),
        "ok": bool(data.get("ok")),
        "kind": kind,
        "updated_at": time.time(),
    }
    if remaining is not None:
        out["remaining"] = round(max(0.0, min(100.0, remaining)), 1)
    if percent is not None:
        out["percent"] = round(max(0.0, min(100.0, percent)), 1)
    if balance is not None:
        out["balance"] = round(balance, 2)
    if granted is not None:
        out["granted"] = round(granted, 2)
    if quotas:
        out["quotas"] = quotas
    if data.get("stale"):
        out["stale"] = True
    return out


def cache_path(root: Path) -> Path:
    return Path(root) / CACHE_NAME


def load(root: Path) -> dict[str, Any]:
    path = cache_path(root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"providers": {}, "updated_at": 0.0}
    if not isinstance(raw, dict):
        return {"providers": {}, "updated_at": 0.0}
    providers = raw.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    clean = {str(k): v for k, v in providers.items() if isinstance(v, dict)}
    return {
        "providers": clean,
        "updated_at": _num(raw.get("updated_at")) or 0.0,
    }


def upsert(root: Path, pid: str, data: dict[str, Any]) -> None:
    if not pid:
        return
    snapshot = sanitize_status(pid, data if isinstance(data, dict) else {})
    path = cache_path(root)
    current = load(root)
    providers = dict(current.get("providers") or {})
    providers[pid] = snapshot
    payload = {"updated_at": time.time(), "providers": providers}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="quota-cache-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def for_provider(root: Path, provider: str | None) -> dict[str, Any] | None:
    pid = provider_to_pid(provider)
    if not pid:
        return None
    entry = (load(root).get("providers") or {}).get(pid)
    return entry if isinstance(entry, dict) else None
