"""Cross-process file locks and a shared OAuth-client request budget."""
import hashlib
import json
import os
from pathlib import Path
import threading
import time
from contextlib import contextmanager

MIN_INTERVAL = 0.6
_LOCKS, _GUARD = {}, threading.Lock()


def shared_root():
    return Path(os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "hermes-reddit/coordination"


@contextmanager
def file_lock(path, timeout=20):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _GUARD:
        lock = _LOCKS.setdefault(str(path.resolve()), threading.RLock())
    with lock, path.open("a+b") as handle:
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


class Budget:
    def __init__(self, values):
        self.values = values

    def capture(self, headers, status=200):
        headers = {k.lower(): v for k, v in (headers.items() if headers else [])}
        self.values["observed_at"] = time.time()
        self.values["headers"] = {k: v for k, v in headers.items() if k.startswith("x-ratelimit-")}
        try:
            if status == 429 or float(headers.get("x-ratelimit-remaining", 1)) <= 0:
                self.values["blocked_until"] = time.time() + max(1, float(headers.get("retry-after") or headers.get("x-ratelimit-reset") or 5)) + 1
        except (TypeError, ValueError):
            if status == 429:
                self.values["blocked_until"] = time.time() + 60


@contextmanager
def request_slot(client_id):
    if not client_id:
        yield Budget({})
        return
    path = shared_root() / (hashlib.sha256(client_id.encode()).hexdigest() + ".json")
    with file_lock(path.with_suffix(".lock")):
        values = read_state(path)
        delay = float(values.get("blocked_until", 0)) - time.time()
        if delay > 0:
            raise RuntimeError(f"Shared Reddit rate budget exhausted; retry after {int(delay) + 1} seconds")
        delay = min(MIN_INTERVAL, max(0, float(values.get("next_at", 0)) - time.time()))
        if delay:
            time.sleep(delay)
        try:
            yield Budget(values)
        finally:
            values["next_at"] = time.time() + MIN_INTERVAL
            path.write_text(json.dumps(values), encoding="utf-8")
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
