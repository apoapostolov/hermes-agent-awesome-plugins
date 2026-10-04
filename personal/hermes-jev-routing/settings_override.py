"""Plugin settings overwrite the JSON file only for keys that are actually set."""

from __future__ import annotations

from dataclasses import replace
from typing import Mapping

_SENTINEL = object()


def present_settings(ctx) -> dict:
    """Read plugin settings. A missing key is absent, so a schema default cannot clobber the file."""
    keys = (
        "enabled",
        "confidence_threshold",
        "min_prompt_chars",
        "timeout_ms",
        "history_turns",
        "stickiness",
        "confirm_on_timeout",
        "confirm_tiers",
        "quota_on_unknown",
        "quota_enabled",
        "cache_aware",
        "free_enabled",
        "free_policy",
    )
    found = {}
    for key in keys:
        try:
            value = ctx.get_config(key, _SENTINEL)
        except Exception:
            continue
        if value is _SENTINEL or value is None or value == "":
            continue
        found[key] = value
    return found


def apply_setting_overrides(config, jev_settings, values: Mapping):
    if not values:
        return config, jev_settings
    if "enabled" in values:
        config.enabled = bool(values["enabled"])
    if "confidence_threshold" in values:
        config.confidence_threshold = float(values["confidence_threshold"])
    if "min_prompt_chars" in values:
        config.min_prompt_chars = int(values["min_prompt_chars"])
    if "stickiness" in values:
        config.stickiness = bool(values["stickiness"])
    if "confirm_on_timeout" in values:
        name = str(values["confirm_on_timeout"]).strip().lower()
        if name in {"accept", "reject"}:
            config.confirm_on_timeout = name
    if "confirm_tiers" in values:
        config.confirm_tiers = tuple(
            part.strip() for part in str(values["confirm_tiers"]).split(",") if part.strip()
        )
    if "quota_on_unknown" in values:
        policy = str(values["quota_on_unknown"]).strip().lower()
        if policy in {"use", "skip"}:
            floors = dict(config.quota_on_unknown)
            floors["openai-codex"] = policy
            config.quota_on_unknown = floors
    if "quota_enabled" in values:
        enabled = dict(config.quota_enabled)
        enabled["openai-codex"] = bool(values["quota_enabled"])
        config.quota_enabled = enabled
    if "cache_aware" in values:
        config.cache = replace(config.cache, aware=bool(values["cache_aware"]))
    if "free_enabled" in values or "free_policy" in values:
        enabled = bool(values["free_enabled"]) if "free_enabled" in values else config.free.enabled
        policy = str(values.get("free_policy") or config.free.policy)
        if policy not in {"prefer", "fallback-only"}:
            policy = config.free.policy
        config.free = replace(config.free, enabled=enabled, policy=policy)
    if "timeout_ms" in values:
        jev_settings.timeout_ms = int(values["timeout_ms"])
    if "history_turns" in values:
        jev_settings.history_turns = int(values["history_turns"])
    return config, jev_settings
