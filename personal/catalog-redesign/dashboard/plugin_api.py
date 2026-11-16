"""Catalog Redesign backend — the public plugin catalog, served from this host.

The renderer cannot read the published catalog feed on every mount: it is a
5 MB snapshot and the page is opened often. This half fetches it once, projects
only the fields the page draws, and keeps the result in memory plus a disk copy
so an offline window still paints the last good catalog.

Routes (mounted at ``/api/plugins/hermes-catalog-redesign/``):

* ``GET /health`` — version, cache age and row count, for a one-line probe.
* ``GET /catalog/plugins`` and ``GET /catalog/skills`` — the two published
  catalogs the native Capabilities page reads, projected to the fields the page
  draws and served one page at a time (``?page=1&size=150&q=``). ``?refresh=1``
  bypasses the TTL (the page's Refresh action).
* ``GET /icons`` — plugin artwork found in each installed plugin folder, as data
  URLs, so a row can show the plugin's own image instead of initials.
* ``POST /servers/toggle`` — enable or disable one configured MCP server, the
  same config write the app's own Connectors tab performs. MCP exposes no
  JSON-RPC toggle, so the renderer needs this door to put a switch on a row.
"""

from __future__ import annotations

import base64
import gzip
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# The same published snapshots the native Capabilities page fetches, on the
# static docs host: the public domain redirects there without CORS headers, and
# the GitHub API splits one catalog across a thousand paginated calls.
CATALOG_BASE = "https://nousresearch.github.io/hermes-agent/docs/api"
CATALOG_FILES = {"plugins": "plugins.json", "skills": "skills.json"}
CATALOG_TTL = 30 * 60
FETCH_TIMEOUT = 120
CACHE_VERSION = 2

DEFAULT_PAGE_SIZE = 150
MAX_PAGE_SIZE = 500
DESCRIPTION_CHARS = 200
TAG_LIMIT = 4

SLUG_RE = re.compile(r"[^a-z0-9]+")
SCREENSHOT_LIMIT = 4

# kind -> {"rows": [...], "at": float, "source": str, "error": str|None}
_snapshots: dict[str, dict[str, Any]] = {}
_snapshot_lock = threading.Lock()
_icons: dict[str, Any] = {"at": 0.0, "rows": []}

ICONS_TTL = 900
ICON_MAX_BYTES = 300_000
ICON_NAMES = ("icon", "logo", "banner", "hero", "cover", "thumbnail", "preview", "art")
ICON_DIRS = ("", "assets", "static", "images", "img", "docs", "media", "desktop")
ICON_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
}


def hermes_home() -> Path:
    """The active profile's Hermes home, resolved from the environment."""
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        win = Path(local) / "hermes"
        if win.exists():
            return win
    return Path.home() / ".hermes"


def cache_dir() -> Path:
    return hermes_home() / "cache" / "hermes-catalog-redesign"


def snapshot_file(kind: str) -> Path:
    return cache_dir() / f"{kind}.json"


def slug(value: Any) -> str:
    return SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")


def _strings(value: Any, limit: int | None = None) -> list[str]:
    rows = [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []
    return rows[:limit] if limit else rows


def _text(value: Any, limit: int = 0) -> str:
    text = str(value or "").strip()
    if limit and len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def _search_key(*parts: Any) -> str:
    """One lowercase haystack per row: a query is then one substring test."""
    return " ".join(_text(part).lower() for part in parts if _text(part))


def project_plugin(row: dict[str, Any]) -> dict[str, Any]:
    """One catalog entry in the shape the page draws, and nothing else."""
    name = str(row.get("name") or "").strip()
    caps = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
    images = [url for url in _strings(row.get("screenshots")) if url.startswith("https://")]
    category = _text(row.get("category")) or "general"
    description = _text(row.get("description"))

    return {
        "key": slug(name),
        "name": name,
        "slug": slug(name),
        "description": description,
        "category": category,
        "tier": _text(row.get("tier")) or "community",
        "maintainer": _text(row.get("maintainer")),
        "maintainerSlug": _text(row.get("maintainerSlug")),
        "version": _text(row.get("version")),
        "hero": _text(row.get("image")) if _text(row.get("image")).startswith("https://") else "",
        "screenshots": images[:SCREENSHOT_LIMIT],
        "stars": row.get("stars") if isinstance(row.get("stars"), int) else None,
        "requiresHermes": _text(row.get("requiresHermes")),
        "platforms": _strings(row.get("platforms")),
        "tools": _strings(caps.get("providesTools")),
        "hooks": _strings(caps.get("providesHooks")),
        "middleware": _strings(caps.get("providesMiddleware")),
        "requiresEnv": _strings(caps.get("requiresEnv")),
        "installCommand": _text(row.get("installCommand")),
        "docsUrl": _text(row.get("docsUrl")),
        "repo": _text(row.get("repo")),
        "sha": _text(row.get("sha")),
        "shaShort": _text(row.get("shaShort")),
        "addedAt": _text(row.get("addedAt")),
        "updatedAt": _text(row.get("updatedAt")),
        "featured": row.get("featured") if isinstance(row.get("featured"), int) else None,
        "s": _search_key(name, description, category, " ".join(_strings(caps.get("providesTools")))),
    }


def project_skill(row: dict[str, Any]) -> dict[str, Any]:
    """One skills snapshot row, trimmed to what a catalog row and panel read.

    The published snapshot holds 104k rows; keeping every field of every row in
    memory costs hundreds of megabytes, so the projection is the point.
    """
    name = _text(row.get("name"))
    category = _text(row.get("category")) or "uncategorized"
    description = _text(row.get("description"), DESCRIPTION_CHARS)
    tags = _strings(row.get("tags"), TAG_LIMIT)
    identifier = _text(row.get("identifier")) or name
    install_identifier = _text(row.get("installIdentifier")) or identifier

    return {
        "key": slug(name) or slug(identifier),
        "name": name,
        "description": description,
        "category": category,
        "categoryLabel": _text(row.get("categoryLabel")) or category.replace("-", " ").title(),
        "source": _text(row.get("source")) or "hub",
        "tags": tags,
        "identifier": identifier,
        "installIdentifier": install_identifier,
        "installCommand": _text(row.get("installCmd")),
        "docsPath": _text(row.get("docsPath")),
        "s": _search_key(name, description, category, " ".join(tags), identifier),
    }


def _project(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    return project_skill(row) if kind == "skills" else project_plugin(row)


def _read_disk_snapshot(kind: str) -> tuple[list[dict[str, Any]], float]:
    path = snapshot_file(kind)

    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return [], 0.0

    return (rows if isinstance(rows, list) else []), path.stat().st_mtime


def _write_disk_snapshot(kind: str, rows: list[dict[str, Any]]) -> None:
    path = snapshot_file(kind)

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        # A cache we cannot write costs one network fetch, never the page.
        pass


def _download(kind: str) -> list[dict[str, Any]]:
    """Fetch one published snapshot and project it, newest rows as they come."""
    url = f"{CATALOG_BASE}/{CATALOG_FILES[kind]}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "User-Agent": f"hermes-catalog-redesign/{CACHE_VERSION}",
        },
    )

    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        raw = response.read()
        encoding = str(response.headers.get("Content-Encoding") or "")

    # urllib does not negotiate compression itself: a gzip body arrives as bytes
    # that look like a JSON parse error rather than a transport detail.
    if encoding == "gzip" or raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)

    data = json.loads(raw.decode("utf-8"))

    if not isinstance(data, list):
        raise ValueError(f"{kind} catalog is not a list")

    rows = [_project(kind, row) for row in data if isinstance(row, dict) and str(row.get("name") or "").strip()]

    if kind == "plugins":
        # The feed carries no order a reader can name, so rank it once here and
        # page a stable list: featured first, then stars, then name.
        rows.sort(key=lambda r: (-(r.get("featured") or 0), -(r.get("stars") or 0), r.get("name", "").lower()))

    return rows


def snapshot(kind: str, force: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Slim rows for one published catalog: memory -> disk TTL -> network.

    Returns the rows plus a small meta dict the route adds to the response, so a
    stale disk copy still paints and the page can say the network failed.
    """
    now = time.time()

    with _snapshot_lock:
        cached = _snapshots.get(kind)

        if cached and not force and now - cached["at"] < CATALOG_TTL:
            return cached["rows"], {"source": cached["source"], "fetched_at": cached["fetchedAt"], "error": cached["error"]}

        rows: list[dict[str, Any]] = []
        source = "network"
        error = None

        try:
            rows = _download(kind)
            _write_disk_snapshot(kind, rows)
        except Exception as exc:
            rows, mtime = _read_disk_snapshot(kind)

            if rows:
                source = "disk"
                error = f"{type(exc).__name__}: {exc}"
            else:
                raise

        fetched_at = (
            datetime.now(timezone.utc).isoformat(timespec="seconds")
            if source == "network"
            else datetime.fromtimestamp(_read_disk_snapshot(kind)[1] or now, timezone.utc).isoformat(timespec="seconds")
        )

        _snapshots[kind] = {"rows": rows, "at": now, "source": source, "fetchedAt": fetched_at, "error": error}

        return rows, {"source": source, "fetched_at": fetched_at, "error": error}


def paged(rows: list[dict[str, Any]], page: int, size: int, query: str) -> dict[str, Any]:
    """One page of a projected catalog, plus the totals the header counts."""
    size = max(1, min(int(size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    needle = str(query or "").strip().lower()
    matched = [row for row in rows if needle in row["s"]] if needle else rows
    total = len(matched)
    total_pages = max(1, (total + size - 1) // size)
    page = max(1, min(int(page or 1), total_pages))
    start = (page - 1) * size

    return {
        "rows": matched[start : start + size],
        "total": total,
        "page": page,
        "totalPages": total_pages,
        "size": size,
    }


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "version": CACHE_VERSION,
        "catalogs": {
            kind: {
                "rows": len(state["rows"]),
                "age_seconds": round(time.time() - state["at"]),
                "source": state["source"],
                "error": state["error"],
            }
            for kind, state in _snapshots.items()
        },
        "cache_dir": str(cache_dir()),
    }


@router.get("/catalog/plugins")
def catalog_plugins(page: int = 1, size: int = DEFAULT_PAGE_SIZE, q: str = "", refresh: int = 0) -> dict[str, Any]:
    rows, meta = snapshot("plugins", force=bool(refresh))
    return {**paged(rows, page, size, q), **meta}


@router.get("/catalog/skills")
def catalog_skills(page: int = 1, size: int = DEFAULT_PAGE_SIZE, q: str = "", refresh: int = 0) -> dict[str, Any]:
    rows, meta = snapshot("skills", force=bool(refresh))
    return {**paged(rows, page, size, q), **meta}


FRONTMATTER_RE = re.compile(r"^([A-Za-z][\w-]*):\s*(.*)$")


def _frontmatter(path: Path) -> dict[str, str]:
    """The handful of SKILL.md header fields an archive row shows."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    if not text.startswith("---"):
        return {}

    body = text.split("---", 2)[1] if text.count("---") >= 2 else ""
    fields: dict[str, str] = {}

    for line in body.splitlines():
        match = FRONTMATTER_RE.match(line.strip())

        if match:
            fields[match.group(1).lower()] = match.group(2).strip().strip('"').strip("'")

    return fields


@router.get("/skills/archive")
def skills_archive() -> dict[str, Any]:
    """Skills the curator moved to ``skills/.archive``, as rows the page can draw.

    Archiving is a directory move, not a registry entry, so the folder on disk is
    the only truth here: one subdirectory per archived skill, each carrying the
    SKILL.md it was archived with.
    """
    root = hermes_home() / "skills" / ".archive"
    rows: list[dict[str, Any]] = []

    if root.is_dir():
        for folder in sorted(root.iterdir(), key=lambda f: f.name.lower()):
            manifest = folder / "SKILL.md"

            if not folder.is_dir() or not manifest.exists():
                continue

            meta = _frontmatter(manifest)
            name = meta.get("name") or folder.name

            try:
                archived = datetime.fromtimestamp(manifest.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")
            except OSError:
                archived = ""

            rows.append(
                {
                    "key": slug(name) or slug(folder.name),
                    "name": name,
                    "description": _text(meta.get("description"), DESCRIPTION_CHARS),
                    "category": _text(meta.get("category")) or "archived",
                    "version": _text(meta.get("version")),
                    "archivedAt": archived,
                    "folder": folder.name,
                    "path": str(folder),
                }
            )

    return {"rows": rows, "total": len(rows), "root": str(root)}


class ToggleRequest(BaseModel):
    """One MCP server, by the name the config uses."""

    name: str
    enabled: bool
    profile: str | None = None


@router.post("/servers/toggle")
def servers_toggle(body: ToggleRequest) -> dict[str, Any]:
    """Flip ``enabled`` on a configured MCP server.

    This mirrors ``PUT /api/mcp/servers/{name}/enabled`` rather than inventing a
    write path: the same guarded config edit, the same refusal for a server a
    plugin provides, and the change lands for the next session or gateway cycle.
    """
    name = str(body.name or "").strip()

    if not name:
        raise HTTPException(status_code=400, detail="A server name is required")

    from hermes_cli.config import load_config, save_config
    from hermes_cli.web_routers._common import config_write_scope
    from tools.mcp_tool_common import write_mcp_server_enabled
    from tui_gateway.mcp_rpc_helpers import server_configs_with_sources

    with config_write_scope(body.profile):
        cfg = load_config()
        _servers, plugins = server_configs_with_sources(cfg.get("mcp_servers") or {})

        if name in plugins:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{name}' is provided by plugin '{plugins[name]}' and cannot be modified",
            )

        servers = cfg.get("mcp_servers")

        if not isinstance(servers, dict) or name not in servers:
            raise HTTPException(status_code=404, detail=f"Server '{name}' not found")

        if not isinstance(servers[name], dict):
            raise HTTPException(status_code=400, detail="Malformed server config")

        write_mcp_server_enabled(servers[name], bool(body.enabled))
        save_config(cfg)

    return {"ok": True, "name": name, "enabled": bool(body.enabled)}


def installed_plugin_dirs() -> list[tuple[str, str, Path]]:
    """Every installed plugin folder under the plugins directory.

    The manifests on disk are the list: a plugin is a directory carrying
    ``plugin.yaml``, at the top level or nested one folder deep, which is how
    the bundled packages are laid out.
    """
    root = hermes_home() / "plugins"
    found: list[tuple[str, str, Path]] = []

    if not root.is_dir():
        return found

    for manifest in sorted(root.rglob("plugin.yaml")):
        folder = manifest.parent
        relative = folder.relative_to(root)

        if any(part.startswith(".") or part in {"__pycache__", "node_modules"} for part in relative.parts[:-1]):
            continue

        name = folder.name

        try:
            text = manifest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        match = re.search(r"^name:\s*[\"']?([^\"'\n]+)", text, re.MULTILINE)

        if match:
            name = match.group(1).strip()

        found.append((name, folder.name, folder))

    return found


def _icon_data_url(folder: Path | None) -> str:
    """The plugin's own artwork as a data URL, smallest name first.

    A plugin that ships a logo in its folder has no catalog entry to borrow one
    from, so the row would otherwise fall back to two letters. Only a file the
    package already carries is used, nothing is fetched.
    """
    if folder is None or not folder.is_dir():
        return ""

    for sub in ICON_DIRS:
        base = folder / sub if sub else folder

        if not base.is_dir():
            continue

        for stem in ICON_NAMES:
            for ext, mime in ICON_MIME.items():
                candidate = base / f"{stem}{ext}"

                if not candidate.is_file():
                    continue

                try:
                    if candidate.stat().st_size > ICON_MAX_BYTES:
                        continue

                    return f"data:{mime};base64,{base64.b64encode(candidate.read_bytes()).decode('ascii')}"
                except OSError:
                    continue

    return ""


@router.get("/icons")
def plugin_icons(refresh: int = 0) -> dict[str, Any]:
    """Artwork for installed plugins, keyed by plugin name and registry key."""
    now = time.time()

    if not refresh and _icons["rows"] and now - _icons["at"] < ICONS_TTL:
        return {"rows": _icons["rows"], "cached": True}

    rows: list[dict[str, Any]] = []

    try:
        for name, key, folder in installed_plugin_dirs():
            data = _icon_data_url(folder)

            if data:
                rows.append({"name": name, "key": key, "data": data})
    except Exception as exc:  # a scan failure must not break the page
        return {"rows": [], "error": f"{type(exc).__name__}: {exc}"}

    _icons.update({"at": now, "rows": rows})

    return {"rows": rows, "cached": False}
