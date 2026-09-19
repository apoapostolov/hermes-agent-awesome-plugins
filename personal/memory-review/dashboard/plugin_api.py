"""Memory-Review backend. Mounted at /api/plugins/memory-review/."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

_DEFAULT_MEMORY_LIMIT = 2200
_DEFAULT_USER_LIMIT = 1375
_LIMIT_RE = re.compile(
    r"^(?:[ \t]*)(memory_char_limit|user_char_limit)[ \t]*:[ \t]*(\d+)",
    re.MULTILINE,
)


def hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        win = Path(local) / "hermes"
        if win.exists():
            return win
    return Path.home() / ".hermes"


def store_chars(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        return len(path.read_text(encoding="utf-8"))
    except OSError:
        return 0


def pending_dir(home: Path) -> Path:
    return home / "pending" / "memory"


# Core writes pending ids as uuid4().hex[:8]; accept only hex ids so a
# request body cannot build a path outside pending/memory/ (../, /).
_PENDING_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")


def pending_path(folder: Path, pid: str) -> Path | None:
    if not _PENDING_ID_RE.fullmatch(pid):
        return None
    return folder / f"{pid}.json"


def char_limits(home: Path) -> tuple[int, int]:
    memory_limit = _DEFAULT_MEMORY_LIMIT
    user_limit = _DEFAULT_USER_LIMIT
    cfg = home / "config.yaml"
    if not cfg.is_file():
        return memory_limit, user_limit
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return memory_limit, user_limit
    for match in _LIMIT_RE.finditer(text):
        key, raw = match.group(1), int(match.group(2))
        if key == "memory_char_limit":
            memory_limit = raw
        else:
            user_limit = raw
    return memory_limit, user_limit


def _op_text(op: dict) -> tuple[str, str]:
    act = str(op.get("action") or "").strip().lower()
    if act == "add":
        text = str(op.get("content") or op.get("new_text") or "").strip()
    elif act == "replace":
        text = str(op.get("content") or op.get("new_text") or "").strip()
    elif act == "remove":
        text = str(op.get("old_text") or "").strip()
    else:
        text = str(op.get("content") or op.get("new_text") or op.get("old_text") or "").strip()
        act = act or "replace"
    return act, text


def public_item(rec: dict) -> dict:
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    ops = payload.get("operations") if isinstance(payload.get("operations"), list) else []
    target = payload.get("target") or "memory"
    if target not in ("memory", "user"):
        target = "memory"
    summary = str(rec.get("summary") or "").strip()
    details = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        act, text = _op_text(op)
        details.append({"action": act, "text": text})
    return {
        "id": str(rec.get("id") or ""),
        "summary": summary,
        "origin": str(rec.get("origin") or ""),
        "target": target,
        "action": str(rec.get("action") or payload.get("action") or ""),
        "ops": len(details) if details else 1,
        "ops_detail": details,
    }


def list_items(home: Path) -> list[dict]:
    folder = pending_dir(home)
    if not folder.is_dir():
        return []
    records: list[dict] = []
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError:
        return []
    for path in paths:
        if not path.is_file():
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(rec, dict):
            continue
        item = public_item(rec)
        if item["id"]:
            records.append(item)
    records.sort(key=lambda row: row["id"])
    return records


def entry_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return 0
    parts = [p for p in text.split("\n§\n") if p.strip()]
    return len(parts)


def store_info(path: Path, limit: int) -> dict:
    used = store_chars(path)
    pct = min(100, int(round(100.0 * used / limit))) if limit > 0 else 0
    return {
        "entries": entry_count(path),
        "used": used,
        "limit": limit,
        "pct": pct,
    }


def read_state(home: Path | None = None) -> dict:
    root = home if home is not None else hermes_home()
    try:
        memory_limit, user_limit = char_limits(root)
        memories = root / "memories"
        mem = store_info(memories / "MEMORY.md", memory_limit)
        user = store_info(memories / "USER.md", user_limit)
        items = list_items(root)
        return {
            "ok": True,
            "pending": len(items),
            "memory_full": bool(memory_limit) and mem["used"] >= memory_limit,
            "user_full": bool(user_limit) and user["used"] >= user_limit,
            "stores": {"memory": mem, "user": user},
            "items": items,
        }
    except Exception:
        return {"ok": False, "items": []}


def _store_entries(store, target: str) -> list[str]:
    if target == "user":
        return [str(x) for x in (getattr(store, "user_entries", None) or [])]
    return [str(x) for x in (getattr(store, "memory_entries", None) or [])]


def _unique_hits(entries: list[str], old: str) -> list[int]:
    if not old:
        return []
    return [i for i, entry in enumerate(entries) if old in entry]


def _guess_old(entries: list[str], content: str) -> str | None:
    if not content or len(content) < 16:
        return None
    key = content[:24]
    hits = [entry for entry in entries if entry.startswith(key) or content.startswith(entry[:24])]
    if len(hits) != 1:
        return None
    entry = hits[0]
    for n in (48, 32, 24):
        needle = entry[:n]
        if needle and sum(1 for item in entries if needle in item) == 1:
            return needle
    return entry[:80]


def _prepare_op(op: dict, entries: list[str]) -> dict | None:
    act = str(op.get("action") or "").strip().lower()
    content = str(op.get("content") or op.get("new_text") or "").strip()
    old = str(op.get("old_text") or "").strip()
    if act == "add":
        return {"action": "add", "content": content} if content else None
    if act == "remove":
        if len(_unique_hits(entries, old)) == 1:
            return {"action": "remove", "old_text": old}
        return None
    if act == "replace":
        if len(_unique_hits(entries, old)) == 1 and content:
            return {"action": "replace", "old_text": old, "content": content}
        guessed = _guess_old(entries, content)
        if guessed and content:
            return {"action": "replace", "old_text": guessed, "content": content}
        return None
    return None


def prepare_payload(payload: dict, store) -> dict:
    if not isinstance(payload, dict):
        return {}
    target = payload.get("target") or "memory"
    if target not in ("memory", "user"):
        target = "memory"
    action = str(payload.get("action") or "").strip().lower()
    entries = _store_entries(store, target)
    if action == "batch":
        ops = []
        for op in payload.get("operations") or []:
            if isinstance(op, dict):
                fixed = _prepare_op(op, entries)
                if fixed:
                    ops.append(fixed)
        out = dict(payload)
        out["target"] = target
        out["action"] = "batch"
        out["operations"] = ops
        return out
    if action == "replace":
        content = str(payload.get("content") or payload.get("new_text") or "").strip()
        old = str(payload.get("old_text") or "").strip()
        if len(_unique_hits(entries, old)) == 1 and content:
            return {**payload, "action": "replace", "target": target, "content": content, "old_text": old}
        guessed = _guess_old(entries, content)
        if guessed and content:
            return {**payload, "action": "replace", "target": target, "content": content, "old_text": guessed}
        if content:
            return {**payload, "action": "add", "target": target, "content": content}
    return dict(payload)


def reject_ids(ids: list[str], home: Path) -> dict:
    folder = pending_dir(home)
    n = 0
    failed: list[dict[str, str]] = []
    for pid in ids:
        path = pending_path(folder, pid)
        if path is None:
            failed.append({"id": pid, "error": "invalid id"})
            continue
        try:
            if path.is_file():
                path.unlink()
                n += 1
        except OSError:
            continue
    return {"ok": True, "rejected": n, "failed": failed}


def _apply_one(rec: dict, apply_fn, store) -> tuple[bool, str]:
    payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
    try:
        result = apply_fn(payload, store)
    except Exception as exc:
        return False, str(exc)
    if isinstance(result, dict):
        return bool(result.get("success")), str(result.get("error") or "")
    return False, "bad apply result"


def approve_ids(ids: list[str], home: Path, apply_fn=None, store=None) -> dict:
    if apply_fn is None or store is None:
        try:
            from tools.memory_tool import apply_memory_pending, load_on_disk_store
        except Exception:
            return {"ok": False, "error": "memory store unavailable", "applied": 0, "failed": []}
        apply_fn = apply_memory_pending
        store = load_on_disk_store()
    folder = pending_dir(home)
    applied = 0
    failed: list[dict[str, str]] = []
    for pid in ids:
        path = pending_path(folder, pid)
        if path is None:
            failed.append({"id": pid, "error": "invalid id"})
            continue
        if not path.is_file():
            failed.append({"id": pid, "error": "missing"})
            continue
        try:
            rec = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            failed.append({"id": pid, "error": "unreadable"})
            continue
        if not isinstance(rec, dict):
            failed.append({"id": pid, "error": "bad record"})
            continue
        payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        prepared = prepare_payload(payload, store)
        reset = getattr(store, "reset_consolidation_failures", None)
        if callable(reset):
            reset()
        load = getattr(store, "load_from_disk", None)
        if callable(load):
            load()
            prepared = prepare_payload(payload, store)

        def attempt(body: dict) -> tuple[bool, str]:
            if body.get("action") == "batch" and not body.get("operations"):
                return True, "stale"
            return _apply_one({"payload": body}, apply_fn, store)

        ok, err = attempt(prepared)
        if not ok and "over the limit" in (err or "").lower():
            slim = dict(prepared)
            if slim.get("action") == "batch":
                slim["operations"] = [
                    op for op in (slim.get("operations") or []) if op.get("action") != "add"
                ]
            ok, err = attempt(slim)
        if ok:
            try:
                path.unlink()
            except OSError:
                pass
            applied += 1
        else:
            failed.append({"id": pid, "error": err or "failed"})
    return {"ok": True, "applied": applied, "failed": failed}


class DecideBody(BaseModel):
    action: str
    ids: list[str] | None = None


def decide(action: str, ids: list[str], home: Path | None = None, apply_fn=None, store=None) -> dict:
    root = home if home is not None else hermes_home()
    clean = [str(i).strip() for i in ids if str(i).strip()]
    if action == "reject":
        return reject_ids(clean, root)
    if action == "approve":
        return approve_ids(clean, root, apply_fn=apply_fn, store=store)
    return {"ok": False, "error": "unknown action"}


@router.get("/state")
def get_state() -> dict:
    return read_state()


@router.post("/decide")
def post_decide(body: DecideBody | None = None) -> dict:
    payload = body if body is not None else DecideBody(action="")
    return decide(payload.action, payload.ids or [])
