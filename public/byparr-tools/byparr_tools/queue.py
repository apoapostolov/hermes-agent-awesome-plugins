"""Single-flight request queue with bounded retries.

Byparr serialises solves internally. Sending parallel requests produces 408s and
lengthens every solve, so this queue keeps one solve in flight per process and
spaces requests. It is dependency-free and safe to use from several threads.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


class SolverQueue:
    def __init__(self, spacing: float = 0.2, retries: int = 2) -> None:
        self._lock = threading.Lock()
        self._spacing = max(0.0, float(spacing))
        self._retries = max(0, int(retries))
        self._last = 0.0
        self.in_flight = 0
        self.completed = 0
        self.retried = 0
        self.failed = 0

    def run(self, fn: Callable[[], T]) -> T:
        with self._lock:
            self.in_flight += 1
            try:
                delay = self._spacing - (time.monotonic() - self._last)
                if delay > 0:
                    time.sleep(delay)
                last_error: Exception | None = None
                for attempt in range(self._retries + 1):
                    try:
                        result = fn()
                        self.completed += 1
                        return result
                    except Exception as exc:  # noqa: BLE001 - retry any transient failure
                        last_error = exc
                        if attempt < self._retries:
                            self.retried += 1
                            time.sleep(min(2.0, 0.25 * (2 ** attempt)))
                self.failed += 1
                assert last_error is not None
                raise last_error
            finally:
                self._last = time.monotonic()
                self.in_flight -= 1

    def stats(self) -> dict:
        return {
            "in_flight": self.in_flight,
            "completed": self.completed,
            "retried": self.retried,
            "failed": self.failed,
            "spacing_seconds": self._spacing,
            "max_retries": self._retries,
        }
