"""voice-gate (personal edition): a prose gate that learns one person's voice.

The public edition ships one set of rules. This edition ships the same rules
plus a place to put your own: a profile document listing the phrases you never
open with, the offers you never make, the words you refuse, and the thresholds
that match your writing. With no profile loaded it behaves exactly like the
public build.

Three tools let an agent drive the gate deliberately instead of waiting for the
turn to end: ``voice_gate_check`` reports findings on demand,
``voice_gate_profile`` shows what is loaded, and ``voice_gate_learn`` turns a
corpus of somebody's writing into a draft profile.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import profile as profiles
from . import rules
from . import vale

log = logging.getLogger(__name__)

PROSE_SUFFIXES = {".md", ".markdown", ".mdx"}
SAMPLE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".json"}
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
_SKIP_WORDS = {"off", "skip", "false", "no", "0"}
_MAX_SAMPLES = 400
_MAX_SAMPLE_BYTES = 2_000_000

_SKILL = Path(__file__).resolve().parent / "skills" / "voice-profile-builder" / "SKILL.md"
_SKILL_DESCRIPTION = "Build a voice-gate writing profile from a corpus of somebody's own writing."

_CTX: Any = None
_CACHE: Dict[str, Any] = {"target": None, "stamp": None, "profile": {}, "path": None, "issues": []}


def _home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))


def _current_profile() -> str:
    """The profile this process serves, or ``default`` for the install root."""
    try:
        import hermes_constants

        name = hermes_constants.profile_name_for_home(hermes_constants.get_hermes_home())
        if name:
            return str(name).strip().lower()
    except Exception:
        log.debug("voice-gate could not resolve its profile", exc_info=True)
    home = _home()
    if home.parent.name == "profiles":
        return home.name.strip().lower()
    return "default"


def _setting(key: str, default: Any) -> Any:
    if _CTX is None:
        return default
    try:
        value = _CTX.get_config(key, default)
        return default if value is None else value
    except Exception:
        return default


def _mode() -> str:
    raw = str(_setting("mode", "warn")).strip().lower()
    if raw in _SKIP_WORDS:
        return "skip"
    return raw if raw in ("warn", "improve") else "warn"


def _loaded(target: str) -> Tuple[Dict[str, Any], Optional[Path], List[str]]:
    """Active profile, cached on the file's mtime so an edit applies at once."""
    path = profiles.resolve(target) if target else None
    stamp = None
    if path is not None:
        try:
            stamp = path.stat().st_mtime_ns
        except OSError:
            stamp = None
    if _CACHE["target"] == target and _CACHE["stamp"] == stamp:
        return _CACHE["profile"], _CACHE["path"], _CACHE["issues"]
    data, path, issues = profiles.load(target) if target else ({}, None, [])
    if issues:
        log.debug("voice-gate profile issues: %s", issues)
    _CACHE.update({"target": target, "stamp": stamp, "profile": data, "path": path, "issues": issues})
    return data, path, issues


def _active() -> Tuple[Dict[str, Any], Optional[Path], List[str]]:
    return _loaded(str(_setting("profile", "") or "").strip())


def _applies_here(data: Dict[str, Any]) -> bool:
    allowed = data.get("applies_to")
    if not isinstance(allowed, (list, tuple)) or not allowed:
        return True
    return _current_profile() in {str(item).strip().lower() for item in allowed}


def _min_words(data: Dict[str, Any]) -> int:
    override = _setting("min_words", 0)
    try:
        value = int(override or 0)
    except (TypeError, ValueError):
        value = 0
    if value > 0:
        return value
    try:
        return int((data.get("thresholds") or {}).get("min_words") or rules.BASE_THRESHOLDS["min_words"])
    except (TypeError, ValueError):
        return int(rules.BASE_THRESHOLDS["min_words"])


def _resolve_path(raw: str) -> Optional[Path]:
    try:
        path = Path(raw)
        if not path.is_absolute():
            path = Path.cwd() / path
        path = path.resolve()
        if not path.is_file() or path.suffix.lower() not in PROSE_SUFFIXES:
            return None
        if any(part in SKIP_PARTS for part in path.parts):
            return None
        return path
    except Exception:
        return None


def _message(found: List[Tuple[str, List[str]]], mode: str, name: str, note: str = "") -> str:
    listed = "; ".join(f"{file}: {', '.join(calls)}" for file, calls in found)
    pieces: List[str] = []
    if listed:
        if mode == "improve":
            pieces.append(f"fix {len(found)} file(s) before this turn ends. {listed}.")
        else:
            pieces.append(f"tells in {len(found)} changed file(s). {listed}.")
    if note:
        pieces.append(note)
    if mode == "improve":
        tail = "Rewrite the passages whose job is explanation, then re-read the file."
        return f"voice-gate improve ({name}): {' '.join(pieces)} {tail}"
    tail = "Rewrite the passages whose job is explanation, or say why the shape is deliberate."
    return f"voice-gate ({name}): {' '.join(pieces)} {tail}"


VALE_OFF = {"off", "skip", "no", "false", "0", ""}


def _vale_advisory(paths: List[Path]) -> Optional[str]:
    """A second opinion from Vale, when it is installed and switched on.

    The pack under ``styles/`` is generated from the same families, so Vale
    contributes positions and a per-rule breakdown rather than different words.
    Fail-open in every direction: no binary, no report, or fewer alerts than the
    threshold, and the gate says nothing on its behalf.
    """
    mode = str(_setting("vale_mode", "off") or "off").strip().lower()
    if mode in VALE_OFF or not paths:
        return None
    override = _vale_path()
    if not vale.resolve_binary(override):
        return None
    report = vale.run([str(path) for path in paths[:6]], override)
    if not report.get("ok"):
        return None
    alerts: List[Dict[str, Any]] = []
    for results in (report.get("report") or {}).values():
        for alert in results or []:
            if str(alert.get("Severity") or "").lower() in ("error", "warning"):
                alerts.append(alert)
    try:
        floor = int(_setting("vale_min_alerts", 3) or 3)
    except (TypeError, ValueError):
        floor = 3
    if len(alerts) < floor:
        return None
    counts: Dict[str, int] = {}
    for alert in alerts:
        name = str(alert.get("Check") or "rule").split(".")[-1]
        counts[name] = counts.get(name, 0) + 1
    summary = ", ".join(f"{name} {count}" for name, count in
                        sorted(counts.items(), key=lambda item: -item[1])[:4])
    first = alerts[0]
    files = len(report.get("report") or {})
    return (f"Vale reports {len(alerts)} alert(s) in {files} file(s) ({summary}); "
            f"first at line {first.get('Line')}: {first.get('Match')}.")


def _on_pre_verify(**kwargs: Any) -> Optional[Dict[str, Any]]:
    try:
        mode = _mode()
        if mode == "skip":
            return None
        attempt = int(kwargs.get("attempt") or 0)
        if mode == "warn" and attempt != 0:
            return None
        data, _path, _issues = _active()
        if not _applies_here(data):
            return None
        floor = _min_words(data)
        found: List[Tuple[str, List[str]]] = []
        checked: List[Path] = []
        for raw in kwargs.get("changed_paths") or []:
            path = _resolve_path(str(raw))
            if path is None:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            result = rules.lint(text, data)
            if int(result.get("words") or 0) < floor:
                continue
            checked.append(path)
            calls = rules.gate_findings(result, data)
            if calls:
                found.append((path.name, calls))
        advisory = _vale_advisory(checked) or ""
        if not found and not advisory:
            return None
        return {"action": "continue",
                "message": _message(found, mode, str(data.get("name") or "base"), advisory)}
    except Exception:
        log.debug("voice-gate pre_verify failed", exc_info=True)
        return None


# --------------------------------------------------------------------------- tools


def _dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _read_sample(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_SAMPLE_BYTES:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _collect(paths: List[str], text: str) -> List[str]:
    samples: List[str] = [text] if text and text.strip() else []
    for raw in paths:
        base = Path(os.path.expandvars(os.path.expanduser(str(raw))))
        if base.is_dir():
            for path in sorted(base.rglob("*")):
                if len(samples) >= _MAX_SAMPLES:
                    break
                if path.is_file() and path.suffix.lower() in SAMPLE_SUFFIXES and \
                        not any(part in SKIP_PARTS for part in path.parts):
                    body = _read_sample(path)
                    if body.strip():
                        samples.append(body)
        elif base.is_file():
            body = _read_sample(base)
            if body.strip():
                samples.append(body)
    return samples[:_MAX_SAMPLES]


def _tool_check(args: Dict[str, Any]) -> Dict[str, Any]:
    target = str(args.get("profile") or "").strip()
    data, path, issues = _loaded(target) if target else _active()
    texts: List[Tuple[str, str]] = []
    if args.get("text"):
        texts.append(("text", str(args["text"])))
    for raw in args.get("paths") or []:
        resolved = _resolve_path(str(raw))
        if resolved is None:
            continue
        try:
            texts.append((resolved.name, resolved.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            continue
    if not texts:
        return {"ok": False, "error": "nothing to check: pass text or paths"}
    reports = []
    for label, body in texts:
        result = rules.lint(body, data)
        reports.append({
            "source": label,
            "words": result["words"],
            "findings": rules.gate_findings(result, data),
            "tells": result["tells"],
        })
    return {
        "ok": True,
        "profile": {"name": data.get("name") or "base", "path": str(path) if path else None, "issues": issues},
        "reports": reports,
    }


def _tool_profile(args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "show").strip().lower()
    if action == "list":
        found = []
        for directory in profiles.search_dirs():
            if not directory.is_dir():
                continue
            for path in sorted(directory.iterdir()):
                if path.suffix.lower() in profiles.PROFILE_SUFFIXES:
                    data, _p, issues = profiles.load(str(path))
                    found.append({"name": data.get("name") or path.stem, "path": str(path), "issues": issues})
        return {"ok": True, "profiles": found, "search_dirs": [str(d) for d in profiles.search_dirs()]}

    target = str(args.get("profile") or _setting("profile", "") or "").strip()
    data, path, issues = _loaded(target) if target else ({}, None, [])
    if action == "validate":
        if path is None:
            return {"ok": False, "error": f"profile {target!r} not found", "search_dirs": [str(d) for d in profiles.search_dirs()]}
        return {"ok": not issues, "path": str(path), "issues": issues}
    merged = rules.merge(data)
    return {
        "ok": True,
        "active": bool(path),
        "name": merged["name"],
        "path": str(path) if path else None,
        "applies_to": data.get("applies_to") or [],
        "current_profile": _current_profile(),
        "applies_here": _applies_here(data),
        "thresholds": merged["thresholds"],
        "preferences": merged["preferences"],
        "rule_counts": {key: len(value) for key, value in merged["rules"].items()},
        "issues": issues,
        "search_dirs": [str(d) for d in profiles.search_dirs()],
    }


def _tool_learn(args: Dict[str, Any]) -> Dict[str, Any]:
    name = str(args.get("name") or "my-voice").strip()
    samples = _collect([str(p) for p in (args.get("paths") or [])], str(args.get("text") or ""))
    if not samples:
        return {"ok": False, "error": "no samples found: pass paths or text"}
    draft = profiles.draft(samples, name)
    saved = None
    if args.get("save"):
        directory = profiles.hermes_home() / "voice-profiles"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.yaml"
        try:
            import yaml  # type: ignore

            path.write_text(yaml.safe_dump(draft, sort_keys=False, allow_unicode=True), encoding="utf-8")
        except Exception:
            path = directory / f"{name}.json"
            path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        saved = str(path)
    return {"ok": True, "samples": len(samples), "draft": draft, "saved": saved}


VALE_SCHEMA = {
    "name": "voice_gate_vale",
    "description": (
        "Install and run Vale, the prose linter, on Markdown you name. action=status reports what is "
        "installed; action=install downloads the pinned release after the digest is checked; "
        "action=check runs it over files and returns the alerts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "install", "check"],
                       "description": "status, install, or check."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Markdown files for action=check."},
            "path": {"type": "string",
                     "description": "Optional path to a Vale binary to use instead of the plugin's copy."},
        },
        "required": ["action"],
    },
}


def _vale_path() -> str:
    return str(_setting("vale_path", "") or "").strip()


def _tool_vale(args: Dict[str, Any]) -> Dict[str, Any]:
    action = str(args.get("action") or "status").strip().lower()
    override = str(args.get("path") or "").strip() or _vale_path()
    if action == "status":
        return vale.status(override)
    if action == "install":
        return vale.install(override)
    if action == "check":
        return vale.run([str(p) for p in (args.get("paths") or [])], override)
    return {"ok": False, "error": f"unknown action {action!r}"}


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **_kwargs: Any) -> Optional[Dict[str, Any]]:
    """Send the one call that downloads and runs a binary to the approval prompt."""
    if tool_name != VALE_SCHEMA["name"] or not isinstance(args, dict):
        return None
    if str(args.get("action") or "").strip().lower() != "install":
        return None
    name, digest, _kind = vale.asset()
    return {
        "action": "approve",
        "message": (
            f"voice_gate_vale install will download {name} from GitHub "
            f"(vale {vale.VERSION}), check sha256 {digest[:16]}…, and run the unpacked binary from "
            f"{vale.data_dir()}"
        ),
    }


CHECK_SCHEMA = {
    "name": "voice_gate_check",
    "description": (
        "Run the active writing profile over text or files and list the tells it finds. "
        "Use before sending something long, or to explain why the gate objected to a file."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Prose to check."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Markdown files to check instead of text."},
            "profile": {"type": "string",
                        "description": "Profile name or path to use instead of the active one."},
        },
        "required": [],
    },
}

PROFILE_SCHEMA = {
    "name": "voice_gate_profile",
    "description": (
        "Inspect writing profiles: which one is active, what rules and thresholds it carries, "
        "whether it has problems, and which profiles are available."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["show", "list", "validate"],
                       "description": "show the active profile, list available profiles, or validate one."},
            "profile": {"type": "string", "description": "Profile name or path. Defaults to the active one."},
        },
        "required": [],
    },
}

LEARN_SCHEMA = {
    "name": "voice_gate_learn",
    "description": (
        "Read a corpus of somebody's writing (chat exports, emails, documents) and produce a draft "
        "voice-gate profile from it, with the measured habits and candidate openings and closings."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Profile name, for example 'my-voice'."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Files or directories holding the samples."},
            "text": {"type": "string", "description": "Samples pasted directly."},
            "save": {"type": "boolean",
                     "description": "Write the draft to HERMES_HOME/voice-profiles/<name>.yaml."},
        },
        "required": ["name"],
    },
}


def _as_handler(fn, name: str):
    def handler(args: Optional[dict] = None, **_kwargs) -> str:
        try:
            payload = fn(dict(args or {}))
            return _dump(payload)
        except Exception as exc:
            log.exception("voice-gate tool %s failed", name)
            return _dump({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return handler


def register(ctx: Any) -> None:
    global _CTX
    _CTX = ctx
    ctx.register_hook("pre_verify", _on_pre_verify)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    for schema, fn in (
        (CHECK_SCHEMA, _tool_check),
        (PROFILE_SCHEMA, _tool_profile),
        (LEARN_SCHEMA, _tool_learn),
        (VALE_SCHEMA, _tool_vale),
    ):
        ctx.register_tool(
            name=schema["name"],
            toolset="voice_gate",
            schema=schema,
            handler=_as_handler(fn, schema["name"]),
            emoji="🪶",
        )
    try:
        ctx.register_skill("voice-profile-builder", _SKILL, description=_SKILL_DESCRIPTION)
    except Exception:
        log.warning("voice-gate could not register its profile skill", exc_info=True)
