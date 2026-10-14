"""Rolling agent telemetry for the Discord presence publisher.

Numbers come from documented Hermes plugin hooks only. Throughput and cache-hit
maths match the desktop status bar: sum(output)/sum(duration) over the window,
and cache_read/prompt with None when the window has no cached reads.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .quota_bridge import for_provider

DEFAULT_WINDOW = 12
TURN_LEASE_SECONDS = 120
_COMPRESSION_DROP_RATIO = 0.5
_COMPRESSION_MIN_PROMPT = 1000


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def _float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number < 0 or number > 1e6:
        return 0.0
    return number


def _clean(value: Any) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _plugin_root() -> Path:
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class Snapshot:
    model: str = ""
    provider: str = ""
    platform: str = ""
    session_id: str = ""
    turn_live: bool = False
    inflight: bool = False
    current_tool: str = ""

    requests: int = 0
    api_calls: int = 0
    errors: int = 0

    tps: float = 0.0
    instant_tps: float = 0.0
    cache_hit_pct: float | None = None
    context_used: int = 0
    context_length: int = 0
    context_pct: float | None = None
    latency: float = 0.0

    output_tokens: int = 0
    total_tokens: int = 0
    compressions: int = 0

    last_activity: float = 0.0
    started_at: float = 0.0

    quota: dict | None = None

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)

    @property
    def busy(self) -> bool:
        return self.busy_at(None)

    def busy_at(self, now: float | None = None) -> bool:
        if self.inflight or self.current_tool:
            return True
        if not self.turn_live:
            return False
        return self.idle_seconds(now) < TURN_LEASE_SECONDS

    def idle_seconds(self, now: float | None = None) -> float:
        if not self.last_activity:
            return 0.0
        return max(0.0, (now if now is not None else time.time()) - self.last_activity)


@dataclass
class _Request:
    ended_at: float
    duration: float
    output_tokens: int
    prompt_tokens: int
    cache_read_tokens: int
    context_length: int


class MetricsCollector:
    def __init__(self, window: int = DEFAULT_WINDOW, *, plugin_root: Path | None = None) -> None:
        self._lock = threading.Lock()
        self._window_size = max(1, int(window or DEFAULT_WINDOW))
        self._requests: deque[_Request] = deque(maxlen=self._window_size)
        self._plugin_root = plugin_root or _plugin_root()
        self._reset_locked()

    def _reset_locked(self) -> None:
        self._requests.clear()
        self._model = ""
        self._provider = ""
        self._platform = ""
        self._session_id = ""
        self._turn_live = False
        self._inflight = False
        self._current_tool = ""
        self._context_length = 0
        self._api_calls = 0
        self._errors = 0
        self._total_tokens = 0
        self._compressions = 0
        self._last_prompt_tokens = 0
        self._last_activity = 0.0
        self._started_at = time.time()

    def reset(self) -> None:
        with self._lock:
            self._reset_locked()

    def on_pre_api_request(self, **kwargs: Any) -> None:
        context_length = _int(kwargs.get("context_length"))
        with self._lock:
            self._inflight = True
            self._last_activity = time.time()
            if context_length:
                self._context_length = context_length
            self._model = _clean(kwargs.get("model")) or self._model
            self._provider = _clean(kwargs.get("provider")) or self._provider
            self._platform = _clean(kwargs.get("platform")) or self._platform
            self._session_id = _clean(kwargs.get("session_id")) or self._session_id

    def on_post_api_request(self, **kwargs: Any) -> None:
        raw_usage = kwargs.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        duration = _float(kwargs.get("api_duration"))
        context_length = _int(kwargs.get("context_length"))
        prompt_tokens = _int(usage.get("prompt_tokens"))
        if not prompt_tokens:
            prompt_tokens = (
                _int(usage.get("input_tokens"))
                + _int(usage.get("cache_read_tokens"))
                + _int(usage.get("cache_write_tokens"))
            )
        record = _Request(
            ended_at=time.time(),
            duration=duration,
            output_tokens=_int(usage.get("output_tokens")),
            prompt_tokens=prompt_tokens,
            cache_read_tokens=_int(usage.get("cache_read_tokens")),
            context_length=context_length,
        )
        with self._lock:
            self._inflight = False
            self._turn_live = True
            self._api_calls += 1
            self._last_activity = record.ended_at
            self._total_tokens += _int(usage.get("total_tokens")) or (
                prompt_tokens + record.output_tokens
            )
            if record.context_length:
                self._context_length = record.context_length
            self._model = _clean(kwargs.get("model")) or self._model
            self._provider = _clean(kwargs.get("provider")) or self._provider
            self._platform = _clean(kwargs.get("platform")) or self._platform
            self._session_id = _clean(kwargs.get("session_id")) or self._session_id
            if (
                self._last_prompt_tokens >= _COMPRESSION_MIN_PROMPT
                and record.prompt_tokens
                < self._last_prompt_tokens * _COMPRESSION_DROP_RATIO
            ):
                self._compressions += 1
            self._last_prompt_tokens = record.prompt_tokens
            self._requests.append(record)

    def on_api_request_error(self, **kwargs: Any) -> None:
        with self._lock:
            self._inflight = False
            self._errors += 1
            self._last_activity = time.time()

    def on_pre_tool_call(self, *, tool_name: str = "", **kwargs: Any) -> None:
        with self._lock:
            self._current_tool = _clean(tool_name)
            self._last_activity = time.time()

    def on_post_tool_call(self, **kwargs: Any) -> None:
        with self._lock:
            self._current_tool = ""

    def on_pre_llm_call(self, **kwargs: Any) -> None:
        with self._lock:
            self._turn_live = True
            self._model = _clean(kwargs.get("model")) or self._model
            self._provider = _clean(kwargs.get("provider")) or self._provider
            self._platform = _clean(kwargs.get("platform")) or self._platform
            self._session_id = _clean(kwargs.get("session_id")) or self._session_id

    def on_post_llm_call(self, **kwargs: Any) -> None:
        with self._lock:
            self._turn_live = False
            self._inflight = False
            self._current_tool = ""
            self._last_activity = time.time()

    def snapshot(self) -> Snapshot:
        with self._lock:
            requests = list(self._requests)
            timed = [r for r in requests if r.duration > 0]
            total_duration = sum(r.duration for r in timed)
            total_output = sum(r.output_tokens for r in timed)
            total_prompt = sum(r.prompt_tokens for r in requests)
            total_read = sum(r.cache_read_tokens for r in requests)
            last = requests[-1] if requests else None
            last_timed = timed[-1] if timed else None
            cache_hit: float | None = None
            if total_prompt > 0 and total_read > 0:
                cache_hit = max(0.0, min(100.0, total_read / total_prompt * 100.0))
            context_used = last.prompt_tokens if last else 0
            context_length = self._context_length or (last.context_length if last else 0)
            context_pct: float | None = None
            if context_length > 0:
                context_pct = max(0.0, min(100.0, context_used / context_length * 100.0))
            provider = self._provider
            snap_kw = dict(
                model=self._model,
                provider=provider,
                platform=self._platform,
                session_id=self._session_id,
                turn_live=self._turn_live,
                inflight=self._inflight,
                current_tool=self._current_tool,
                requests=len(requests),
                api_calls=self._api_calls,
                errors=self._errors,
                tps=(total_output / total_duration) if total_duration > 0 else 0.0,
                instant_tps=(
                    (last_timed.output_tokens / last_timed.duration)
                    if last_timed and last_timed.duration > 0
                    else 0.0
                ),
                cache_hit_pct=cache_hit,
                context_used=context_used,
                context_length=context_length,
                context_pct=context_pct,
                latency=(total_duration / len(timed)) if timed else 0.0,
                output_tokens=total_output,
                total_tokens=self._total_tokens,
                compressions=self._compressions,
                last_activity=self._last_activity,
                started_at=self._started_at,
            )
        quota = None
        try:
            quota = for_provider(self._plugin_root, provider)
        except Exception:
            quota = None
        return Snapshot(**snap_kw, quota=quota)
