"""Profile-local Reddit bookmarks with expiring source snapshots and literal search.

Only the standard library is used. No tokens or raw API payloads enter this DB.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import sqlite3
import time
from contextlib import contextmanager

from . import client

TTL = 48 * 60 * 60
MAX_BODY = 40000


def account_key(account="", home=None):
    name = account or client.load_token(home).get("username") or "local"
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", name):
        raise client.RedditError("Invalid library account name")
    return name.casefold()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _terms(query):
    try:
        lexer = shlex.shlex(query, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ""
        lexer.quotes = '"'
        terms = list(lexer)
    except ValueError as exc:
        raise client.RedditError("Close quoted phrases in the search query") from exc
    if len(terms) > 30 or len(query) > 1000:
        raise client.RedditError("Search supports at most 30 terms and 1000 characters")
    return [term.casefold() for term in terms if term]


class Library:
    def __init__(self, account="", home=None):
        self.account = account_key(account, home)
        self.home = pathlib.Path(home or client.hermes_home())
        self.path = self.home / "plugin-data/reddit/library.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS saves (
                account TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL,
                search_text TEXT NOT NULL, title_text TEXT NOT NULL,
                context_text TEXT NOT NULL, checked REAL NOT NULL,
                first_saved REAL NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (account, name))""")
            db.execute("CREATE INDEX IF NOT EXISTS saves_checked ON saves(checked)")
            self._expire(db)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        # Deleted text must not remain in free pages; use rollback journals,
        # not a long-lived WAL containing superseded snapshots.
        db.execute("PRAGMA secure_delete=ON")
        db.execute("PRAGMA journal_mode=DELETE")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _expire(self, db):
        rows = db.execute("SELECT account,name,payload FROM saves WHERE stale=0 AND checked<=?", (time.time() - TTL,)).fetchall()
        for row in rows:
            old = json.loads(row["payload"])
            tombstone = {"name": row["name"], "kind": old.get("kind"), "stale": True,
                         "remote_saved": old.get("remote_saved"), "needs_refresh": True, "read": bool(old.get("read"))}
            db.execute("UPDATE saves SET payload=?,search_text='',title_text='',context_text='',stale=1 WHERE account=? AND name=?",
                       (_json(tombstone), row["account"], row["name"]))
        return len(rows)

    def _row(self, db, name):
        return db.execute("SELECT * FROM saves WHERE account=? AND name=?", (self.account, name)).fetchone()

    def _write(self, db, record, checked, first_saved):
        searchable = "\n".join(str(record.get(key) or "") for key in
                               ("title", "body", "context", "summary", "notes", "author", "subreddit", "url", "permalink", "parent_id", "link_id"))
        searchable += "\n" + " ".join(record.get("tags") or [])
        db.execute("""INSERT INTO saves VALUES (?,?,?,?,?,?,?,?,0)
            ON CONFLICT(account,name) DO UPDATE SET payload=excluded.payload,
            search_text=excluded.search_text,title_text=excluded.title_text,
            context_text=excluded.context_text,checked=excluded.checked,stale=0""",
            (self.account, record["name"], _json(record), searchable.casefold(),
             record.get("title", "").casefold(),
             (record.get("summary", "") + "\n" + record.get("context", "")).casefold(),
             checked, first_saved))

    def upsert(self, child, remote_saved=None):
        data = child.get("data") or {}
        name = client.normalize_fullname(data.get("name") or "")
        kind = child.get("kind")
        if kind not in {"t1", "t3"} or not name.startswith(kind + "_"):
            raise client.RedditError("Library accepts only Reddit posts and comments")
        body = data.get("selftext" if kind == "t3" else "body") or ""
        unavailable = (body.strip() in {"[deleted]", "[removed]"} or data.get("removed_by_category")
                       or data.get("author") in {None, "[deleted]"})
        if unavailable:
            if data.get("author") in {None, "[deleted]"}:
                with self.connection() as db:
                    authors = db.execute("SELECT json_extract(payload,'$.author') FROM saves WHERE name=?", (name,)).fetchall()
                    for author in authors:
                        if author[0]:
                            db.execute("DELETE FROM saves WHERE json_extract(payload,'$.author')=?", (author[0],))
            self.remove(name, all_accounts=True)
            return {"name": name, "removed": True, "reason": "source unavailable or author deleted"}
        snapshot = {"name": name, "kind": kind, "title": str(data.get("title") or "")[:1000],
                    "body": str(body)[:MAX_BODY], "body_truncated": len(body) > MAX_BODY,
                    "author": str(data.get("author") or ""), "subreddit": str(data.get("subreddit") or ""),
                    "permalink": str(data.get("permalink") or ""), "url": str(data.get("url") or ""),
                    "parent_id": data.get("parent_id"), "link_id": data.get("link_id"),
                    "created_utc": data.get("created_utc"), "score": data.get("score")}
        # Score changes do not make a source summary obsolete.
        content_hash = hashlib.sha256(_json({k: v for k, v in snapshot.items() if k != "score"}).encode()).hexdigest()
        now = time.time()
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, name)
            old = json.loads(row["payload"]) if row else {}
            same = old.get("content_hash") == content_hash
            record = dict(snapshot, content_hash=content_hash, stale=False,
                          summary_source="extractive", summary=client._clip(" ".join((snapshot["title"] + " " + snapshot["body"]).split()), 800),
                          context=(f"{kind} in r/{snapshot['subreddit']}" +
                                   (f"; thread {snapshot['link_id']}; parent {snapshot['parent_id']}" if kind == "t1" else "")),
                          tags=[], notes="", read=bool(old.get("read")), remote_saved=remote_saved if remote_saved is not None else data.get("saved", old.get("remote_saved")))
            if same:
                for key in ("summary", "summary_source", "context", "tags", "notes"):
                    record[key] = old.get(key, record[key])
            self._write(db, record, now, row["first_saved"] if row else now)
        return {"name": name, "stored": True, "summary_source": record["summary_source"], "source_changed": bool(old and not same)}

    def get(self, target):
        name = client.normalize_fullname(target)
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, name)
            if not row:
                raise client.RedditError("Item is not in this account's local library")
            result = json.loads(row["payload"])
            result.update(account=self.account, first_saved=row["first_saved"], checked_at=row["checked"], expires_at=row["checked"] + TTL)
            return result

    def annotate(self, target, summary=None, context=None, notes=None, tags=None, expected_hash=None):
        name = client.normalize_fullname(target)
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, name)
            if not row or row["stale"]:
                raise client.RedditError("Capture or refresh the item before annotating it")
            record = json.loads(row["payload"])
            if expected_hash and record.get("content_hash") != expected_hash:
                raise client.RedditError("Source changed since it was read; fetch the current source before annotating")
            for key, value in (("summary", summary), ("context", context), ("notes", notes)):
                if value is not None:
                    if not isinstance(value, str) or len(value) > 12000:
                        raise client.RedditError(f"{key} must be text of at most 12000 characters")
                    record[key] = value
            if summary is not None:
                record["summary_source"] = "agent_or_user"
            if tags is not None:
                if not isinstance(tags, list) or len(tags) > 50 or any(not isinstance(t, str) or len(t) > 100 for t in tags):
                    raise client.RedditError("Supply at most 50 text tags, each at most 100 characters")
                record["tags"] = sorted({t.strip().casefold() for t in tags if t.strip()})
            # Annotation must never extend the source's retention window.
            self._write(db, record, row["checked"], row["first_saved"])
        return {"name": name, "annotated": True, "expires_at": row["checked"] + TTL}

    def remove(self, target, all_accounts=False):
        name = client.normalize_fullname(target)
        with self.connection() as db:
            sql, values = "DELETE FROM saves WHERE name=?", [name]
            if not all_accounts:
                sql += " AND account=?"
                values.append(self.account)
            removed = db.execute(sql, values).rowcount
        return {"name": name, "removed": removed}

    def mark_saved(self, target, saved):
        name = client.normalize_fullname(target)
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, name)
            if row:
                record = json.loads(row["payload"])
                record["remote_saved"] = bool(saved)
                # JSON-only update also works for expired bookmark tombstones.
                db.execute("UPDATE saves SET payload=? WHERE account=? AND name=?", (_json(record), self.account, name))

    def search(self, query="", limit=25, offset=0, subreddit="", author="", tag="", kind="", include_stale=False, summary_source="", read=None):
        terms = _terms(query)
        limit, offset = max(1, min(int(limit), 100)), max(0, int(offset))
        where, args = ["account=?"], [self.account]
        if not include_stale:
            where.append("stale=0")
        for key, value in (("subreddit", subreddit.removeprefix("r/")), ("author", author.removeprefix("u/")), ("kind", kind)):
            if value:
                where.append(f"lower(json_extract(payload,'$.{key}'))=?")
                args.append(value.casefold())
        if tag:
            where.append("EXISTS (SELECT 1 FROM json_each(json_extract(payload,'$.tags')) WHERE value=?)")
            args.append(tag.casefold())
        if summary_source:
            if summary_source not in {"extractive", "agent_or_user"}:
                raise client.RedditError("Unknown summary source")
            where.append("json_extract(payload,'$.summary_source')=?")
            args.append(summary_source)
        if read is not None:
            where.append("coalesce(json_extract(payload,'$.read'),0)=?")
            args.append(int(bool(read)))
        rank, rank_args = [], []
        for term in terms:
            excluded = term.startswith("-") and len(term) > 1
            needle = term[1:] if excluded else term
            where.append("instr(search_text,?)" + ("=0" if excluded else ">0"))
            args.append(needle)
            if not excluded:
                rank.extend(["(instr(title_text,?)>0)*5", "(instr(context_text,?)>0)*3"])
                rank_args.extend([needle, needle])
        predicate = " AND ".join(where)
        with self.connection() as db:
            self._expire(db)
            total = db.execute("SELECT count(*) FROM saves WHERE " + predicate, args).fetchone()[0]
            rows = db.execute("SELECT *, " + ("+".join(rank) or "0") + " AS rank FROM saves WHERE " + predicate +
                              " ORDER BY rank DESC,first_saved DESC,name LIMIT ? OFFSET ?", rank_args + args + [limit, offset]).fetchall()
        items = []
        for row in rows:
            record = json.loads(row["payload"])
            record["body"] = client._clip(record.get("body", ""), 700)
            record.update(checked_at=row["checked"], rank=row["rank"])
            items.append(record)
        return {"account": self.account, "count": len(items), "total": total, "items": items,
                "next_offset": offset + len(items) if offset + len(items) < total else None,
                "search": "literal AND terms; quoted phrases; -term excludes; Unicode casefold"}

    def stats(self):
        with self.connection() as db:
            expired = self._expire(db)
            rows = db.execute("SELECT stale,count(*) AS n FROM saves WHERE account=? GROUP BY stale", (self.account,)).fetchall()
        counts = {row["stale"]: row["n"] for row in rows}
        return {"account": self.account, "database": str(self.path), "fresh": counts.get(0, 0),
                "stale": counts.get(1, 0), "expired_now": expired, "snapshot_ttl_hours": 48,
                "maintenance": "Expiry runs on access and every minute while the plugin is loaded. Stopped Hermes cannot run cleanup."}

    def mark_read(self, target, read=True):
        name = client.normalize_fullname(target)
        with self.connection() as db:
            self._expire(db)
            row = self._row(db, name)
            if not row:
                raise client.RedditError("Item is not in the local library")
            record = json.loads(row["payload"])
            record["read"] = bool(read)
            db.execute("UPDATE saves SET payload=? WHERE account=? AND name=?", (_json(record), self.account, name))
        return {"name": name, "read": bool(read)}

    def export_bookmarks(self):
        with self.connection() as db:
            self._expire(db)
            rows = db.execute("SELECT name FROM saves WHERE account=? ORDER BY name", (self.account,)).fetchall()
        return {"format": "hermes-reddit-bookmarks", "version": 1, "items": [{"name": r["name"]} for r in rows]}

    def import_bookmarks(self, payload):
        if not isinstance(payload, dict) or payload.get("format") != "hermes-reddit-bookmarks" or payload.get("version") != 1:
            raise client.RedditError("Unsupported bookmark format")
        items = payload.get("items")
        if not isinstance(items, list) or len(items) > 10000:
            raise client.RedditError("Import supports at most 10000 bookmark identifiers")
        names = [client.normalize_fullname(item.get("name", "")) for item in items if isinstance(item, dict)]
        if len(names) != len(items):
            raise client.RedditError("Every bookmark needs a valid fullname")
        added = 0
        with self.connection() as db:
            for name in dict.fromkeys(names):
                record = {"name": name, "kind": name[:2], "stale": True, "needs_refresh": True}
                added += db.execute("INSERT OR IGNORE INTO saves VALUES (?,?,?,'','','',?,?,1)", (self.account, name, _json(record), 0, time.time())).rowcount
        return {"imported": added, "supplied": len(names), "requires_refresh": True}

    def names(self, limit=100, offset=0):
        with self.connection() as db:
            self._expire(db)
            rows = db.execute("SELECT name FROM saves WHERE account=? ORDER BY checked,name LIMIT ? OFFSET ?",
                              (self.account, max(1, min(int(limit), 100)), max(0, int(offset)))).fetchall()
        return [row["name"] for row in rows]


def sync_saved(session, library, pages=1, after=""):
    username = account_key(session.require_account())
    if username != library.account:
        raise client.RedditError("Sync account must match the logged-in Reddit account")
    cursor, stored, removed, seen = after, 0, 0, set()
    for _ in range(max(1, min(int(pages), 10))):
        payload = session.account_listing("saved", limit=100, after=cursor, raw=True)
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("children"), list):
            raise client.RedditError("Unexpected saved-list response; existing local records were preserved")
        for child in data["children"]:
            if child.get("kind") in {"t1", "t3"}:
                result = library.upsert(child, remote_saved=True)
                stored += int(result.get("stored", False))
                removed += int(result.get("removed", False))
        next_cursor = data.get("after") or ""
        if next_cursor and (next_cursor == cursor or next_cursor in seen):
            raise client.RedditError("Reddit repeated a saved-list cursor; sync stopped")
        seen.add(next_cursor)
        cursor = next_cursor
        if not cursor:
            break
    return {"stored": stored, "removed": removed, "after": cursor or None, "has_more": bool(cursor),
            "account": library.account, "coverage": "Only returned listing pages; not a complete account export. Missing items are not treated as unsaved."}


def refresh(session, library, names):
    if not names:
        return {"checked": 0, "removed": 0}
    payload = session.info(names)
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("children"), list):
        raise client.RedditError("Unexpected info response; no local items were removed")
    found = {c.get("data", {}).get("name"): c for c in data["children"]}
    removed = 0
    for name in names:
        if name not in found:
            # Unavailable may mean deleted, private, or no longer accessible.
            library.remove(name, all_accounts=True)
            removed += 1
        else:
            removed += int(library.upsert(found[name]).get("removed", False))
    return {"checked": len(names), "removed": removed}
