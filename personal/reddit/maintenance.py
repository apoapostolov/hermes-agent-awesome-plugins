"""Profile-bound cleanup and optional bounded revalidation."""
import json
from pathlib import Path
import threading
import time
from . import client, coordination, library

_RUNNERS, _STOPS, _LOCK = {}, {}, threading.Lock()


def run_once(home=None):
    home = Path(home or client.hermes_home()).resolve()
    root = home / "plugin-data/reddit"
    with coordination.file_lock(root / "maintenance.lock"):
        store = library.Library(home=home)
        state = {"checked_at": int(time.time()), "purge": "complete", "refresh": "disabled"}
        if client.load_config(home).get("background_refresh"):
            previous = coordination.read_state(root / "maintenance.json")
            if time.time() - previous.get("last_refresh_attempt", 0) >= 1800:
                state["last_refresh_attempt"] = time.time()
                session = client.Reddit(home=home)
                if session.has_refresh_token:
                    try:
                        store = library.Library(session.require_account(), home=home)
                        state["refresh"] = library.refresh(session, store, store.names(100))
                    except Exception as exc:
                        state.update(refresh="failed", error=str(exc)[:500])
                else:
                    state["refresh"] = "login_required"
            else:
                state.update(last_refresh_attempt=previous.get("last_refresh_attempt", 0), refresh="not_due")
        client._atomic_write(root / "maintenance.json", json.dumps(state))
        return state


def status(home=None):
    home = Path(home or client.hermes_home()).resolve()
    return {"running": str(home) in _RUNNERS and _RUNNERS[str(home)].is_alive(),
            "background_refresh": bool(client.load_config(home).get("background_refresh")),
            "last_run": coordination.read_state(home / "plugin-data/reddit/maintenance.json"),
            "limit": "Cleanup stops when Hermes is stopped. Optional online refresh checks at most 100 items per 30 minutes."}


def stop(home=None):
    event = _STOPS.get(str(Path(home or client.hermes_home()).resolve()))
    if event:
        event.set()


def start(home=None):
    home = Path(home or client.hermes_home()).resolve()
    key = str(home)
    with _LOCK:
        if key in _RUNNERS and _RUNNERS[key].is_alive():
            return lambda: stop(home)
        stopping = threading.Event()
        def worker():
            while not stopping.is_set():
                try:
                    run_once(home)
                except Exception:
                    pass
                stopping.wait(60)
        thread = threading.Thread(target=worker, name="reddit-maintenance", daemon=True)
        _RUNNERS[key], _STOPS[key] = thread, stopping
        thread.start()
        return lambda: stop(home)
