"""Named Skills/Tools/Plugins presets, shared by /preset and the Desktop page.

The JSON store is the single source of truth: the slash command and the
Settings ▸ Plugins page read and write the same file, so a preset saved in chat
shows up in the page and the other way round.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._'-]{0,59}$")
KINDS = ("skills", "tools", "plugins")
USAGE = (
    "Usage:\n"
    "  /preset save skills|tools|plugins <name>\n"
    "  /preset skills|tools|plugins <name>"
)


def hermes_home() -> Path:
    """The active profile's Hermes home, resolved per call."""
    try:
        from hermes_constants import get_hermes_home

        return Path(get_hermes_home())
    except Exception:
        env = os.environ.get("HERMES_HOME")
        if env:
            return Path(env)
        local = os.environ.get("LOCALAPPDATA")
        if local:
            win = Path(local) / "hermes"
            if win.exists():
                return win
        return Path.home() / ".hermes"


def store_path() -> Path:
    return hermes_home() / "better-capabilities-presets.json"


def pending_path() -> Path:
    return hermes_home() / "better-capabilities-pending.json"


def empty_store() -> dict[str, Any]:
    return {"skills": {}, "tools": {}, "plugins": {}}


def load_store() -> dict[str, Any]:
    path = store_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_store()
    if not isinstance(raw, dict):
        return empty_store()
    store = empty_store()
    for kind in KINDS:
        value = raw.get(kind)
        store[kind] = value if isinstance(value, dict) else {}
    return store


def save_store(store: dict[str, Any]) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(store, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def write_pending(kind: str, name: str) -> None:
    path = pending_path()
    path.write_text(json.dumps({"kind": kind, "name": name}), encoding="utf-8")


def read_pending() -> dict[str, str] | None:
    path = pending_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind") or "")
    name = str(raw.get("name") or "")
    if kind not in KINDS or not name:
        return None
    return {"kind": kind, "name": name}


def clear_pending() -> None:
    try:
        pending_path().unlink()
    except OSError:
        pass


def parse_command(raw_args: str) -> dict[str, str]:
    tokens = (raw_args or "").strip().split()
    if not tokens:
        return {"error": USAGE}
    if tokens[0].lower() == "save":
        if len(tokens) < 3:
            return {"error": USAGE}
        kind = tokens[1].lower()
        name = " ".join(tokens[2:]).strip()
        action = "save"
    else:
        if len(tokens) < 2:
            return {"error": USAGE}
        kind = tokens[0].lower()
        name = " ".join(tokens[1:]).strip()
        action = "apply"
    if kind not in KINDS:
        return {"error": "Kind must be skills, tools, or plugins.\n" + USAGE}
    if not PRESET_NAME_RE.match(name):
        return {
            "error": (
                "Name is not valid. Use letters, numbers, spaces, or hyphens. "
                "Start with a letter or number."
            )
        }
    return {"action": action, "kind": kind, "name": name}


def write_preset(kind: str, name: str, payload: dict[str, Any]) -> None:
    store = load_store()
    bucket = store.get(kind)
    if not isinstance(bucket, dict):
        bucket = {}
        store[kind] = bucket
    bucket[name] = payload
    order = [item for item in bucket.get("_order", []) if item and item != "_order"]
    if name not in order:
        order.append(name)
    bucket["_order"] = order
    store[kind] = bucket
    save_store(store)


def read_preset(kind: str, name: str) -> dict[str, Any] | None:
    bucket = load_store().get(kind) or {}
    payload = bucket.get(name)
    return payload if isinstance(payload, dict) else None


def snapshot_skills() -> dict[str, Any]:
    from hermes_cli.config import load_config
    from hermes_cli.skills_config import get_disabled_skills
    from tools.skills_tool import find_all_skills

    config = load_config()
    disabled = get_disabled_skills(config)
    enabled: dict[str, bool] = {}
    for row in find_all_skills(skip_disabled=True):
        name = row.get("name")
        if name:
            enabled[str(name)] = str(name) not in disabled
    return {"enabled": enabled}


def apply_skills(payload: dict[str, Any]) -> int:
    from hermes_cli.config import load_config
    from hermes_cli.skills_config import get_disabled_skills, save_disabled_skills
    from hermes_cli.web_routers._common import config_write_scope

    enabled = (payload or {}).get("enabled") or {}
    if not isinstance(enabled, dict):
        return 0
    changed = 0
    with config_write_scope(None):
        config = load_config()
        disabled = get_disabled_skills(config)
        for name, on in enabled.items():
            key = str(name)
            want = bool(on)
            if want and key in disabled:
                disabled.discard(key)
                changed += 1
            elif not want and key not in disabled:
                disabled.add(key)
                changed += 1
        save_disabled_skills(config, disabled)
    return changed


def _toolset_rows() -> list[str]:
    from hermes_cli.tools_config import _get_effective_configurable_toolsets

    return [name for name, _label, _desc in _get_effective_configurable_toolsets()]


def snapshot_tools() -> dict[str, Any]:
    """Read every configurable toolset's enabled state the way the Toolsets tab does."""
    from hermes_cli.config import load_config
    from hermes_cli.tools_config import (
        _CONFIG_ONLY_TOOLSETS,
        _get_platform_tools,
        _toolset_configuration_platform,
    )

    config = load_config()
    enabled: dict[str, bool] = {}
    for name in _toolset_rows():
        try:
            if name in _CONFIG_ONLY_TOOLSETS:
                section = config.get(name)
                enabled[name] = bool(isinstance(section, dict) and section.get("enabled"))
                continue
            platform = _toolset_configuration_platform(name)
            current = set(
                _get_platform_tools(config, platform, include_default_mcp_servers=False)
            )
            enabled[name] = name in current
        except Exception:
            continue
    return {"enabled": enabled}


def apply_tools(payload: dict[str, Any]) -> int:
    """Write the toolset switches through the same helpers the Toolsets tab uses."""
    from hermes_cli.config import load_config, save_config
    from hermes_cli.tools_config import (
        _CONFIG_ONLY_TOOLSETS,
        _get_platform_tools,
        _save_platform_tools,
        _toolset_configuration_platform,
    )
    from hermes_cli.web_routers._common import config_write_scope

    enabled = (payload or {}).get("enabled") or {}
    if not isinstance(enabled, dict):
        return 0
    known = set(_toolset_rows())
    changed = 0
    with config_write_scope(None):
        config = load_config()
        for name, on in enabled.items():
            key = str(name)
            if key not in known:
                continue
            want = bool(on)
            try:
                if key in _CONFIG_ONLY_TOOLSETS:
                    section = config.get(key)
                    if not isinstance(section, dict):
                        section = {}
                        config[key] = section
                    if bool(section.get("enabled")) != want:
                        section["enabled"] = want
                        changed += 1
                        save_config(config)
                    continue
                platform = _toolset_configuration_platform(key)
                current = set(
                    _get_platform_tools(config, platform, include_default_mcp_servers=False)
                )
                if want and key not in current:
                    current.add(key)
                    _save_platform_tools(config, platform, current)
                    changed += 1
                elif not want and key in current:
                    current.discard(key)
                    _save_platform_tools(config, platform, current)
                    changed += 1
            except Exception:
                continue
    return changed


def _profile_names() -> list[str]:
    names = ["default"]
    try:
        from hermes_cli.profiles import list_profiles

        for row in list_profiles():
            name = getattr(row, "name", None) or (row.get("name") if isinstance(row, dict) else None)
            if name and str(name) not in names:
                names.append(str(name))
    except Exception:
        pass
    return names


def _plugin_keys() -> list[str]:
    keys: list[str] = []
    try:
        from hermes_cli.plugins import _ensure_plugins_discovered

        for row in _ensure_plugins_discovered().list_plugins():
            key = row.get("key") or row.get("name")
            if key and key not in keys:
                keys.append(str(key))
    except Exception:
        pass
    plugins_root = hermes_home() / "plugins"
    if plugins_root.is_dir():
        for child in plugins_root.iterdir():
            try:
                if not child.is_dir():
                    continue
                if (child / "plugin.yaml").is_file() or (child / "plugin.yml").is_file():
                    if child.name not in keys:
                        keys.append(child.name)
            except OSError:
                continue
    return keys


def snapshot_agent_for_profile(profile: str) -> dict[str, bool]:
    from hermes_cli.plugins_discovery import _get_disabled_plugins, _get_enabled_plugins
    from hermes_cli.web_server_profiles import _profile_scope

    scope = None if profile == "default" else profile
    with _profile_scope(scope):
        disabled = _get_disabled_plugins()
        enabled_set = _get_enabled_plugins()
    agent: dict[str, bool] = {}
    for key in _plugin_keys():
        if key in disabled:
            agent[key] = False
        elif enabled_set is None:
            agent[key] = False
        else:
            agent[key] = key in enabled_set
    return agent


def snapshot_plugins() -> dict[str, Any]:
    """Agent-plugin switches for every profile that exists at save time.

    Desktop-plugin switches are deliberately absent: the Desktop keeps them in
    renderer-local storage behind a read-only plugin door, so a plugin cannot set
    them. The page says so instead of pretending to restore them.
    """
    agent_by_profile = {}
    for profile in _profile_names():
        try:
            agent_by_profile[profile] = snapshot_agent_for_profile(profile)
        except Exception:
            continue
    current = agent_by_profile.get("default") or next(iter(agent_by_profile.values()), {})
    return {"agent": current, "agentByProfile": agent_by_profile}


def apply_plugins(payload: dict[str, Any]) -> int:
    from hermes_cli.plugins_cmd import dashboard_set_agent_plugin_enabled
    from hermes_cli.web_routers._common import config_write_scope

    agent = (payload or {}).get("agent") or {}
    by_profile = (payload or {}).get("agentByProfile")
    maps = by_profile if isinstance(by_profile, dict) else {"default": agent}
    changed = 0
    for profile, mapping in maps.items():
        if not isinstance(mapping, dict):
            continue
        scope = None if profile == "default" else str(profile)
        with config_write_scope(scope):
            for key, on in mapping.items():
                try:
                    result = dashboard_set_agent_plugin_enabled(str(key), enabled=bool(on))
                except Exception:
                    continue
                if result.get("ok") and not result.get("unchanged"):
                    changed += 1
    return changed


SNAPSHOTTERS = {"skills": snapshot_skills, "tools": snapshot_tools, "plugins": snapshot_plugins}
APPLIERS = {"skills": apply_skills, "tools": apply_tools, "plugins": apply_plugins}


def handle_preset_command(raw_args: str) -> str:
    parsed = parse_command(raw_args)
    if parsed.get("error"):
        return parsed["error"]
    kind = parsed["kind"]
    name = parsed["name"]
    if parsed["action"] == "save":
        try:
            payload = SNAPSHOTTERS[kind]()
        except Exception as exc:  # a broken snapshot must not save an empty preset
            return f"Could not read the current {kind} state: {exc}"
        if not payload:
            return f"Could not read the current {kind} state."
        write_preset(kind, name, payload)
        return f"Saved {kind} preset '{name}'."
    payload = read_preset(kind, name)
    if payload is None:
        return f"No {kind} preset named '{name}'."
    changed = APPLIERS[kind](payload)
    if kind == "plugins":
        write_pending(kind, name)
    return f"Applied {kind} preset '{name}' ({changed} switch{'es' if changed != 1 else ''} changed)."
