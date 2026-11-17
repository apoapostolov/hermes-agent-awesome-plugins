"""In-memory, session-scoped cookie jar for solver-to-browser handoff.

No disk writes by default: cookies are live session state and must not leak into
backups, commits or chat. The optional disk tier is off unless the user opts in
in Settings, and even then it stores only the CDP payload in the plugin's own
data dir with restrictive permissions.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List


class CookieJar:
    def __init__(self, ttl: int = 1800, persist: bool = False, data_dir: str = "") -> None:
        self._ttl = max(1, int(ttl))
        self._persist = bool(persist)
        self._data_dir = data_dir
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _path(self, session: str) -> str:
        safe = "".join(c for c in session if c.isalnum() or c in "-_")
        return os.path.join(self._data_dir or ".", "cookies-" + (safe or "default") + ".json")

    def put(self, session: str, cookies: List[Dict[str, Any]], user_agent: str = "") -> Dict[str, Any]:
        entry = {
            "cookies": cookies,
            "user_agent": user_agent,
            "created": time.time(),
        }
        self._sessions[session] = entry
        if self._persist and self._data_dir:
            try:
                os.makedirs(self._data_dir, exist_ok=True)
                with open(self._path(session), "w", encoding="utf-8") as fh:
                    json.dump(entry, fh)
                os.chmod(self._path(session), 0o600)
            except OSError:
                pass
        return self.describe(session)

    def get(self, session: str) -> Dict[str, Any] | None:
        entry = self._sessions.get(session)
        if entry and time.time() - entry["created"] > self._ttl:
            self.clear(session)
            return None
        if not entry and self._persist and self._data_dir:
            try:
                with open(self._path(session), encoding="utf-8") as fh:
                    entry = json.load(fh)
                self._sessions[session] = entry
            except (OSError, ValueError, TypeError):
                return None
        return entry

    def clear(self, session: str) -> bool:
        existed = self._sessions.pop(session, None) is not None
        if self._persist and self._data_dir:
            try:
                os.remove(self._path(session))
            except OSError:
                pass
        return existed

    def describe(self, session: str) -> Dict[str, Any]:
        entry = self.get(session)
        if not entry:
            return {"session": session, "count": 0, "names": [], "expired": True}
        return {
            "session": session,
            "count": len(entry.get("cookies") or []),
            "names": [c.get("name") for c in entry.get("cookies") or []],
            "user_agent": entry.get("user_agent", ""),
            "expired": False,
        }

    def list(self) -> List[Dict[str, Any]]:
        out = []
        for session in list(self._sessions):
            out.append(self.describe(session))
            if out[-1]["expired"]:
                self._sessions.pop(session, None)
        return out
