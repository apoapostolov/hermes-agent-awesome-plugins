"""Prose checks, contextual editorial review, and bounded revision guidance.

Both editions share the rules and tools for checking and reviewing documents.
The personal edition also loads approved writing profiles and can draft a
profile from explicitly curated author samples.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import profile as profiles
from . import extract
from . import rules
from . import vale
from . import editorial
from . import model_review
from . import coverage
from . import diagnostics

log = logging.getLogger(__name__)

PROSE_SUFFIXES = set(extract.TEXT_SUFFIXES) | set(extract.PDF_SUFFIXES)
SAMPLE_SUFFIXES = {".md", ".markdown", ".mdx", ".txt", ".json"}
SKIP_PARTS = {".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"}
_SKIP_WORDS = {"off", "skip", "false", "no", "0"}
_MAX_SAMPLES = 400
_MAX_SAMPLE_BYTES = 2_000_000

_SKILL = Path(__file__).resolve().parent / "skills" / "voice-profile-builder" / "SKILL.md"
_SKILL_DESCRIPTION = "Build a voice-gate writing profile from a corpus of somebody's own writing."

_CTX: Any = None
_CACHE: Dict[str, Any] = {"target": None, "stamp": None, "profile": {}, "path": None, "issues": []}
_TURN_RECORDS: Dict[Any, Any] = {}
_REVIEWED: Dict[Any, str] = {}
PERSONAL_EDITION = _SKILL.is_file()
_OWNED_REVIEW_TASK = False


def _home() -> Path:
    """The Hermes home of the profile this turn belongs to.

    The host resolves it: a context-local override, then ``HERMES_HOME``, then the
    platform default. Reading the variable here instead lands the turn in the
    launch profile's tree whenever one process serves several profiles, which
    puts the settings and the voice profiles under the wrong profile. The probe
    below stays for a host where core cannot be imported.
    """
    served = profiles.served_home()
    if served is not None:
        return served
    candidates: List[Path] = []
    raw = os.environ.get("HERMES_HOME")
    if raw:
        candidates.append(Path(raw))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "hermes")
    candidates.append(Path.home() / ".hermes")
    for candidate in candidates:
        if (candidate / "config.yaml").is_file():
            return candidate
    return candidates[0]


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


BOT_FLAGS = {
    "default": "apply_hermes",
    "hermes": "apply_hermes",
    "herald": "apply_herald",
    "keeper": "apply_keeper",
    "steward": "apply_steward",
    "tinker": "apply_tinker",
}
_TRUTHY = {"1", "true", "yes", "on", "y"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUTHY


def _plugin_name() -> str:
    try:
        manifest = (Path(__file__).parent / 'plugin.yaml').read_text(encoding='utf-8')
        match = re.search(r'^name:\s*(.+)$', manifest, re.M)
        name = match[1].strip().strip('\"\'') if match else ''
        if name:
            return name
    except Exception:
        pass
    return "voice-gate"


def _root_settings() -> Dict[str, Any]:
    """The plugin's settings as the install root holds them.

    A settings page opened on the Herald scope writes Herald's own config, so
    the per-bot switches are read from the file the default profile owns. The
    host has no PyYAML in its process, and a plugin should not reach into the
    host's own config reader, so this reads the flat ``apply_*`` scalars under
    ``plugins.entries.<plugin>.settings`` by indentation.
    """
    home = _home()
    if home.parent.name == "profiles":
        home = home.parent.parent
    try:
        lines = (home / "config.yaml").read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    names = {_plugin_name(), "voice-gate", "Voice Gate"}
    entries_indent = None
    entry_indent = None
    settings_indent = None
    found: Dict[str, Any] = {}
    for raw in lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        stripped = raw.strip()
        if entries_indent is None:
            if stripped == "entries:":
                entries_indent = indent
            continue
        if strip_key(stripped) in names and indent > entries_indent:
            entry_indent, settings_indent, found = indent, None, {}
            continue
        if entry_indent is None:
            continue
        if indent <= entry_indent:
            if found:
                return found
            entry_indent, settings_indent = None, None
            if stripped == "entries:":
                entries_indent = indent
            continue
        if settings_indent is None:
            if stripped == "settings:":
                settings_indent = indent
            continue
        if indent <= settings_indent:
            return found
        key, _, value = stripped.partition(":")
        key = key.strip().strip("\"'")
        if key.startswith("apply_"):
            found[key] = value.strip().strip("\"'")
    return found


def strip_key(line: str) -> str:
    return line.partition(":")[0].strip().strip("\"'")


def _bots_allow() -> bool:
    """Which bots run the gate. No boxes set means every bot runs it."""
    flags = {key: value for key, value in _root_settings().items() if str(key).startswith("apply_")}
    if not flags:
        return True
    wanted = BOT_FLAGS.get(_current_profile())
    if wanted is None:
        return True
    return _truthy(flags.get(wanted, True))


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
    if _CACHE["target"] == target and _CACHE["stamp"] == stamp and _CACHE['path'] == path:
        return _CACHE["profile"], _CACHE["path"], _CACHE["issues"]
    data, path, issues = profiles.load(target) if target else ({}, None, [])
    if issues:
        log.warning("voice-gate profile rejected; using base rules: %s", issues)
        data = {}
    _CACHE.update({"target": target, "stamp": stamp, "profile": data, "path": path, "issues": issues})
    _diagnostic('profile.loaded', profile=diagnostics.identifier(path) if path else None,
                issues_count=len(issues), fallback=bool(issues))
    return data, path, issues


def _active() -> Tuple[Dict[str, Any], Optional[Path], List[str]]:
    data, path, issues = _loaded(str(_setting("profile", "") or "").strip()) if PERSONAL_EDITION else ({}, None, [])
    context = str(_setting('context', '') or '').strip().lower()
    if context and context != 'auto':
        data = {**data, 'context': context}
    if _truthy(_setting('no_prose_em_dash', True)):
        data = {**data, 'preferences': {**(data.get('preferences') or {}), 'no_em_dash': True}}
    return data, path, issues


def _applies_here(data: Dict[str, Any]) -> bool:
    """The per-bot switches win when any are set; otherwise the profile decides."""
    if any(str(key).startswith("apply_") for key in _root_settings()):
        return _bots_allow()
    allowed = data.get("applies_to")
    if not isinstance(allowed, (list, tuple)) or not allowed:
        return True
    return _current_profile() in {str(item).strip().lower() for item in allowed}


def _min_words(data: Dict[str, Any]) -> int:
    """An explicit 0 turns the floor off; unset falls back to the profile."""
    raw = _setting("min_words", None)
    if raw is not None and str(raw).strip() != "":
        try:
            return max(int(raw), 0)
        except (TypeError, ValueError):
            pass
    try:
        return max(0, int((data.get("thresholds") or {}).get("min_words", rules.BASE_THRESHOLDS["min_words"])))
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
            pieces.append(f"review {len(found)} file(s) before this turn ends. {listed}.")
        else:
            pieces.append(f"tells in {len(found)} changed file(s). {listed}.")
    if note:
        pieces.append(note)
    if mode == "improve":
        tail = "Inspect context and pass conditions before editing. Fix only justified, authorized spans; a phrase match alone never requires a rewrite."
        return f"voice-gate improve ({name}): {' '.join(pieces)} {tail}"
    tail = "Rewrite the passages whose job is explanation, or say why the shape is deliberate."
    return f"voice-gate ({name}): {' '.join(pieces)} {tail}"


VALE_OFF = {"off", "skip", "no", "false", "0", ""}


def _vale_advisory(paths: List[Path], active_families: Optional[set] = None) -> Optional[str]:
    """A second opinion from Vale, when it is installed and switched on.

    The pack under ``styles/`` is generated from the same families, so Vale
    contributes positions and a per-rule breakdown rather than different words.
    Fail-open in every direction: no binary, no report, or fewer alerts than the
    threshold, and the gate says nothing on its behalf.
    """
    mode = str(_setting("vale_mode", "off") or "off").strip().lower()
    if mode in VALE_OFF or not paths:
        _diagnostic('vale.skip', reason='disabled_or_no_documents')
        return None
    override = _vale_path()
    if not vale.resolve_binary(override):
        _diagnostic('vale.skip', reason='binary_unavailable')
        return None
    started = time.perf_counter()
    report = vale.run([str(path) for path in paths[:6]], override, approved_only=True)
    _diagnostic('vale.result', ok=report.get('ok'), documents_count=min(len(paths), 6),
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2))
    if not report.get("ok"):
        return None
    alerts: List[Dict[str, Any]] = []
    family_by_check = {
        'Terms': {'buzzwords', 'tier1a', 'tier2'}, 'Marketing': {'marketing_adjectives'},
        'Significance': {'significance_inflation'}, 'Signposts': {'conclusion_signposts'},
        'Openers': {'cliche_openers'}, 'Candor': {'candor_frames'}, 'Objections': {'objection_frames'},
        'Slogans': {'dev_slogans'}, 'WhOpener': {'wh_openers'}, 'FutureNarrative': {'future_narrative'},
        'NumberedList': {'number_inflation'}, 'Hashtags': {'hashtag_stuffing'},
        'ToolFingerprint': {'tool_fingerprints'}, 'AssistantResidue': {'assistant_residue'},
        'TemplateResidue': {'template_residue'}, 'NegationTriad': {'negation_triads'},
    }
    for filename, results in (report.get("report") or {}).items():
        policy = active_families.get(str(Path(filename).resolve()), {}) if isinstance(active_families, dict) else {}
        active_here = set(policy) if isinstance(active_families, dict) else active_families
        if isinstance(results, dict):
            results = results.get('Alerts', [])
        for alert in results or []:
            family = str(alert.get('Check') or '').rsplit('.', 1)[-1]
            if active_here is not None and not family_by_check.get(family, {family}).intersection(active_here):
                continue
            if policy:
                accepted = set()
                for key in family_by_check.get(family, {family}):
                    accepted.update(re.sub(r'\s+', ' ', value).strip().lower() for value in policy.get(key, []))
                matched = re.sub(r'\s+', ' ', str(alert.get('Match') or '')).strip().lower()
                if accepted and matched not in accepted:
                    continue
            if str(alert.get("Severity") or "").lower() in ("error", "warning"):
                alerts.append(alert)
    try:
        floor = int(_setting("vale_min_alerts", 3) or 3)
    except (TypeError, ValueError):
        floor = 3
    if len(alerts) < floor:
        _diagnostic('vale.below_floor', alerts_count=len(alerts), floor=floor)
        return None
    counts: Dict[str, int] = {}
    for alert in alerts:
        name = str(alert.get("Check") or "rule").split(".")[-1]
        counts[name] = counts.get(name, 0) + 1
    _diagnostic('vale.findings', alerts_count=len(alerts), floor=floor, rules=counts)
    summary = ", ".join(f"{name} {count}" for name, count in
                        sorted(counts.items(), key=lambda item: -item[1])[:4])
    first = alerts[0]
    files = len(report.get("report") or {})
    return (f"Vale reports {len(alerts)} alert(s) in {files} file(s) ({summary}); "
            f"first at line {first.get('Line')}: {first.get('Match')}.")


def _exceptions_block(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The profile's exceptions with the settings' own rows laid over them.

    A profile carries exceptions because a preference about typography belongs
    to the person writing. The settings copy exists for a public install with no
    profile, and both merge, so a row added in one place never cancels the other.
    """
    data = data or {}
    rows = rules.exceptions(data.get("exceptions"), str(_setting("exceptions", "") or ""))
    block = dict(data)
    if rows:
        block["exceptions"] = rows
    return block


def _family_off(key: str) -> bool:
    """A family switched off in settings never fires, whatever the profile says."""
    value = _setting(f"tell_{key}", True)
    if isinstance(value, str):
        return value.strip().lower() in {"0", "false", "off", "no", "skip"}
    return value is False


def _disabled_families() -> List[str]:
    return [key for key in rules.TELL_KEYS if _family_off(key)]


def _diagnostic(event: str, **fields: Any) -> None:
    try:
        diagnostics.emit(_home(), event, **fields)
    except Exception:
        pass


@diagnostics.traced('gate', _home)
def _on_pre_verify(**kwargs: Any) -> Optional[Dict[str, Any]]:
    try:
        mode = _mode()
        _diagnostic('gate.policy', mode=mode, attempt=kwargs.get('attempt'),
                    session=diagnostics.identifier(kwargs.get('session_id') or ''),
                    changed_paths_count=len(kwargs.get('changed_paths') or []),
                    bot=diagnostics.identifier(_current_profile()))
        if mode == "skip":
            _diagnostic('gate.skip', reason='mode_off')
            return None
        attempt = int(kwargs.get("attempt") or 0)
        if attempt >= 2:
            _diagnostic('gate.skip', reason='pass_limit')
            log.info('voice-gate stopped after two review/edit opportunities; report unresolved residuals.')
            return None
        if mode == "warn" and attempt != 0:
            _diagnostic('gate.skip', reason='warn_already_shown')
            return None
        data, _path, _issues = _active()
        if not _applies_here(data):
            _diagnostic('gate.skip', reason='profile_excluded')
            return None
        block = _exceptions_block(data)
        floor = _min_words(data)
        found: List[Tuple[str, List[str]]] = []
        checked: List[Path] = []
        disabled = _disabled_families()
        _diagnostic('gate.configuration', word_floor=floor, disabled=disabled,
                    profile=diagnostics.identifier(_path) if _path else None,
                    profile_issue_count=len(_issues),
                    model_review=_truthy(_setting('model_review', False)))
        families = {}
        model_documents = {}
        model_exclusions = {}
        notes = []
        if _issues:
            notes.append('Profile configuration is invalid; base rules are in use: ' + '; '.join(_issues))
        for raw in kwargs.get("changed_paths") or []:
            path = _resolve_path(str(raw))
            if path is None:
                _diagnostic('document.skip', file=diagnostics.file_id(str(raw)), reason='unresolved_or_unsupported')
                continue
            try:
                text = (extract.read(path) or "")
            except OSError as exc:
                _diagnostic('document.skip', file=diagnostics.file_id(path), reason='read_error', **diagnostics.error_fields(exc))
                continue
            if not text.strip():
                _diagnostic('document.skip', file=diagnostics.file_id(path), reason='empty_or_unextractable')
                continue
            started = time.perf_counter()
            result = rules.lint(text, data, path)
            _diagnostic('document.lint', file=diagnostics.file_id(path), content=editorial.digest(text),
                        words=result.get('words'), context=result.get('context'),
                        elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                        rules={key: tell.get('count', 0) for key, tell in result['tells'].items() if tell.get('count', 0)})
            strict_dash = (data.get('preferences') or {}).get('no_em_dash') and result['tells']['em_dashes']['count']
            if int(result.get("words") or 0) < floor and not strict_dash:
                _diagnostic('document.skip', file=diagnostics.file_id(path), reason='below_word_floor')
                continue
            key = _review_key(path, text, block, disabled)
            if key in _REVIEWED:
                _diagnostic('document.skip', file=diagnostics.file_id(path), reason='review_record_matches')
                continue
            checked.append(path)
            model_documents[str(path)] = text
            issues = rules.gate_findings(result, block, str(path), disabled=disabled, structured=True)
            if int(result.get('words') or 0) < floor:
                issues = [item for item in issues if item['rule'] == 'em_dashes']
            _diagnostic('document.findings', file=diagnostics.file_id(path),
                        issues=[{'rule': item['rule'], 'severity': item['severity']} for item in issues],
                        suppressed=rules.suppressed(block, str(path)))
            skip = set(rules.suppressed(block, str(path))) | set(disabled) | set(rules.relaxed(result['context']))
            families[str(path)] = {key: tell.get('samples', []) for key, tell in result['tells'].items()
                                   if tell.get('count', 0) and key not in skip}
            model_exclusions[str(path)] = [number for number in range(1, 111)
                                           if f'pattern_{number}' in skip or set(coverage.MECHANICAL.get(number, ())).intersection(skip)]
            if len(model_exclusions[str(path)]) == 110:
                model_documents.pop(str(path), None)
            calls = [f"{item['severity']} {item['message']}" for item in issues]
            turn_key = (str(kwargs.get('session_id') or ''), str(path))
            signature = editorial.signature(text)
            previous = _TURN_RECORDS.get(turn_key)
            if previous and attempt:
                integrity = editorial.compare_signatures(previous['signature'], signature)
                _diagnostic('document.preservation', file=diagnostics.file_id(path),
                            errors_count=len(integrity['errors']), warnings_count=len(integrity['warnings']),
                            unchanged=previous['digest'] == editorial.digest(text))
                if integrity['errors']:
                    calls = ['Repair only protected material changed during revision: ' + ', '.join(integrity['errors'])]
                notes.extend(integrity['warnings'])
                if previous['digest'] == editorial.digest(text):
                    notes.append(f'{path.name} is unchanged. Record a justified no-op with voice_gate_review; do not rewrite only to lower counts.')
            else:
                _remember(_TURN_RECORDS, turn_key, {'signature': signature, 'digest': editorial.digest(text)})
            if calls:
                found.append((path.name, calls))
        advisory = _vale_advisory(checked, families) or ''
        if _truthy(_setting('model_review', False)) and model_documents:
            started = time.perf_counter()
            contextual = model_review.analyze(_CTX, model_documents, data, _OWNED_REVIEW_TASK, model_exclusions)
            _diagnostic('model_review.result', elapsed_ms=round((time.perf_counter() - started) * 1000, 2), **diagnostics.summary(contextual))
            if contextual.get('ok'):
                for issue in contextual['issues']:
                    found.append((Path(issue['path']).name, [f"{issue['severity']} humanizer {issue['pattern_id']}: {issue['quote']!r}. {issue['explanation']} {issue['repair']}"]))
            else:
                log.warning('voice-gate contextual review unavailable: %s', contextual.get('error'))
                if found:
                    notes.append('The model review was unavailable; complete the contextual review explicitly.')
        if not found and not advisory and not _issues:
            _diagnostic('gate.decision', decision='allow', checked_count=len(checked))
            return None
        notes.append(f"Read {editorial.SOURCE / 'SKILL.md'} and the relevant catalog references. Check meaning, reader priority, supported voice, evidence, narrative when applicable, delivery residue, and over-correction. Preserve code, quotations, tables, URLs, paths, headings, and technical terms. Record the reviewed paths and assessment with voice_gate_review(action='record'). Use at most two passes including preservation repairs; then report residuals. These are editorial signals, never authorship proof.")
        if advisory:
            notes.append(advisory)
        _diagnostic('gate.decision', decision='request_review', checked_count=len(checked),
                    flagged_count=len(found), vale_advisory=bool(advisory), notes_count=len(notes))
        return {"action": "continue",
                "message": _message(found, mode, str(data.get("name") or "base"), ' '.join(dict.fromkeys(notes)))}
    except Exception as exc:
        _diagnostic('gate.failure', **diagnostics.error_fields(exc))
        log.exception("voice-gate pre_verify failed; gate did not verify this turn")
        return None


# --------------------------------------------------------------------------- tools


def _dump(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _remember(cache: Dict[Any, Any], key: Any, value: Any) -> None:
    if len(cache) >= 64 and key not in cache:
        cache.pop(next(iter(cache)))
    cache.pop(key, None)
    cache[key] = value


def _review_key(path: Path, text: str, data: Dict[str, Any], disabled: List[str]) -> Any:
    policy = editorial.digest(json.dumps({'profile': data, 'disabled': disabled, 'owner': str(_home()), 'bot': _current_profile(), 'model_review': _truthy(_setting('model_review', False)), 'vale': _setting('vale_mode', 'off')}, sort_keys=True))
    return (str(path), editorial.digest(text), policy)


def _tool_review(args: Dict[str, Any]) -> Dict[str, Any]:
    if str(args.get('action') or '') == 'analyze':
        if not _truthy(_setting('model_review', False)):
            return {'ok': False, 'error': 'Turn on Review meaning and structure in Voice Gate settings before requesting a model review.'}
        data, _path, issues = _active()
        if issues:
            return {'ok': False, 'issues': issues, 'error': 'Fix the writing profile before requesting model review.'}
        documents = {}
        exclusions = {}
        for raw in args.get('paths') or []:
            path = _resolve_path(str(raw))
            text = extract.read(path) if path else None
            if text:
                documents[str(path)] = text
                context = data.get('context') or rules.context_for_path(str(path))
                skip = set(rules.suppressed(_exceptions_block(data), str(path))) | set(_disabled_families()) | set(rules.relaxed(context))
                exclusions[str(path)] = [number for number in range(1, 111)
                                         if f'pattern_{number}' in skip or set(coverage.MECHANICAL.get(number, ())).intersection(skip)]
        if not documents:
            return {'ok': False, 'error': 'Pass readable prose files in paths.'}
        return model_review.analyze(_CTX, documents, data, _OWNED_REVIEW_TASK, exclusions)
    if str(args.get('action') or 'plan') == 'plan':
        plan = editorial.review_plan(args.get('pattern_ids'))
        if not args.get('pattern_ids'):
            plan['patterns'] = [{'id': entry['id'], 'title': entry['title']} for entry in plan['patterns']]
        return {'ok': True, **plan}
    assessment = str(args.get('assessment') or '').strip()
    if not assessment:
        return {'ok': False, 'error': 'Record the contextual assessment, justified edits or no-op, and any protected or factual residuals.'}
    data, _path, issues = _active()
    if issues:
        return {'ok': False, 'error': 'Fix the profile configuration before recording a review.', 'issues': issues}
    block, disabled = _exceptions_block(data), _disabled_families()
    reviewed, residuals = [], []
    for raw in args.get('paths') or []:
        path = _resolve_path(str(raw))
        if path is None:
            return {'ok': False, 'error': f'Unreadable or unsupported prose path: {raw}'}
        text = extract.read(path)
        if text is None:
            return {'ok': False, 'error': f'Could not extract prose: {path}'}
        previous = next((record for key, record in reversed(list(_TURN_RECORDS.items())) if key[1] == str(path)), None)
        if previous:
            integrity = editorial.compare_signatures(previous['signature'], editorial.signature(text))
            if integrity['errors']:
                return {'ok': False, 'error': 'Repair protected material before completing the review.', 'preservation': integrity}
        result = rules.lint(text, data, str(path))
        calls = rules.gate_findings(result, block, str(path), disabled=disabled, structured=True)
        if (data.get('preferences') or {}).get('no_em_dash') and any(call['rule'] == 'em_dashes' for call in calls):
            return {'ok': False, 'error': 'The explicit prose em-dash policy is still violated. Fix editable prose or report the protected residual; a review cannot waive the house rule.', 'issues': calls}
        key = _review_key(path, text, block, disabled)
        reviewed.append(key)
        residuals.append({'path': str(path), 'issues': calls})
    if not reviewed:
        return {'ok': False, 'error': 'Pass the prose paths you reviewed.'}
    for key in reviewed:
        _remember(_REVIEWED, key, assessment)
    return {'ok': True, 'reviewed': [key[0] for key in reviewed], 'assessment': assessment,
            'residuals': residuals, 'interpretation': 'editorial_attestation_not_machine_certification'}


def _read_sample(path: Path) -> str:
    try:
        if path.stat().st_size > _MAX_SAMPLE_BYTES:
            return ""
        if path.suffix.lower() == '.json':
            try:
                data = json.loads(path.read_text(encoding='utf-8-sig'))
                samples = data.get('samples') if isinstance(data, dict) else data
                return '\n\n'.join(samples) if isinstance(samples, list) and all(isinstance(item, str) for item in samples) else ''
            except (ValueError, OSError):
                return ''
        return (extract.read(path) or "")
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
    data, path, issues = _loaded(target) if target and PERSONAL_EDITION else _active()
    block = _exceptions_block(data)
    declared = str(args.get("path") or "").strip()
    texts: List[Tuple[str, str, str]] = []
    if args.get("text"):
        texts.append(("text", str(args["text"]), declared))
    for raw in args.get("paths") or []:
        resolved = _resolve_path(str(raw))
        if resolved is None:
            continue
        try:
            texts.append((resolved.name, (extract.read(resolved) or ""), str(resolved)))
        except OSError:
            continue
    if not texts:
        return {"ok": False, "error": "nothing to check: pass text or paths"}
    disabled = _disabled_families()
    reports = []
    for label, body, where in texts:
        result = rules.lint(body, data, where)
        reports.append({
            "source": label,
            "words": result["words"],
            'context': result['context'] or 'blog',
            'eligible_for_turn_gate': result['words'] >= _min_words(data) or bool((data.get('preferences') or {}).get('no_em_dash') and result['tells']['em_dashes']['count']),
            "findings": rules.gate_findings(result, block, where, disabled=disabled),
            "issues": rules.gate_findings(result, block, where, disabled=disabled, structured=True),
            "exceptions": rules.suppressed(block, where),
            "tells": result["tells"],
        })
    return {
        "ok": True,
        "profile": {"name": data.get("name") or "base", "path": str(path) if path else None, "issues": issues},
        "checks": reports,
        'interpretation': 'editorial_signals_only',
        'review_checks': editorial.REVIEW_CHECKS,
        'review_source': str(editorial.SOURCE / 'SKILL.md'),
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
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', name):
        return {'ok': False, 'error': 'Use a profile name containing letters, digits, hyphens, or underscores; paths are not names.'}
    samples = _collect([str(p) for p in (args.get("paths") or [])], str(args.get("text") or ""))
    if not samples:
        return {"ok": False, "error": "no samples found: pass paths or text"}
    draft = profiles.draft(samples, name)
    saved = None
    if args.get("save"):
        directory = profiles.hermes_home() / "voice-profiles"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{name}.yaml"
        if path.exists() or path.with_suffix('.json').exists():
            return {'ok': False, 'error': 'This profile already exists; choose a new name to preserve it.'}
        path = directory / f'{name}.json'
        path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding='utf-8')
        saved = str(path)
    return {"ok": True, "samples": len(samples), "draft": draft, "saved": saved}


VALE_SCHEMA = {
    "name": "voice_gate_vale",
    "description": (
        "Install and run Vale, the prose linter, on prose files you name. action=status reports what is "
        "installed; action=install downloads the pinned release after the digest is checked; "
        "action=check runs it over files and returns the alerts."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["status", "install", "check"],
                       "description": "status, install, or check."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Prose files for action=check."},
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
        result = vale.status(override)
    elif action == "install":
        result = vale.install(override)
    elif action == "check":
        result = vale.run([str(p) for p in (args.get("paths") or [])], override)
    else:
        return {"ok": False, "error": f"unknown action {action!r}"}
    # Reaching here means the pre_tool_call gate let the call through, so the
    # binary this call named is the one a person approved. Turn-time findings
    # accept only that binary, and only while its digest still matches.
    binary = str(result.get("binary") or "") or vale.resolve_binary(override)
    if binary and (action != "install" or result.get("ok")):
        vale.record_approval(binary)
    return result


def _on_pre_tool_call(tool_name: str = "", args: Any = None, **_kwargs: Any) -> Optional[Dict[str, Any]]:
    """Send the one call that downloads and runs a binary to the approval prompt."""
    if tool_name != VALE_SCHEMA["name"] or not isinstance(args, dict):
        return None
    action = str(args.get('action') or '').strip().lower()
    _diagnostic('vale.approval_check', action=action if action in {'status', 'check', 'install'} else 'unknown',
                paths_count=len(args.get('paths') or []))
    if action in {'status', 'check'}:
        binary = vale.resolve_binary(str(args.get('path') or '').strip() or _vale_path())
        if not binary:
            return None
        arguments = ['--version'] if action == 'status' else [f'--config={vale.config_path()}', '--output=JSON', *[str(path) for path in args.get('paths', [])]]
        return {'action': 'approve', 'message': f'Run {binary} with arguments {arguments!r} for voice_gate_vale {action}.'}
    if action != 'install':
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
            "path": {"type": "string",
                     "description": "Optional file name for text, so exceptions written for that "
                                    "kind of file apply."},
            "paths": {"type": "array", "items": {"type": "string"},
                      "description": "Prose files to check instead of text."},
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
                     "description": "Write the draft to HERMES_HOME/voice-profiles/<name>.json."},
        },
        "required": ["name"],
    },
}

REVIEW_SCHEMA = {
    'name': 'voice_gate_review',
    'description': 'Get the complete 110-pattern humanizer review plan, inspect numbered rules and carve-outs, or record a contextual review/no-op for exact file contents. Never certifies authorship or factual correctness.',
    'parameters': {'type': 'object', 'properties': {
        'action': {'type': 'string', 'enum': ['plan', 'analyze', 'record']},
        'pattern_ids': {'type': 'array', 'items': {'type': 'integer'}, 'description': 'For plan: return the full guidance for these catalog pattern numbers.'},
        'paths': {'type': 'array', 'items': {'type': 'string'}, 'description': 'For record: the files actually reread against the humanizer editorial contract.'},
        'assessment': {'type': 'string', 'description': 'For record: explain context, evidence, edits or deliberate no-op, preservation and remaining limitations.'},
    }, 'required': ['action']},
}


def _as_handler(fn, name: str):
    @diagnostics.traced('tool.' + name, _home)
    def handler(args: Optional[dict] = None, **_kwargs) -> str:
        try:
            _diagnostic('tool.input', tool=name, action=(args or {}).get('action') if (args or {}).get('action') in {'status', 'check', 'install', 'show', 'list', 'validate', 'plan', 'analyze', 'record'} else None,
                        paths_count=len((args or {}).get('paths') or []),
                        text_chars=len(str((args or {}).get('text') or '')),
                        assessment_chars=len(str((args or {}).get('assessment') or '')))
            payload = fn(dict(args or {}))
            _diagnostic('tool.result', tool=name, **diagnostics.summary(payload))
            return _dump(payload)
        except Exception as exc:
            _diagnostic('tool.failure', tool=name, **diagnostics.error_fields(exc))
            log.exception("voice-gate tool %s failed", name)
            return _dump({"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    return handler


def register(ctx: Any) -> None:
    global _CTX, _OWNED_REVIEW_TASK
    _CTX = ctx
    _diagnostic('plugin.register', edition='personal', max_log_bytes=diagnostics.MAX_BYTES,
                backups=diagnostics.BACKUPS, bot=diagnostics.identifier(_current_profile()))
    _OWNED_REVIEW_TASK = False
    register_task = getattr(ctx, 'register_auxiliary_task', None)
    if callable(register_task):
        register_task(model_review.TASK, display_name='Voice Gate review', description='Check changed prose against the humanizer editorial contract.')
        _OWNED_REVIEW_TASK = True
    ctx.register_hook("pre_verify", _on_pre_verify)
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    for schema, fn in (
        (CHECK_SCHEMA, _tool_check),
        (PROFILE_SCHEMA, _tool_profile),
        (LEARN_SCHEMA, _tool_learn),
        (VALE_SCHEMA, _tool_vale),
        (REVIEW_SCHEMA, _tool_review),
    ):
        if not PERSONAL_EDITION and schema['name'] in {'voice_gate_profile', 'voice_gate_learn'}:
            continue
        if not PERSONAL_EDITION and schema['name'] == 'voice_gate_check':
            properties = {key: value for key, value in schema['parameters']['properties'].items() if key != 'profile'}
            schema = {**schema, 'parameters': {**schema['parameters'], 'properties': properties}}
        ctx.register_tool(
            name=schema["name"],
            toolset="voice_gate",
            schema=schema,
            handler=_as_handler(fn, schema["name"]),
            emoji="🪶",
        )
    try:
        if PERSONAL_EDITION:
            ctx.register_skill("voice-profile-builder", _SKILL, description=_SKILL_DESCRIPTION)
    except Exception:
        log.warning("voice-gate could not register its profile skill", exc_info=True)
