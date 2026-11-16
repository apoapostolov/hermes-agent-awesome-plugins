"""Catalog Redesign backend — the public plugin catalog, served from this host.

The renderer cannot read the published catalog feed on every mount: it is a
5 MB snapshot and the page is opened often. This half fetches it once, projects
only the fields the page draws, and keeps the result in memory plus a disk copy
so an offline window still paints the last good catalog.

Routes (mounted at ``/api/plugins/hermes-catalog-redesign/``):

* ``GET /health`` — version, cache age and row count, for a one-line probe.
* ``GET /catalog/plugins`` — the projected plugin catalog; ``?refresh=1``
  bypasses the TTL (the page's Refresh action).
* ``GET /icons`` — plugin artwork found in each installed plugin folder, as data
  URLs, so a row can show the plugin's own image instead of initials.
* ``POST /servers/toggle`` — enable or disable one configured MCP server, the
  same config write the app's own Connectors tab performs. MCP exposes no
  JSON-RPC toggle, so the renderer needs this door to put a switch on a row.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

CATALOG_URL = "https://hermes-agent.nousresearch.com/docs/api/plugins.json"
CATALOG_TTL = 6 * 3600
FETCH_TIMEOUT = 90
CACHE_VERSION = 1

SLUG_RE = re.compile(r"[^a-z0-9]+")
SCREENSHOT_LIMIT = 4

_state: dict[str, Any] = {"at": 0.0, "payload": None}
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


def cache_file() -> Path:
    return hermes_home() / "cache" / "hermes-catalog-redesign" / "plugins.json"


def slug(value: Any) -> str:
    return SLUG_RE.sub("-", str(value or "").strip().lower()).strip("-")


def _strings(value: Any, limit: int | None = None) -> list[str]:
    rows = [v for v in value if isinstance(v, str) and v] if isinstance(value, list) else []
    return rows[:limit] if limit else rows


def project(row: dict[str, Any]) -> dict[str, Any]:
    """One catalog entry in the shape the page draws, and nothing else."""
    name = str(row.get("name") or "").strip()
    caps = row.get("capabilities") if isinstance(row.get("capabilities"), dict) else {}
    images = [url for url in _strings(row.get("screenshots")) if url.startswith("https://")]

    return {
        "key": slug(name),
        "name": name,
        "slug": slug(name),
        "description": str(row.get("description") or "").strip(),
        "category": str(row.get("category") or "general"),
        "tier": str(row.get("tier") or "community"),
        "maintainer": str(row.get("maintainer") or ""),
        "maintainerSlug": str(row.get("maintainerSlug") or ""),
        "version": str(row.get("version") or ""),
        "hero": str(row.get("image") or "") if str(row.get("image") or "").startswith("https://") else "",
        "screenshots": images[:SCREENSHOT_LIMIT],
        "stars": row.get("stars") if isinstance(row.get("stars"), int) else None,
        "requiresHermes": str(row.get("requiresHermes") or ""),
        "platforms": _strings(row.get("platforms")),
        "tools": _strings(caps.get("providesTools")),
        "hooks": _strings(caps.get("providesHooks")),
        "middleware": _strings(caps.get("providesMiddleware")),
        "requiresEnv": _strings(caps.get("requiresEnv")),
        "installCommand": str(row.get("installCommand") or ""),
        "docsUrl": str(row.get("docsUrl") or ""),
        "repo": str(row.get("repo") or ""),
        "sha": str(row.get("sha") or ""),
        "shaShort": str(row.get("shaShort") or ""),
        "addedAt": str(row.get("addedAt") or ""),
        "updatedAt": str(row.get("updatedAt") or ""),
        "featured": row.get("featured") if isinstance(row.get("featured"), int) else None,
    }


def payload_for(rows: list[dict[str, Any]], fetched_at: str, cached: bool) -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "fetched_at": fetched_at,
        "cached": cached,
        "count": len(rows),
        "rows": rows,
    }


def read_disk() -> dict[str, Any] | None:
    try:
        raw = json.loads(cache_file().read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION or not isinstance(raw.get("rows"), list):
        return None
    return raw


def write_disk(payload: dict[str, Any]) -> None:
    path = cache_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        # A cache we cannot write costs one network fetch, never the page.
        pass


def fetch_catalog() -> dict[str, Any]:
    request = urllib.request.Request(
        CATALOG_URL,
        headers={"Accept": "application/json", "User-Agent": "hermes-catalog-redesign/1"},
    )
    with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not isinstance(data, list):
        raise ValueError("catalog feed is not a list")

    rows = [project(row) for row in data if isinstance(row, dict) and str(row.get("name") or "").strip()]
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = payload_for(rows, fetched_at, False)
    write_disk(payload)

    return payload


def current_payload(force: bool = False) -> dict[str, Any]:
    """Memory → TTL → disk → network, in that order."""
    now = time.time()

    if not force and _state["payload"] is not None and now - _state["at"] < CATALOG_TTL:
        return _state["payload"]

    try:
        payload = fetch_catalog()
        _state.update({"at": now, "payload": payload})
        return payload
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
        disk = read_disk()
        if disk is not None:
            disk = dict(disk)
            disk["cached"] = True
            disk["error"] = f"{type(exc).__name__}: {exc}"
            # Keep serving the snapshot; retry the network on the next TTL window.
            _state.update({"at": now, "payload": disk})
            return disk
        raise


@router.get("/health")
def health() -> dict[str, Any]:
    payload = _state["payload"]
    return {
        "ok": True,
        "version": CACHE_VERSION,
        "rows": payload["count"] if payload else 0,
        "fetched_at": payload["fetched_at"] if payload else None,
        "cache_file": str(cache_file()),
    }


@router.get("/catalog/plugins")
def catalog_plugins(refresh: int = 0) -> dict[str, Any]:
    return current_payload(force=bool(refresh))


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
