"""Reach the live agent and switch it before the provider client sends.

pre_llm_call runs on a worker, so the agent is not a hook argument. The caller
thread is blocked in that hook and still holds the gateway cache, or the agent
itself, in a stack frame. This module walks those frames. It does not patch
Hermes.
"""

from __future__ import annotations

import sys
import threading
from typing import Any, Mapping, Optional

try:
    from .decide import TIERS, AvailableModel, Decision
except ImportError:
    from decide import TIERS, AvailableModel, Decision


def _lock(owner: Any):
    lock = getattr(owner, "_agent_cache_lock", None)
    return lock if lock is not None else threading.Lock()


def _agent_from_cache_entry(entry: Any) -> Any:
    if isinstance(entry, tuple) and entry:
        return entry[0]
    return entry


def _matches(agent: Any, session_id: str) -> bool:
    if agent is None or not session_id:
        return False
    if str(getattr(agent, "session_id", "") or "") != session_id:
        return False
    return callable(getattr(agent, "switch_model", None))


def _cache_hit(owner: Any, session_id: str) -> Any:
    cache = getattr(owner, "_agent_cache", None)
    if not isinstance(cache, Mapping):
        return None
    with _lock(owner):
        for entry in list(cache.values()):
            agent = _agent_from_cache_entry(entry)
            if _matches(agent, session_id):
                return agent
    return None


def find_live_agent(session_id: str, frames: Optional[Mapping[int, Any]] = None) -> Any:
    """Return the cached agent for this session, or the agent sitting on a caller frame."""
    if not session_id:
        return None
    if frames is None:
        frames = sys._current_frames()
    for frame in frames.values():
        current = frame
        while current is not None:
            locals_ = getattr(current, "f_locals", {}) or {}
            for value in list(locals_.values()):
                cached = _cache_hit(value, session_id)
                if cached is not None:
                    return cached
                if _matches(value, session_id):
                    return value
            current = getattr(current, "f_back", None)
    return None


def tier_index_for(config: Any, provider: str, model_id: str) -> Optional[int]:
    for index, tier in enumerate(TIERS):
        for target in config.routes.get(tier) or ():
            if target.provider == provider and target.model == model_id:
                return index
    return None


def current_model(agent: Any) -> Optional[AvailableModel]:
    provider = str(getattr(agent, "provider", "") or "")
    model_id = str(getattr(agent, "model", "") or "")
    if not provider or not model_id:
        return None
    return AvailableModel(provider=provider, id=model_id)


def apply_switch(agent: Any, decision: Decision) -> str:
    """Call switch_model when the live agent is not already on the pick."""
    provider = str(getattr(agent, "provider", "") or "")
    model_id = str(getattr(agent, "model", "") or "")
    if provider == decision.target.provider and model_id == decision.target.model:
        return "same"
    agent.switch_model(decision.target.model, decision.target.provider)
    _apply_thinking(agent, decision.target.thinking_level)
    return "switched"


def _apply_thinking(agent: Any, level: Optional[str]) -> None:
    if not level or not hasattr(agent, "reasoning_config"):
        return
    name = str(level).strip().lower()
    if name in {"off", "none", "false", "disabled"}:
        agent.reasoning_config = {"enabled": False}
        return
    agent.reasoning_config = {"enabled": True, "effort": name}


def maybe_switch(
    decision: Optional[Decision],
    session_id: str,
    mode: str,
    frames: Optional[Mapping[int, Any]] = None,
) -> str:
    if mode != "auto" or decision is None or decision.held:
        return "skip"
    agent = find_live_agent(session_id, frames)
    if agent is None:
        return "missing-agent"
    try:
        return apply_switch(agent, decision)
    except Exception:
        return "switch-failed"
