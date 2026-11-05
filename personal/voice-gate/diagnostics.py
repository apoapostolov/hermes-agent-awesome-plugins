"""Personal-only, bounded local diagnostics. Never record document contents."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import traceback
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 4
MAX_RECORD_BYTES = 16 * 1024
_lock = threading.Lock()
_operation = ContextVar('voice_gate_diagnostic_operation', default=None)


def identifier(value):
    return hashlib.sha256(str(value).encode('utf-8', errors='replace')).hexdigest()[:20]


def file_id(path):
    path = Path(path)
    try:
        resolved = path.resolve()
    except (OSError, ValueError):
        resolved = path
    return {'id': identifier(resolved), 'suffix': path.suffix.lower()[:16]}


def _bounded(value, depth=0):
    if depth > 4:
        return '[depth limit]'
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:160]
    if isinstance(value, dict):
        return {str(k)[:80]: _bounded(v, depth + 1) for k, v in list(value.items())[:128]}
    if isinstance(value, (list, tuple)):
        return [_bounded(v, depth + 1) for v in value[:48]]
    return type(value).__name__


@contextmanager
def _process_lock(directory):
    # A shared one-byte lock keeps rotation safe across Hermes bot processes.
    descriptor = os.open(directory / 'events.lock', os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, 'r+b') as handle:
        if handle.seek(0, 2) == 0:
            handle.write(b'0')
            handle.flush()
        acquired = False
        try:
            for _ in range(5):
                try:
                    handle.seek(0)
                    if os.name == 'nt':
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    acquired = True
                    break
                except OSError:
                    time.sleep(0.01)
            yield acquired
        finally:
            if acquired:
                if os.name == 'nt':
                    import msvcrt
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def emit(home, event, **fields):
    """Logging must never interrupt a tool or a review; contention may drop events."""
    try:
        record = {'time': datetime.now(timezone.utc).isoformat(), 'event': event,
                  'schema': 1, 'pid': os.getpid(), 'operation': _operation.get(),
                  **_bounded(fields)}
        encoded = (json.dumps(record, ensure_ascii=True, allow_nan=False) + '\n').encode('utf-8')
        if len(encoded) > MAX_RECORD_BYTES:
            record = {k: record[k] for k in ('time', 'event', 'schema', 'pid', 'operation')}
            record['details_dropped'] = True
            encoded = (json.dumps(record) + '\n').encode('utf-8')
        directory = Path(home) / 'logs' / 'voice-gate'
        with _lock:
            directory.mkdir(parents=True, exist_ok=True)
            with _process_lock(directory) as acquired:
                if not acquired:
                    return
                target = directory / 'events.jsonl'
                if target.exists() and target.stat().st_size + len(encoded) > MAX_BYTES:
                    for index in range(BACKUPS, 0, -1):
                        older = directory / ('events.jsonl' if index == 1 else f'events.jsonl.{index - 1}')
                        newer = directory / f'events.jsonl.{index}'
                        if older.exists():
                            older.replace(newer)
                with target.open('ab') as handle:
                    handle.write(encoded)
    except Exception:
        # A full disk, unavailable home or locked file must not change plugin behavior.
        pass


def error_fields(exc):
    return {'error_type': type(exc).__name__,
            'frames': [{'file': Path(frame.filename).name, 'function': frame.name, 'line': frame.lineno}
                       for frame in traceback.extract_tb(exc.__traceback__)[-12:]]}


def summary(payload):
    if not isinstance(payload, dict):
        return {'result': 'no_action' if payload is None else type(payload).__name__}
    result = {'ok': payload.get('ok'), 'action': payload.get('action'),
              'has_error': bool(payload.get('error'))}
    for key in ('checks', 'issues', 'reviewed', 'residuals', 'profiles', 'patterns'):
        if isinstance(payload.get(key), (list, dict)):
            result[key + '_count'] = len(payload[key])
    result['checks'] = [
        {'words': check.get('words'), 'context': check.get('context'),
         'eligible': check.get('eligible_for_turn_gate'),
         'rules': {key: tell.get('count', 0) for key, tell in check.get('tells', {}).items()
                   if tell.get('count', 0)}}
        for check in payload.get('checks', [])[:12] if isinstance(check, dict)]
    return result


def traced(event, home):
    """Correlate entry/exit/errors while retaining the hook/tool calling convention."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            token = _operation.set(uuid.uuid4().hex)
            start = time.perf_counter()
            def record(name, **fields):
                try:
                    emit(home(), name, **fields)
                except Exception:
                    pass
            try:
                record(event + '.start')
                result = fn(*args, **kwargs)
                record(event + '.finish', elapsed_ms=round((time.perf_counter() - start) * 1000, 2),
                     **summary(result))
                return result
            except Exception as exc:
                record(event + '.error', **error_fields(exc))
                raise
            finally:
                _operation.reset(token)
        return wrapped
    return decorate
