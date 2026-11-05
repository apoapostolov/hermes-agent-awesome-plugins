"""Cross-process file locks and a shared OAuth-client request budget."""
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
from contextlib import contextmanager

MIN_INTERVAL = 0.6
_LOCKS, _GUARD = {}, threading.Lock()
_HELD = threading.local()


def shared_root():
    return Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hermes-reddit/coordination"


@contextmanager
def file_lock(path, timeout=20):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _GUARD:
        lock = _LOCKS.setdefault(str(path.resolve()), threading.RLock())
    with lock:
        held = getattr(_HELD, "paths", set())
        key = str(path.resolve())
        if key in held:
            yield
            return
        with _os_lock(path, timeout) as handle:
            held.add(key)
            _HELD.paths = held
            try:
                yield
            finally:
                held.remove(key)


@contextmanager
def _os_lock(path, timeout):
    with path.open("a+b") as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b"0")
            handle.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise RuntimeError("Reddit state is busy in another process; retry shortly") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def retry_delay(headers):
    headers = {k.lower(): v for k, v in (headers.items() if headers else [])}
    for key in ("retry-after", "x-ratelimit-reset"):
        try:
            value = float(headers[key])
            if math.isfinite(value):
                return max(1, math.ceil(value) + 1)
        except (KeyError, TypeError, ValueError):
            pass
    return 6


class Budget:
    def __init__(self, values):
        self.values = values

    def capture(self, headers, status=200):
        headers = {k.lower(): v for k, v in (headers.items() if headers else [])}
        self.values["observed_at"] = time.time()
        self.values["headers"] = {k: v for k, v in headers.items() if k.startswith("x-ratelimit-")}
        try:
            if status == 429 or float(headers.get("x-ratelimit-remaining", 1)) <= 0:
                self.values["blocked_until"] = time.time() + retry_delay(headers)
        except (TypeError, ValueError):
            if status == 429:
                self.values["blocked_until"] = time.time() + 60


def _slot_path(client_id):
    return shared_root() / (hashlib.sha256(client_id.encode()).hexdigest() + ".json")


def _write_state(path, values):
    try:
        path.write_text(json.dumps(values), encoding="utf-8")
        os.chmod(path, 0o600)
    except OSError:
        # A successful remote write must not be reported as failed solely
        # because optional pacing state could not be persisted.
        import logging
        logging.getLogger(__name__).warning("Reddit pacing state could not be persisted")


def reserve_slot(client_id):
    """Take the shared slot, persist pacing, and release before the caller's network call.

    Holding the file lock across ``urlopen`` made a second process wait out
    ``file_lock`` and fail as busy on a request that was only slow.
    """
    if not client_id:
        return Budget({})
    path = _slot_path(client_id)
    with file_lock(path.with_suffix(".lock"), timeout=55):
        values = read_state(path)
        delay = float(values.get("blocked_until", 0)) - time.time()
        if delay > 0:
            raise RuntimeError(f"Shared Reddit rate budget exhausted; retry after {int(delay) + 1} seconds")
        delay = min(MIN_INTERVAL, max(0, float(values.get("next_at", 0)) - time.time()))
        if delay:
            time.sleep(delay)
        values["next_at"] = time.time() + MIN_INTERVAL
        _write_state(path, values)
    return Budget(values)


def record_slot(client_id, budget):
    """Fold one response's rate-limit headers back into the shared state."""
    if not client_id or budget is None or not budget.values:
        return
    path = _slot_path(client_id)
    try:
        with file_lock(path.with_suffix(".lock"), timeout=55):
            values = read_state(path)
            values.update({key: value for key, value in budget.values.items() if value})
            _write_state(path, values)
    except RuntimeError:
        import logging
        logging.getLogger(__name__).warning("Reddit pacing state could not be recorded")


@contextmanager
def request_slot(client_id):
    budget = reserve_slot(client_id)
    try:
        yield budget
    finally:
        record_slot(client_id, budget)
