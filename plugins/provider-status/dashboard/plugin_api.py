"""Provider Status plugin backend — mounted at /api/plugins/provider-status/"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter
from pydantic import BaseModel

log = logging.getLogger(__name__)
router = APIRouter()

# Config lives NEXT TO THE PLUGIN (dashboard/../config.json) so it works no matter
# what HERMES_HOME the embedding process uses. Also read env from that same home.
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PLUGIN_ROOT / "config.json"


def _default_hermes_home() -> Path:
    env = os.environ.get("HERMES_HOME")
    if env:
        return Path(env)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        win = Path(local) / "hermes"
        if win.exists():
            return win
    return Path.home() / ".hermes"


HERMES_HOME = _default_hermes_home()
LIFESTYLE_ENV = Path("C:/git/lifestyle/.env")
CACHE_TTL = 60  # 1 min — keep the bar fresh, APIs are cheap

# ── Config ─────────────────────────────────────────────────────────
def load_config() -> dict:
    cfg: dict = {"providers": {}}
    if CONFIG_PATH.exists():
        try:
            loaded = json.loads(CONFIG_PATH.read_text("utf-8"))
            if isinstance(loaded, dict):
                cfg = loaded
        except Exception:
            pass
    if not cfg.get("poll_minutes"):
        lib = PLUGIN_ROOT / "library.env"
        if lib.exists():
            try:
                for line in lib.read_text("utf-8").splitlines():
                    if line.strip().startswith("POLL_MINUTES="):
                        cfg["poll_minutes"] = max(1, int(line.split("=", 1)[1].strip()))
                        break
            except Exception:
                pass
    return cfg

def save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: readers never see a truncated file (empty JSON used to make
    # the dialog show "not logged in" and could wipe tokens on the next save).
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2), "utf-8")
    os.replace(tmp, CONFIG_PATH)
    try:
        pm = int(cfg.get("poll_minutes") or 0)
        if pm >= 1:
            _upsert_env_key(PLUGIN_ROOT / "library.env", "POLL_MINUTES", str(pm))
    except Exception:
        pass


# Serializes every read-modify-write of config.json. Without it, a token
# refresh (grok/codex rotate their refresh_token on use) racing any other
# writer resurrects the ALREADY-CONSUMED refresh_token -> "re-login required".
_config_lock = threading.RLock()


def mutate_config(fn) -> dict:
    """Locked read-modify-write: load fresh, let fn mutate, save. Use this
    instead of ad-hoc load_config()+save_config() pairs."""
    with _config_lock:
        cfg = load_config()
        fn(cfg)
        save_config(cfg)
        return cfg


def _merge_pool_fields(fresh_cfg: dict, src_providers: dict, pids: list[str]) -> None:
    """Copy ONLY pool/pool_index from src_providers into fresh_cfg. Never
    rewrites the whole provider dict, so OAuth secrets written concurrently
    by a token refresh survive."""
    provs = fresh_cfg.setdefault("providers", {})
    for pid in pids:
        src = src_providers.get(pid) or {}
        prev = dict(provs.get(pid) or {})
        for f in ("pool", "pool_index", "reset_days", "reset_days_fired"):
            if f in src:
                prev[f] = src[f]
        provs[pid] = prev

# ── Env resolution ─────────────────────────────────────────────────
_env_cache: dict[str, str] = {}
_env_loaded = False

def _load_env_files() -> None:
    global _env_loaded
    if _env_loaded:
        return
    _env_loaded = True
    for p in [LIFESTYLE_ENV, HERMES_HOME / ".env"]:
        try:
            if not p.exists():
                continue
            for line in p.read_text("utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip("\"'")
                # Hermes .env is loaded second and wins so a rotated
                # runtime key beats the lifestyle original.
                if k:
                    _env_cache[k] = v
        except Exception:
            pass
    # expand ${VAR} refs against the merged map (lifestyle numbered-pool layout uses them)
    for _ in range(4):  # bounded passes for chained refs
        changed = False
        for k, v in list(_env_cache.items()):
            if "${" in v:
                for rk, rv in _env_cache.items():
                    nv = v.replace("${" + rk + "}", rv)
                    if nv != v:
                        _env_cache[k] = nv
                        v = nv
                        changed = True
        if not changed:
            break

def resolve_key(env_names: list[str], pool: list[str] | None = None, pool_index: int = 0) -> str | None:
    _load_env_files()
    if pool:
        idx = pool_index % len(pool)
        if pool[idx]:
            return pool[idx]
    for name in env_names:
        v = os.environ.get(name)
        if v:
            return v
        v = _env_cache.get(name)
        if v:
            return v
    return None


# ── Key library + rotation ─────────────────────────────────────────
# Provider-status keeps its own env file so rotating the active Hermes
# key never drops a previous subscription. Hermes .env is copy-in only.
LIBRARY_PATH = PLUGIN_ROOT / "library.env"
HERMES_ENV = HERMES_HOME / ".env"
ROTATE_REMAINING = 2.0  # switch when displayed remaining is 2% or less
_library_lock = threading.Lock()

ROTATABLE = {
    "tavily": {"primary": "TAVILY_API_KEY", "match": ("TAVILY_API_KEY",)},
    "opencode": {"primary": "OPENCODE_GO_API_KEY", "match": ("OPENCODE_GO_API_KEY", "OPENCODE_GO_2_API_KEY")},
    "deepseek": {"primary": "DEEPSEEK_API_KEY", "match": ("DEEPSEEK_API_KEY",)},
    "glm": {"primary": "ZAI_API_KEY", "match": ("ZAI_API_KEY", "GLM_API_KEY")},
    "openrouter": {"primary": "OPENROUTER_API_KEY", "match": ("OPENROUTER_API_KEY",)},
}
_SKIP_ENV = (
    "_LABEL", "_LABELS", "_INDEX", "_POOL", "_WORKSPACE", "_WORPLACE",
    "_AUTH_COOKIE", "_LAST_REASON", "_LAST_ROTATED", "_LEFT_SLOT",
    "_LEFT_SLOT1", "_LEFT_SLOT_2",
)


def _parse_env_map(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    try:
        for line in path.read_text("utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, _, v = s.partition("=")
            k, v = k.strip(), v.strip().strip("\"'")
            if k and v and not v.startswith("${"):
                out[k] = v
    except Exception:
        pass
    return out


def _upsert_env_key(path: Path, key: str, value: str) -> None:
    """Replace KEY=... in place or append. Preserve comments and other keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        raw = path.read_text("utf-8") if path.exists() else ""
    except Exception:
        raw = ""
    lines = raw.splitlines()
    found = False
    prefix = key + "="
    out_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) and not stripped.startswith("#"):
            out_lines.append(f"{key}={value}")
            found = True
        else:
            out_lines.append(line)
    if not found:
        if out_lines and out_lines[-1].strip():
            out_lines.append("")
        out_lines.append(f"{key}={value}")
    text = "\n".join(out_lines)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _library_values() -> list[str]:
    return list(_parse_env_map(LIBRARY_PATH).values())


def _library_has_value(value: str) -> bool:
    return value in set(_library_values())


def _next_library_name(primary: str, existing: dict[str, str]) -> str:
    if primary not in existing:
        return primary
    n = 2
    while f"{primary}_{n}" in existing:
        n += 1
    return f"{primary}_{n}"


def _is_key_name(name: str, stems: tuple[str, ...]) -> bool:
    if any(name.endswith(suf) for suf in _SKIP_ENV):
        return False
    for stem in stems:
        if name == stem or name.startswith(stem + "_"):
            return True
        # OPENCODE_GO_2_API_KEY vs stem OPENCODE_GO_API_KEY
        if stem.endswith("_API_KEY") and name.endswith("_API_KEY") and name.startswith(stem[: -len("_API_KEY")]):
            return True
    return False


def _ingest_library(cfg: dict) -> dict:
    """Copy new keys from Hermes .env + current pools into library.env. Never delete."""
    hermes = _parse_env_map(HERMES_ENV)
    with _library_lock:
        lib = _parse_env_map(LIBRARY_PATH)
        added = 0
        for pid, spec in ROTATABLE.items():
            stems = tuple(spec["match"])
            candidates: list[str] = []
            for name, val in hermes.items():
                if _is_key_name(name, stems) and val not in candidates:
                    candidates.append(val)
            pool = ((cfg.get("providers") or {}).get(pid) or {}).get("pool") or []
            for val in pool:
                if val and val not in candidates:
                    candidates.append(val)
            for val in candidates:
                if val in lib.values():
                    continue
                slot = _next_library_name(spec["primary"], lib)
                lib[slot] = val
                _upsert_env_key(LIBRARY_PATH, slot, val)
                added += 1
        if added:
            log.info("provider-status library ingested %s new key(s)", added)
        # sync config pools from library (unique, stable order)
        providers = cfg.setdefault("providers", {})
        dirty = False
        for pid, spec in ROTATABLE.items():
            stems = tuple(spec["match"])
            values = [v for k, v in lib.items() if _is_key_name(k, stems)]
            # keep first-seen order from current pool then library extras
            pconf = providers.get(pid)
            if pconf is None:
                continue  # deleted rows stay gone; do not resurrect from library.env
            old = list(pconf.get("pool") or [])
            merged: list[str] = []
            for v in old + values:
                if v and v not in merged:
                    merged.append(v)
            if merged != old:
                pconf["pool"] = merged
                dirty = True
            if pconf.get("pool_index", 0) >= max(len(merged), 1):
                pconf["pool_index"] = 0
                dirty = True
        if dirty:
            with _config_lock:
                fresh = load_config()
                _merge_pool_fields(fresh, cfg.get("providers") or {}, list(ROTATABLE))
                save_config(fresh)
    return cfg


def _display_remaining(pid: str, status: dict) -> float | None:
    """Same remaining % the statusbar shows. None if this provider has no %."""
    if not status or not status.get("ok"):
        return None
    bal = status.get("balance")
    if bal is not None and pid in ("deepseek", "openrouter"):
        try:
            bal_f = float(bal)
        except (TypeError, ValueError):
            return None
        try:
            granted = float(status.get("granted") or 0)
        except (TypeError, ValueError):
            granted = 0.0
        if granted > 0:
            return max(0.0, (bal_f / granted) * 100.0)
        return 0.0 if bal_f <= 0 else 100.0
    pct = status.get("exhaust_percent", status.get("percent"))
    if pct is None:
        return None
    try:
        pct = float(pct)
    except (TypeError, ValueError):
        return None
    return max(0.0, 100.0 - pct)


def _exhausted(pid: str, status: dict) -> bool:
    rem = _display_remaining(pid, status)
    return rem is not None and rem <= ROTATE_REMAINING


# Foundry AI-Provider-Library classify-probe.mjs
# green = key works; amber = quota / retry later; red = dead / banned / auth
_WARN_CODES = {402, 408, 425, 429, 503, 529}
_ERROR_CODES = {
    400, 401, 403, 404, 405, 409, 410, 413, 414, 415, 422, 451,
    500, 501, 502, 504, 507, 520, 521, 522, 523, 524,
}
_WARN_TEXT = (
    "rate limit", "too many requests", "overloaded", "resource exhausted",
    "insufficient quota", "insufficient credit", "insufficient balance",
    "quota exceeded", "credit balance", "spend limit", "payment required",
    "timeout", "no grok code cli plan",
)


def _http_code(status: dict) -> int:
    if not isinstance(status, dict):
        return 0
    raw = status.get("status") or status.get("code") or 0
    try:
        n = int(raw)
        if n:
            return n
    except (TypeError, ValueError):
        pass
    err = str(status.get("error") or "")
    for tok in err.replace("HTTP", " ").replace("auth", " ").split():
        if tok.isdigit() and len(tok) == 3:
            return int(tok)
    return 0


def classify_tone(pid: str, status: dict) -> dict:
    """Return {tone: ok|warn|error, reason, remaining} for a traffic-light dot."""
    rem = _display_remaining(pid, status) if isinstance(status, dict) else None
    if status and status.get("ok"):
        if _exhausted(pid, status):
            return {"tone": "warn", "reason": "Exhausted", "remaining": rem}
        return {"tone": "ok", "reason": "Healthy", "remaining": rem}
    err = str((status or {}).get("error") or "unknown")
    low = err.lower()
    code = _http_code(status or {})
    if (status or {}).get("needs_auth") or code in (401, 403):
        return {"tone": "error", "reason": err or "unauthorized", "remaining": rem}
    if (status or {}).get("no_plan"):
        return {"tone": "error", "reason": err or "no plan", "remaining": rem}
    if code in _WARN_CODES or any(m in low for m in _WARN_TEXT):
        return {"tone": "warn", "reason": err or "retry later", "remaining": rem}
    if code in _ERROR_CODES or any(m in low for m in ("unreachable", "econnrefused", "enotfound", "no key", "banned")):
        return {"tone": "error", "reason": err or "not working", "remaining": rem}
    return {"tone": "error", "reason": err or "not working", "remaining": rem}


def _apply_hermes_key(pid: str, key: str) -> None:
    spec = ROTATABLE.get(pid)
    if not spec or not key:
        return
    primary = spec["primary"]
    with _library_lock:
        _upsert_env_key(HERMES_ENV, primary, key)
    os.environ[primary] = key
    _env_cache[primary] = key
    log.info("provider-status rotated %s -> Hermes .env %s", pid, primary)


def _maybe_rotate(pid: str, pconf: dict, status: dict, fetcher) -> tuple[dict, dict, bool]:
    """If this key is at <=2% remaining, switch to another library key that is not."""
    pool = [k for k in (pconf.get("pool") or []) if k]
    if len(pool) < 2 or not _exhausted(pid, status):
        return status, pconf, False
    start = int(pconf.get("pool_index") or 0) % len(pool)
    for off in range(1, len(pool)):
        idx = (start + off) % len(pool)
        trial = dict(pconf)
        trial["pool_index"] = idx
        st = fetcher(trial)
        if st.get("ok") and not _exhausted(pid, st):
            pconf = dict(pconf)
            pconf["pool_index"] = idx
            _apply_hermes_key(pid, pool[idx])
            st["rotated"] = True
            st["pool_index"] = idx
            st["pool_size"] = len(pool)
            return st, pconf, True
    status = dict(status)
    status["exhausted_pool"] = True
    status["pool_index"] = start
    status["pool_size"] = len(pool)
    return status, pconf, False

# ── OAuth account pools (grok/codex) ───────────────────────────────
# Multiple logged-in accounts per provider, rotated like key pools when the
# active one is exhausted. Storage: pconf["accounts"] = [acc, ...] plus
# pconf["account_index"]. The flat access_token/refresh_token/... fields are
# always kept in sync with the ACTIVE account so the fetchers (which read the
# flat fields) never need to know pools exist.

_OAUTH_FIELDS = ("access_token", "refresh_token", "expires_at", "client_id", "issuer", "email")


def _oauth_accounts(pconf: dict) -> list[dict]:
    """Normalized account list: explicit `accounts` if present, else the legacy
    flat single-account view."""
    accounts = [a for a in (pconf.get("accounts") or [])
                if isinstance(a, dict) and (a.get("access_token") or a.get("refresh_token"))]
    if accounts:
        return accounts
    if pconf.get("access_token") or pconf.get("refresh_token"):
        return [{f: pconf.get(f) for f in _OAUTH_FIELDS if f in pconf}]
    return []


def _materialize_oauth(pconf: dict) -> dict:
    """Copy the active account's fields over the flat fields."""
    accounts = _oauth_accounts(pconf)
    if not accounts:
        return pconf
    idx = int(pconf.get("account_index") or 0) % len(accounts)
    out = dict(pconf)
    for f in _OAUTH_FIELDS:
        if f in accounts[idx]:
            out[f] = accounts[idx][f]
    out["account_index"] = idx
    out["account_size"] = len(accounts)
    return out


def _maybe_rotate_oauth(pid: str, pconf: dict, status: dict, fetcher) -> tuple[dict, dict, bool]:
    """If the active account is exhausted, switch to another account that is not."""
    accounts = _oauth_accounts(pconf)
    if len(accounts) < 2 or not _exhausted(pid, status):
        return status, pconf, False
    start = int(pconf.get("account_index") or 0) % len(accounts)
    for off in range(1, len(accounts)):
        idx = (start + off) % len(accounts)
        trial = _materialize_oauth({**pconf, "account_index": idx})
        st = fetcher(trial)
        if st.get("ok") and not _exhausted(pid, st):
            pconf = dict(pconf)
            pconf["accounts"] = accounts
            pconf["account_index"] = idx
            for f in _OAUTH_FIELDS:
                if f in accounts[idx]:
                    pconf[f] = accounts[idx][f]
            st["rotated"] = True
            st["account_index"] = idx
            st["account_size"] = len(accounts)
            return st, pconf, True
    status = dict(status)
    status["exhausted_pool"] = True
    status["account_index"] = start
    status["account_size"] = len(accounts)
    return status, pconf, False


# ── Subscription renewal-day rotation (OpenCode Go, extensible) ────
# Every key can carry `reset_days` = [int|None] (index-aligned with pool).
# Day X = the day of month that subscription renews on. After the day passes
# (i.e. on day X+1, once), the provider switches to that key — the renewed
# subscription has a fresh quota. Month-guarded so the switch fires exactly
# once per month per key. Applies to providers in ROTATABLE (key pools).

RESET_ROTATABLE = ("opencode",)  # providers where the dropdown is offered


def _maybe_reset_day_rotate(pid: str, pconf: dict) -> tuple[dict, bool]:
    """Returns (updated pconf, dirty). If any key's renewal day has passed this
    month and hasn't been consumed yet, switch pool_index to it."""
    if pid not in RESET_ROTATABLE:
        return pconf, False
    pool = [k for k in (pconf.get("pool") or []) if k]
    if len(pool) < 2:
        return pconf, False
    days = list(pconf.get("reset_days") or [])
    if not any(isinstance(d, int) and 1 <= d <= 31 for d in days):
        return pconf, False
    today = time.localtime()
    ym = today.tm_year * 100 + today.tm_mon          # 202608 style month key
    consumed = list(pconf.get("reset_days_fired") or [])  # ["202608:3", ...]
    cur = int(pconf.get("pool_index") or 0) % len(pool)
    for i, d in enumerate(days):
        if not isinstance(d, int) or not 1 <= d <= 31:
            continue
        tag = f"{ym}:{d}"
        if i == cur:
            if tag not in consumed:
                consumed.append(tag)          # own day passed: mark done
            continue
        if tag in consumed:
            continue
        # day has passed this month?
        last_day = _days_in_month(today.tm_year, today.tm_mon)
        effective = min(d, last_day)
        passed = today.tm_mday > effective
        if not passed and today.tm_mday <= 2 and d >= 29:
            # a day the previous month couldn't have (31st in a 30-day month,
            # 30th/31st in Feb): the renewal happened at that month's end —
            # fire early in the new month instead of never
            py, pm = (today.tm_year, today.tm_mon - 1) if today.tm_mon > 1 else (today.tm_year - 1, 12)
            pdim = _days_in_month(py, pm)
            prev_tag = f"{py * 100 + pm}:{d}"
            if d > pdim and prev_tag not in consumed and f"{ym}:{d}" not in consumed:
                passed = True
        if passed:
            pconf = dict(pconf)
            pconf["pool_index"] = i
            pconf["reset_days_fired"] = consumed + [tag]
            _apply_hermes_key(pid, pool[i])
            log.info("provider-status %s: renewal day %s passed, switched to key #%d",
                     pid, d, i + 1)
            return pconf, True
    # nothing fired; persist consumed marks only if they changed
    if consumed != list(pconf.get("reset_days_fired") or []):
        pconf = dict(pconf)
        pconf["reset_days_fired"] = consumed
        return pconf, True
    return pconf, False


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (time.mktime((year, month + 1, 1, 0, 0, 0, 0, 0, -1)) -
            time.mktime((year, month, 1, 0, 0, 0, 0, 0, -1))) // 86400


# ── HTTP helper ────────────────────────────────────────────────────
def api_get(url: str, headers: dict[str, str], timeout: int = 10) -> dict:
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

def api_post(url: str, headers: dict[str, str], body: dict, timeout: int = 10) -> dict:
    data = urlencode(body).encode()
    req = Request(url, data=data, headers=headers, method="POST")
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())

# ── Cache + failure resilience ─────────────────────────────────────
_cache: dict[str, dict[str, Any]] = {}      # pid -> {"data": ..., "ts": ...} (fresh)
_last_good: dict[str, dict[str, Any]] = {}  # pid -> last successful payload (kept forever)
_fail_counts: dict[str, int] = {}           # consecutive failures per provider
_cache_lock = threading.Lock()
FAIL_THRESHOLD = 3  # show degraded state only after this many consecutive errors
TRANSIENT_MARKERS = ("urlopen error", "timed out", "timeout", "temporary failure",
                     "name or service not known", "getaddrinfo", "connection refused",
                     "econnrefused", "enotfound", "11001", "network")

def _is_transient(err_text: str) -> bool:
    t = (err_text or "").lower()
    return any(m in t for m in TRANSIENT_MARKERS)

def cached_status(pid: str) -> dict[str, Any] | None:
    with _cache_lock:
        e = _cache.get(pid)
        if e and time.time() - e["ts"] < CACHE_TTL:
            return e["data"]
    return None

def store_status(pid: str, data: dict[str, Any]) -> None:
    with _cache_lock:
        _cache[pid] = {"data": data, "ts": time.time()}
        if data.get("ok", False):
            _last_good[pid] = data
            _fail_counts[pid] = 0
    if data.get("ok", False):
        _sample_usage(pid, data)


# ── Burn-rate tracking (in-memory) ─────────────────────────────────
# Keeps the last few (ts, headline-number) samples per provider and derives
# "at this pace, exhausted in ~Xh" for the chip tooltip. Reset detection: a
# sample that DROPS by >25 points marks a window reset — the rate before it
# is meaningless for the new window, so history is cleared.

_samples: dict[str, list[tuple[float, float]]] = {}
_SAMPLES_MAX = 12
_SAMPLES_MIN_SPACING = 45.0  # seconds; ignore faster duplicate polls


def _sample_usage(pid: str, data: dict[str, Any]) -> None:
    # headline metric per provider: the number that matters for exhaustion
    if pid in ("deepseek", "openrouter"):
        val = data.get("balance")
    else:
        val = data.get("exhaust_percent", data.get("percent"))
    if not isinstance(val, (int, float)):
        return
    val = float(val)
    now = time.time()
    with _cache_lock:
        hist = _samples.setdefault(pid, [])
        if hist and now - hist[-1][0] < _SAMPLES_MIN_SPACING:
            hist[-1] = (now, val)  # refresh the latest sample in place
            return
        if hist and val < hist[-1][1] - 25.0:
            hist.clear()  # window reset — burn history is stale
        hist.append((now, val))
        del hist[:-_SAMPLES_MAX]


def burn_projection(pid: str) -> dict:
    """Derived burn rate from samples. Returns {} when not enough data.
    percent_per_hour >0 means the headline number RISES (5h used %);
    <0 means it FALLS (remaining drains / balance drops)."""
    with _cache_lock:
        hist = list(_samples.get(pid) or [])
    if len(hist) < 2:
        return {}
    (t0, v0), (t1, v1) = hist[0], hist[-1]
    dt = t1 - t0
    if dt < 60:
        return {}
    rate = (v1 - v0) / (dt / 3600.0)  # units per hour
    if abs(rate) < 0.5:
        return {"rate_per_hour": round(rate, 2), "eta_hours": None}
    if rate > 0:
        eta = (100.0 - v1) / rate if v1 < 100 else 0.0
    else:
        eta = v1 / abs(rate) if v1 > 0 else 0.0
    return {"rate_per_hour": round(rate, 2), "eta_hours": round(max(0.0, eta), 1)}

def record_failure(pid: str) -> dict[str, Any] | None:
    """Count a provider failure. Before FAIL_THRESHOLD: serve the last good payload
    tagged stale. From threshold on: return the degraded payload. Network blips never
    blank the bar."""
    with _cache_lock:
        n = _fail_counts.get(pid, 0) + 1
        _fail_counts[pid] = n
    if n < FAIL_THRESHOLD:
        lg = _last_good.get(pid)
        if lg is not None:
            out = dict(lg)
            out["stale"] = True
            return out
    return None


# ── Provider fetchers ──────────────────────────────────────────────

def fetch_deepseek(cfg: dict) -> dict:
    key = resolve_key(["DEEPSEEK_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "DEEPSEEK_API_KEY"}
    try:
        d = api_get("https://api.deepseek.com/user/balance",
                     {"Authorization": f"Bearer {key}", "Accept": "application/json"})
        bi = d.get("balance_infos", [{}])[0]
        bal = float(bi.get("total_balance", 0))
        return {"ok": True, "balance": bal,
                "granted": float(bi.get("granted_balance", 0)),
                "topped_up": float(bi.get("topped_up_balance", 0))}
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


def fetch_openrouter(cfg: dict) -> dict:
    key = resolve_key(["OPENROUTER_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "OPENROUTER_API_KEY"}
    try:
        d = api_get("https://openrouter.ai/api/v1/credits",
                     {"Authorization": f"Bearer {key}", "Accept": "application/json"})
        data = d.get("data") if isinstance(d.get("data"), dict) else d
        total = float(data.get("total_credits") or 0)
        used = float(data.get("total_usage") or 0)
        return {"ok": True, "balance": total - used, "granted": total, "used": used}
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


def _next_reset_epoch(lim: dict) -> float:
    """z.ai limits carry nextResetTime in epoch ms; normalize to epoch s."""
    try:
        v = int(lim.get("nextResetTime") or 0)
        if v > 1e12:  # ms
            v /= 1000
        return float(v) if v > 1e9 else 0.0
    except (TypeError, ValueError):
        return 0.0


def fetch_glm(cfg: dict) -> dict:
    key = resolve_key(["ZAI_API_KEY", "GLM_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "ZAI_API_KEY"}
    try:
        d = api_get("https://api.z.ai/api/monitor/usage/quota/limit",
                     {"Authorization": key, "Accept": "application/json"})
        if not d.get("success", True):
            return {"ok": False, "error": d.get("msg", "API error")}
        data = d.get("data") or {}
        limits = data.get("limits") if isinstance(data, dict) else None
        limits = limits if isinstance(limits, list) else []
        session_pct = weekly_pct = monthly_pct = 0.0
        session_reset = 0.0
        for lim in limits:
            ltype = str(lim.get("type") or "").upper()
            unit = int(lim.get("unit") or -1)
            pct = float(lim.get("percentage") or 0)
            if ltype == "TOKENS_LIMIT":
                if unit == 3:
                    session_pct = pct
                    session_reset = _next_reset_epoch(lim)
                elif unit in (6, 4):
                    weekly_pct = pct
            elif ltype == "TIME_LIMIT" and unit in (5, 7):
                monthly_pct = pct
        # Headline is the 5h increase window (used %). Rotation uses
        # monthly/weekly exhaust, never the 5h burst.
        exhaust = monthly_pct or weekly_pct or None
        windows = []
        if session_pct or session_pct == 0:
            windows.append({"label": "5h", "pct": session_pct, "direction": "increase"})
        if weekly_pct is not None:
            windows.append({"label": "wk", "pct": weekly_pct, "direction": "exhaust"})
        if monthly_pct is not None:
            windows.append({"label": "mo", "pct": monthly_pct, "direction": "exhaust"})
        return {"ok": True, "percent": session_pct,
                "exhaust_percent": exhaust,
                "resets_at": session_reset,
                "detail": "5h",
                "windows": windows}
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


def fetch_tavily(cfg: dict) -> dict:
    key = resolve_key(["TAVILY_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "TAVILY_API_KEY"}
    try:
        d = api_get("https://api.tavily.com/usage",
                     {"Authorization": f"Bearer {key}", "Accept": "application/json",
                      "User-Agent": "provider-status-plugin/0.2"})
        acct = d.get("account") or {}
        keyu = d.get("key") or {}
        plan_usage = float(acct.get("plan_usage") or 0)
        plan_limit = float(acct.get("plan_limit") or 0)
        paygo_usage = float(acct.get("paygo_usage") or 0)
        paygo_limit = float(acct.get("paygo_limit") or 0)
        key_usage = float(keyu.get("usage") or 0)
        key_limit = float(keyu.get("limit") or 0)

        pct = 0.0
        in_paygo = False
        if plan_limit > 0:
            plan_pct = plan_usage / plan_limit * 100
            if plan_pct < 100:
                pct = plan_pct
            elif paygo_usage > 0:
                in_paygo = True
                pct = 100 + (min(paygo_usage / paygo_limit * 100, 100) if paygo_limit > 0 else 0)
            else:
                pct = 100
        elif key_limit > 0:
            pct = key_usage / key_limit * 100

        used = int(plan_usage or key_usage)
        limit = int(plan_limit or key_limit)
        # Quota line reads Monthly: the plan pool is a monthly allowance.
        return {"ok": True, "percent": round(pct, 1),
                "windows": [{"label": "mo", "pct": round(pct, 1), "direction": "exhaust"}],
                "detail": f"{used}/{limit}" + (" +paygo" if in_paygo else "")}
    except HTTPError as e:
        if e.code == 429:
            return {"ok": False, "error": "rate limited"}
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


# ── Grok OIDC device flow ─────────────────────────────────────────

OIDC_DISCOVERY = "https://auth.x.ai/.well-known/openid-configuration"
DEFAULT_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"  # grok CLI public client

# Codex (OpenAI) device flow — same issuer/client the codex CLI uses
CODEX_ISSUER = "https://auth.openai.com"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_SCOPE = "openid profile email offline_access"
CODEX_UA = "codex-cli/0.144.6"

def _oidc_discover(issuer: str = "https://auth.x.ai") -> dict:
    return api_get(issuer.rstrip("/") + "/.well-known/openid-configuration", {"Accept": "application/json"})

def grok_device_start(client_id: str = DEFAULT_CLIENT_ID) -> dict:
    try:
        disc = _oidc_discover()
        ep = disc.get("device_authorization_endpoint", "https://auth.x.ai/oauth/device/code")
        body = {"client_id": client_id, "scope": GROK_SCOPE}
        d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        return {"ok": True, "verification_uri": d.get("verification_uri", ""),
                "user_code": d.get("user_code", ""),
                "device_code": d.get("device_code", ""),
                "interval": d.get("interval", 5),
                "expires_in": d.get("expires_in", 300)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}

def _device_start(issuer: str, client_id: str, scope: str) -> dict:
    try:
        disc = _oidc_discover(issuer)
        ep = disc.get("device_authorization_endpoint", issuer.rstrip("/") + "/oauth/device/code")
        body = {"client_id": client_id, "scope": scope}
        d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded"}, body)
        return {"ok": True, "verification_uri": d.get("verification_uri", ""),
                "user_code": d.get("user_code", ""),
                "device_code": d.get("device_code", ""),
                "interval": d.get("interval", 5),
                "expires_in": d.get("expires_in", 300)}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}

def _device_poll(issuer: str, device_code: str, client_id: str) -> dict:
    try:
        disc = _oidc_discover(issuer)
        ep = disc.get("token_endpoint", issuer.rstrip("/") + "/oauth/token")
        body = {"grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code, "client_id": client_id}
        try:
            d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded"}, body)
            if "access_token" in d:
                return {"ok": True, "access_token": d["access_token"],
                        "id_token": d.get("id_token", ""),
                        "refresh_token": d.get("refresh_token", ""),
                        "expires_in": d.get("expires_in", 3600)}
            err = d.get("error", "")
        except HTTPError as e:
            err = f"HTTP {e.code}"
        if err in ("authorization_pending", "slow_down"):
            return {"ok": False, "pending": True, "error": err or "authorization_pending"}
        return {"ok": False, "error": err or "device flow failed"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}

# Single-flight token refresh: two concurrent callers (statusbar poll + dialog
# probe) must not both POST the refresh endpoint with the same refresh_token —
# providers rotate it on use, so the loser gets invalid_grant and reports a
# spurious "re-login required". Serialize per issuer; a caller that waited and
# finds the same refresh_token already refreshed reuses that result.
_refresh_locks: dict[str, threading.Lock] = {}
_refresh_locks_guard = threading.Lock()
_refresh_results: dict[tuple[str, str], dict] = {}


def _token_refresh(issuer: str, refresh_token: str, client_id: str) -> dict:
    with _refresh_locks_guard:
        lock = _refresh_locks.setdefault(issuer, threading.Lock())
    with lock:
        cached = _refresh_results.get((issuer, refresh_token))
        if cached is not None:
            return dict(cached)
        try:
            disc = _oidc_discover(issuer)
            ep = disc.get("token_endpoint", issuer.rstrip("/") + "/oauth/token")
            body = {"grant_type": "refresh_token", "refresh_token": refresh_token,
                    "client_id": client_id}
            d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded"}, body)
            if "access_token" in d:
                out = {"ok": True, "access_token": d["access_token"],
                       "refresh_token": d.get("refresh_token", refresh_token),
                       "expires_in": d.get("expires_in", 3600)}
            else:
                out = {"ok": False, "error": d.get("error", "refresh failed")}
        except Exception as e:
            out = {"ok": False, "error": str(e)[:80]}
        # remember successes per refresh_token (it is single-use; a repeat call
        # with it can only ever fail). Do not cache failures — they may be transient.
        if out.get("ok"):
            _refresh_results[(issuer, refresh_token)] = dict(out)
        return out


GROK_BILLING_URL = "https://cli-chat-proxy.grok.com/v1/billing?format=credits"
# Same product scopes the grok CLI requests. Device-flow with only
# "openid offline_access" gets 403 "no Grok Code CLI permission" even
# when the account has a plan.
GROK_SCOPE = "openid profile email offline_access grok-cli:access api:access"


def _jwt_payload(token: str) -> dict:
    try:
        import base64
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        data = json.loads(base64.urlsafe_b64decode(part.encode()))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _has_cli_scope(token: str) -> bool:
    scope = str(_jwt_payload(token).get("scope") or "")
    return "grok-cli:access" in scope.split()


def _jwt_alive(token: str, skew: int = 60) -> bool:
    exp = _jwt_payload(token).get("exp") or 0
    try:
        return float(exp) > time.time() + skew
    except (TypeError, ValueError):
        return False


def _cli_grok_entry() -> dict | None:
    p = Path.home() / ".grok" / "auth.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    best = None
    best_exp = -1.0
    for entry in (data or {}).values():
        if not isinstance(entry, dict):
            continue
        tok = str(entry.get("key") or "").strip()
        if not tok:
            continue
        exp = entry.get("expires_at")
        try:
            import datetime as _dt
            exp_ts = _dt.datetime.fromisoformat(str(exp).replace("Z", "+00:00")).timestamp() if exp else float("inf")
        except Exception:
            exp_ts = float(_jwt_payload(tok).get("exp") or 0) or 0.0
        if exp_ts >= best_exp:
            best, best_exp = entry, exp_ts
    return best


def _upsert_oauth_account(pid: str, result: dict, client_id: str, issuer: str, email: str = "") -> None:
    """Add or update (by refresh_token) an account in the provider's account
    pool and make it active. New logins append; re-logins refresh in place."""
    def _m(c: dict) -> None:
        p = c.setdefault("providers", {}).setdefault(pid, {})
        new_rt = str(result.get("refresh_token") or "")
        new_at = str(result.get("access_token") or "")
        accounts = [a for a in (p.get("accounts") or []) if isinstance(a, dict)]
        idx = None
        for i, a in enumerate(accounts):
            if new_rt and a.get("refresh_token") == new_rt:
                idx = i
                break
            if not new_rt and a.get("access_token") == new_at and new_at:
                idx = i
                break
        entry = {f: a.get(f) for f in _OAUTH_FIELDS if a.get(f) is not None} if idx is not None else {}
        entry.update({
            "access_token": new_at,
            "refresh_token": new_rt,
            "expires_at": time.time() + result.get("expires_in", 3600),
            "client_id": client_id,
        })
        if issuer:
            entry["issuer"] = issuer
        if email:
            entry["email"] = email
        if idx is None:
            accounts.append(entry)
            idx = len(accounts) - 1
        else:
            accounts[idx] = entry
        p["accounts"] = accounts
        p["account_index"] = idx
        for f in _OAUTH_FIELDS:
            if f in entry:
                p[f] = entry[f]
        p["enabled"] = True
    mutate_config(_m)


def _persist_grok_tokens(access: str, refresh: str, expires_in: int, client_id: str, email: str = "") -> None:
    try:
        _upsert_oauth_account("grok", {
            "access_token": access, "refresh_token": refresh, "expires_in": expires_in},
            client_id or DEFAULT_CLIENT_ID, "https://auth.x.ai", email)
    except Exception:
        pass


class BillingPermissionError(Exception):
    """Account lacks the Grok Code CLI product (403 from the proxy)."""
    pass


def _parse_iso_epoch(s: str) -> float:
    """ISO8601 (with Z or offset) -> unix epoch; 0.0 when unparsable."""
    if not s:
        return 0.0
    import datetime as _dt
    try:
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def _grok_billing(token: str) -> dict:
    import json as _json
    req = Request(GROK_BILLING_URL,
                  headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                           "User-Agent": "hermes-tui-grok-usage/1.0",
                           "x-grok-client-mode": "cli"})
    try:
        with urlopen(req, timeout=15) as resp:
            d = _json.loads(resp.read())
    except HTTPError as e:
        try:
            body = e.read().decode()[:200]
        except Exception:
            body = ""
        if e.code == 403 and "permission" in body.lower():
            if not _has_cli_scope(token):
                raise BillingPermissionError("token missing grok-cli:access (re-login)")
            raise BillingPermissionError("no Grok Code CLI plan")
        raise
    cfg2 = d.get("config", {})
    pct = float(cfg2.get("creditUsagePercent", 0))
    period = cfg2.get("currentPeriod", {}).get("type", "")
    ptype = "weekly" if "WEEKLY" in str(period) else "monthly" if "MONTHLY" in str(period) else "daily"
    reset_at = _parse_iso_epoch(cfg2.get("billingPeriodEnd", ""))
    return {"ok": True, "percent": pct, "period": ptype,
            "resets_at": reset_at,
            "reset": cfg2.get("billingPeriodEnd", "")}


def _try_grok_token(token: str, source: str) -> dict | None:
    if not token:
        return None
    try:
        out = _grok_billing(token)
        out["source"] = source
        return out
    except BillingPermissionError as e:
        err = str(e)
        if "missing grok-cli:access" in err:
            return {"ok": False, "error": err, "needs_auth": True, "source": source}
        return {"ok": False, "error": err, "no_plan": True, "source": source}
    except HTTPError as e:
        if e.code in (401, 403):
            return None
        return {"ok": False, "error": f"HTTP {e.code}", "source": source}
    except Exception:
        return None


def fetch_grok(cfg: dict) -> dict:
    """Use a token that actually has grok-cli:access.

    Setup-dialog device flow used to request only openid+offline_access, so a
    successful login still 403'd as "no plan". Prefer (1) an unexpired plugin
    token with CLI scope, (2) grok CLI auth.json, (3) refresh the CLI
    refresh_token, (4) refresh the plugin refresh_token.
    """
    client_id = cfg.get("client_id") or DEFAULT_CLIENT_ID
    dialog = str(cfg.get("access_token") or "").strip()
    if dialog and _jwt_alive(dialog) and _has_cli_scope(dialog):
        hit = _try_grok_token(dialog, "dialog")
        if hit and hit.get("ok"):
            return hit

    cli_entry = _cli_grok_entry() or {}
    cli_tok = str(cli_entry.get("key") or "").strip()
    if cli_tok and _jwt_alive(cli_tok) and _has_cli_scope(cli_tok):
        hit = _try_grok_token(cli_tok, "cli")
        if hit and hit.get("ok"):
            return hit

    cli_rt = str(cli_entry.get("refresh_token") or "").strip()
    if cli_rt:
        r = _token_refresh("https://auth.x.ai", cli_rt, cli_entry.get("oidc_client_id") or client_id)
        if r.get("ok"):
            tok = r["access_token"]
            _persist_grok_tokens(tok, r.get("refresh_token", cli_rt), r.get("expires_in", 21600),
                                 cli_entry.get("oidc_client_id") or client_id,
                                 str(cli_entry.get("email") or ""))
            hit = _try_grok_token(tok, "cli-refresh")
            if hit:
                return hit

    if dialog and _jwt_alive(dialog):
        hit = _try_grok_token(dialog, "dialog")
        if hit:
            return hit

    rt = str(cfg.get("refresh_token") or "").strip()
    if rt:
        r = _token_refresh("https://auth.x.ai", rt, client_id)
        if r.get("ok"):
            tok = r["access_token"]
            _persist_grok_tokens(tok, r.get("refresh_token", rt), r.get("expires_in", 3600), client_id)
            hit = _try_grok_token(tok, "dialog-refresh")
            if hit:
                return hit

    if dialog or cli_tok:
        return {"ok": False, "error": "re-login required (need grok-cli:access)", "needs_auth": True}
    return {"ok": False, "error": "not logged in", "needs_auth": True}

# ── Codex (OAuth device flow) ────────────────────────────────────

WHAM_URL = "https://chatgpt.com/backend-api/wham/usage"

def fetch_codex(cfg: dict) -> dict:
    token = cfg.get("access_token", "")
    expires = cfg.get("expires_at", 0)
    if not token:
        return {"ok": False, "error": "not logged in", "needs_auth": True}
    # refresh if needed
    if expires and time.time() > expires - 60:
        rt = cfg.get("refresh_token", "")
        if rt:
            r = _token_refresh(CODEX_ISSUER, rt, CODEX_CLIENT_ID)
            if r.get("ok"):
                token = r["access_token"]
                # persist refreshed token (locked; keeps the account pool in sync)
                try:
                    _upsert_oauth_account("codex", {
                        "access_token": token,
                        "refresh_token": r.get("refresh_token", rt),
                        "expires_in": r.get("expires_in", 3600),
                    }, CODEX_CLIENT_ID, CODEX_ISSUER)
                except Exception: pass
            else:
                return {"ok": False, "error": "token expired", "needs_auth": True}
        else:
            return {"ok": False, "error": "token expired", "needs_auth": True}
    try:
        d = api_get(WHAM_URL, {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": CODEX_UA,
        })
        email = str(cfg.get("email") or d.get("email") or "").strip()
        if email and email != cfg.get("email"):
            # remember which account is logged in (WHAM carries it)
            try:
                def _m(c: dict) -> None:
                    gp = c.setdefault("providers", {}).setdefault("codex", {})
                    gp["email"] = email
                mutate_config(_m)
            except Exception: pass
        # WHAM carries two windows: primary (weekly, 604800s) and secondary
        # (5h rolling, 18000s; null when idle). Classify by duration, not by
        # name — plans swap which slot carries which window.
        rl = d.get("rate_limit", {})
        def _win_used(w: dict) -> float | None:
            if not w or "used_percent" not in w:
                return None  # absent/null window — not "0% used"
            try:
                return float(w["used_percent"])
            except (TypeError, ValueError):
                return None
        def _win_secs(w: dict) -> int:
            try:
                return int(w.get("limit_window_seconds") or 0)
            except (TypeError, ValueError):
                return 0
        def _win_reset(w: dict) -> float:
            ra = w.get("reset_at")
            try:
                ra = float(ra)
                if ra > 1e9:
                    return ra
            except (TypeError, ValueError):
                pass
            raf = w.get("reset_after_seconds")
            try:
                raf = float(raf)
                if raf > 0:
                    return time.time() + raf
            except (TypeError, ValueError):
                pass
            return 0.0
        five = None; five_reset = 0.0
        weekly = None; weekly_reset = 0.0
        for w in (rl.get("primary_window") or {}, rl.get("secondary_window") or {}):
            u = _win_used(w)
            if u is None:
                continue
            if _win_secs(w) <= 21600:  # 5h-class rolling window
                five = u; five_reset = _win_reset(w)
            else:                       # weekly/monthly budget window
                weekly = u; weekly_reset = _win_reset(w)
        # opencode-style multi-window display: ↑5h headroom, ↓weekly remaining
        segs = []
        if five is not None:
            segs.append(f"↑{max(0.0, 100 - five):.0f}%")
        if weekly is not None:
            segs.append(f"↓{max(0.0, 100 - weekly):.0f}%")
        used_vals = [u for u in (five, weekly) if u is not None]
        worst = max(used_vals) if used_vals else 0.0
        resets = [r for r in (five_reset, weekly_reset) if r > 0]
        resets_at = min(resets) if resets else 0.0
        return {"ok": True, "percent": worst,
                "exhaust_percent": weekly,
                "reset_after": int(resets_at - time.time()) if resets_at else 0,
                "resets_at": resets_at,
                "detail": " ".join(segs),
                "email": email}
    except HTTPError as e:
        if e.code in (401, 403):
            return {"ok": False, "error": f"auth {e.code}", "needs_auth": True}
        return {"ok": False, "error": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


# ── OpenCode Go (stub) ────────────────────────────────────────────

OPENCODE_API_CANDIDATES = [
    "https://opencode.ai/zen/go/v1/usage",
    "https://opencode.ai/zen/go/v1/quota",
]

def _oc_pick_window(root: dict, names: list[str]) -> dict | None:
    for n in names:
        v = root.get(n)
        if isinstance(v, dict):
            return v
    return None

def _oc_parse_window(w: dict | None) -> float | None:
    """Window dicts carry usagePercent (number or string) in every shape seen so far."""
    if not isinstance(w, dict):
        return None
    raw = w.get("usagePercent", w.get("percent", w.get("usage")))
    try:
        pct = float(raw)
        return pct if 0 <= pct <= 100 else None
    except (TypeError, ValueError):
        return None

def _oc_window_reset(w: dict | None) -> float:
    """Window dicts may carry resetsAt (ISO). -> epoch, 0.0 when absent."""
    if not isinstance(w, dict):
        return 0.0
    return _parse_iso_epoch(str(w.get("resetsAt") or w.get("resetAt") or ""))

def fetch_opencode(cfg: dict) -> dict:
    """OpenCode Go quota via the key-authenticated REST endpoint (no dashboard).
    Tries /v1/usage then /v1/quota; parses rolling(5h)/weekly/monthly windows."""
    key = resolve_key(["OPENCODE_GO_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "OPENCODE_GO_API_KEY"}

    last_status = None
    for url in OPENCODE_API_CANDIDATES:
        try:
            d = api_get(url, {"Authorization": f"Bearer {key}",
                              "Accept": "application/json",
                              "User-Agent": "hermes-tui-opencode-usage/1.0"})
        except HTTPError as e:
            last_status = e.code
            if e.code == 404:
                continue  # candidate endpoint absent — try next
            if e.code in (401, 403):
                return {"ok": False, "error": f"auth {e.code}", "needs_auth": True}
            if e.code == 429:
                return {"ok": False, "error": "rate limited"}
            continue
        except Exception as e:
            last_status = None
            continue

        # Actual payload: {"usage": {"rolling": {"percent", "resetsAt"}, ...}}
        root = d.get("usage") or d.get("quota") or d.get("data") or d
        if not isinstance(root, dict):
            continue
        rolling_w = _oc_pick_window(root, ["rollingUsage", "window_5h", "rolling", "5h", "hourly"])
        weekly_w = _oc_pick_window(root, ["weeklyUsage", "window_weekly", "weekly", "week", "wk"])
        monthly_w = _oc_pick_window(root, ["monthlyUsage", "window_monthly", "monthly", "month", "mo"])
        rolling = _oc_parse_window(rolling_w)
        weekly = _oc_parse_window(weekly_w)
        monthly = _oc_parse_window(monthly_w)

        vals = [v for v in (rolling, weekly, monthly) if v is not None]
        if not vals:
            continue  # unrecognised payload shape — try next candidate
        worst = max(vals)
        # All three windows as remaining %, e.g. "↑100% ↓19% ↓1%"
        # (rolling=5h increase-type; weekly/monthly exhaust-type)
        segs = []
        if rolling is not None: segs.append(f"↑{max(0, 100 - rolling):.0f}%")
        if weekly is not None: segs.append(f"↓{max(0, 100 - weekly):.0f}%")
        if monthly is not None: segs.append(f"↓{max(0, 100 - monthly):.0f}%")
        exhaust = monthly if monthly is not None else weekly
        # earliest reset across the windows that carry one (headline reset)
        resets = [_oc_window_reset(w) for w in (rolling_w, weekly_w, monthly_w)]
        resets_at = min([r for r in resets if r > 0], default=0.0)
        return {"ok": True, "percent": round(worst, 1),
                "exhaust_percent": round(exhaust, 1) if exhaust is not None else None,
                "resets_at": resets_at,
                "detail": " ".join(segs)}

    if last_status == 404:
        return {"ok": False, "error": "endpoint not found"}
    return {"ok": False, "error": f"HTTP {last_status}" if last_status else "unreachable"}


def fetch_openai(cfg: dict) -> dict:
    """OpenAI legacy credit-grants balance (grants/usage based, not usage-based
    subscriptions). Showed only when a remaining balance exists."""
    key = resolve_key(["OPENAI_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "OPENAI_API_KEY"}
    try:
        d = api_get("https://api.openai.com/dashboard/billing/credit_grants",
                    {"Authorization": f"Bearer {key}", "Accept": "application/json",
                     "Referer": "https://platform.openai.com/", "Origin": "https://platform.openai.com"})
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", **({"needs_auth": True} if e.code in (401, 403) else {})}
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}
    avail = d.get("total_available")
    if avail is None:
        granted = d.get("total_granted"); used = d.get("total_used")
        if granted is not None and used is not None:
            avail = float(granted) - float(used)
    if avail is None:
        return {"ok": False, "error": "no wallet"}
    return {"ok": True, "balance": round(max(0.0, float(avail)), 2),
            "pct": None, "detail": f"${max(0.0, float(avail)):.2f}"}


def fetch_anthropic(cfg: dict) -> dict:
    """Anthropic exposes no wallet balance; surface the per-minute request
    rate-limit as a bounded wall from the /v1/models probe headers."""
    key = resolve_key(["ANTHROPIC_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "ANTHROPIC_API_KEY"}
    try:
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            "https://api.anthropic.com/v1/models",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "Accept": "application/json"})
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=10) as resp:
            h = resp.headers
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", **({"needs_auth": True} if e.code in (401, 403) else {})}
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}
    lim = h.get("anthropic-ratelimit-requests-limit")
    rem = h.get("anthropic-ratelimit-requests-remaining")
    if lim is None or rem is None:
        return {"ok": False, "error": "no rate-limit headers"}
    used = float(lim) - float(rem)
    return {"ok": True, "percent": round(used / float(lim) * 100, 1),
            "detail": f"RPM {int(used)}/{int(float(lim))}"}


def _header_limit_fetch(url: str, label: str, keyname: str, cfg: dict) -> dict:
    """Groq / Cerebras: rate-limit headers on the /models probe."""
    key = resolve_key([keyname], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": keyname}
    try:
        req = __import__("urllib.request", fromlist=["Request"]).Request(
            url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"})
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(req, timeout=10) as resp:
            h = resp.headers
    except HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}", **({"needs_auth": True} if e.code in (401, 403) else {})}
    except Exception as e:
        return {"ok": False, "error": str(e)[:60]}
    lim = h.get("x-ratelimit-limit-requests")
    rem = h.get("x-ratelimit-remaining-requests")
    if lim is None or rem is None:
        return {"ok": False, "error": "no rate-limit headers"}
    used = float(lim) - float(rem)
    return {"ok": True, "percent": round(used / float(lim) * 100, 1),
            "detail": f"{label} {int(used)}/{int(float(lim))}"}


def fetch_groq(cfg: dict) -> dict:
    return _header_limit_fetch("https://api.groq.com/openai/v1/models", "RPM", "GROQ_API_KEY", cfg)


def fetch_cerebras(cfg: dict) -> dict:
    return _header_limit_fetch("https://api.cerebras.ai/v1/models", "RPM", "CEREBRAS_API_KEY", cfg)


def fetch_moonshot(cfg: dict) -> dict:
    key = resolve_key(["MOONSHOT_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "MOONSHOT_API_KEY"}
    last = None
    for base in ("https://api.moonshot.ai", "https://api.moonshot.cn"):
        try:
            d = api_get(f"{base}/v1/users/me/balance",
                        {"Authorization": f"Bearer {key}", "Accept": "application/json"})
            break
        except HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (400, 401, 403):
                break
        except Exception as e:
            last = str(e)[:40]
            break
    else:
        return {"ok": False, "error": last or "unreachable"}
    body = d.get("data") if isinstance(d, dict) else {}
    if not isinstance(body, dict):
        body = d if isinstance(d, dict) else {}
    amt = body.get("available_balance", body.get("balance", body.get("total_balance")))
    if amt is None:
        return {"ok": False, "error": "empty"}
    return {"ok": True, "balance": round(float(amt), 2),
            "pct": None, "detail": f"{float(amt):.2f}"}


def fetch_minimax(cfg: dict) -> dict:
    key = resolve_key(["MINIMAX_API_KEY"], cfg.get("pool"), cfg.get("pool_index", 0))
    if not key:
        return {"ok": False, "error": "no key", "label": "MINIMAX_API_KEY"}
    last = None
    data = None
    for url in ("https://www.minimax.io/v1/token_plan/remains",
                "https://api.minimax.io/v1/token_plan/remains"):
        try:
            data = api_get(url, {"Authorization": f"Bearer {key}", "Accept": "application/json"})
            break
        except HTTPError as e:
            last = f"HTTP {e.code}"
        except Exception as e:
            last = str(e)[:40]
    if data is None:
        return {"ok": False, "error": last or "unreachable"}
    raw = data.get("data") if isinstance(data, dict) else None
    rows = raw.get("model_remains") if isinstance(raw, dict) and isinstance(raw.get("model_remains"), list) else [raw]
    best = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        total = row.get("current_interval_total_count") or row.get("currentIntervalTotalCount")
        left = row.get("current_interval_usage_count") or row.get("currentIntervalUsageCount")
        if total is None or left is None:
            continue
        used = float(total) - float(left)
        if total:
            best = round(used / float(total) * 100, 1)
            break
    if best is None:
        return {"ok": False, "error": "empty"}
    return {"ok": True, "percent": best, "detail": f"used {best}%"}


# Cloud providers with no public quota/wallet/rate-limit endpoint: still addable
# and key-configurable, but the chip reports no usage boundary.
def _no_quota(label: str):
    def _f(cfg: dict) -> dict:
        key = resolve_key([label], cfg.get("pool"), cfg.get("pool_index", 0))
        if not key:
            return {"ok": False, "error": "no key", "label": label}
        return {"ok": False, "error": "no public quota endpoint"}
    return _f


fetch_gemini = _no_quota("GEMINI_API_KEY")
fetch_huggingface = _no_quota("HUGGINGFACE_API_KEY")
fetch_mistral = _no_quota("MISTRAL_API_KEY")
fetch_qwen = _no_quota("DASHSCOPE_API_KEY")


# ── Dispatch ───────────────────────────────────────────────────────


FETCHERS = {
    "deepseek": fetch_deepseek, "glm": fetch_glm, "tavily": fetch_tavily,
    "grok": fetch_grok, "codex": fetch_codex, "opencode": fetch_opencode,
    "openrouter": fetch_openrouter,
    "openai": fetch_openai, "anthropic": fetch_anthropic,
    "groq": fetch_groq, "cerebras": fetch_cerebras,
    "moonshot": fetch_moonshot, "minimax": fetch_minimax,
    "gemini": fetch_gemini, "huggingface": fetch_huggingface,
    "mistral": fetch_mistral, "qwen": fetch_qwen,
}

PROVIDER_META = {
    "deepseek": {"name": "DeepSeek", "short": "DeepSeek", "icon": "database", "env": ["DEEPSEEK_API_KEY"]},
    "glm": {"name": "GLM (z.ai)", "short": "GLM", "icon": "hubot", "env": ["ZAI_API_KEY", "GLM_API_KEY"]},
    "tavily": {"name": "Tavily", "short": "Tavily", "icon": "search", "env": ["TAVILY_API_KEY"]},
    "grok": {"name": "Grok (xAI)", "short": "Grok", "icon": "comment", "env": []},
    "codex": {"name": "Codex (OpenAI)", "short": "Codex", "icon": "code", "env": []},
    "opencode": {"name": "OpenCode Go", "short": "Go", "icon": "terminal", "env": ["OPENCODE_GO_API_KEY"]},
    "openrouter": {"name": "OpenRouter", "short": "OR", "icon": "globe", "env": ["OPENROUTER_API_KEY"]},
    "openai": {"name": "OpenAI", "short": "OA", "icon": "cloud", "env": ["OPENAI_API_KEY"]},
    "anthropic": {"name": "Anthropic", "short": "AN", "icon": "comment-discussion", "env": ["ANTHROPIC_API_KEY"]},
    "groq": {"name": "Groq", "short": "GQ", "icon": "zap", "env": ["GROQ_API_KEY"]},
    "cerebras": {"name": "Cerebras", "short": "CB", "icon": "chip", "env": ["CEREBRAS_API_KEY"]},
    "moonshot": {"name": "Moonshot Kimi", "short": "MS", "icon": "moon", "env": ["MOONSHOT_API_KEY"]},
    "minimax": {"name": "MiniMax", "short": "MX", "icon": "symbol-numeric", "env": ["MINIMAX_API_KEY"]},
    "gemini": {"name": "Google Gemini", "short": "GM", "icon": "sparkle", "env": ["GEMINI_API_KEY"]},
    "huggingface": {"name": "Hugging Face", "short": "HF", "icon": "smiley", "env": ["HUGGINGFACE_API_KEY"]},
    "mistral": {"name": "Mistral", "short": "MI", "icon": "wind", "env": ["MISTRAL_API_KEY"]},
    "qwen": {"name": "Qwen", "short": "QW", "icon": "archive", "env": ["DASHSCOPE_API_KEY"]},
}


# ── API endpoints ──────────────────────────────────────────────────

class ProviderConfig(BaseModel):
    enabled: bool = False
    pool: list[str] = []
    pool_index: int = 0
    access_token: str = ""
    refresh_token: str = ""
    expires_at: float = 0
    client_id: str = ""
    email: str = ""
    reset_days: list = []   # per-key day-of-month (int 1-31 or None), index-aligned with pool

class ConfigUpdate(BaseModel):
    providers: dict[str, ProviderConfig] = {}
    order: list[str] = []
    poll_minutes: int | None = None
    remove: list[str] = []   # provider ids to delete entirely (rows + order)

@router.get("/status")
def get_status(only: set | None = None):
    """`only` limits live refetching to those pids (statusbar chip click).
    Other pids are served from cache or last-good, never refetched, so a
    single-chip refresh cannot be gated by unrelated slow providers."""
    cfg = _ingest_library(load_config())
    pcfg = cfg.get("providers", {})
    # Order results by the saved `order` list so the statusbar matches dialog order.
    saved_order = [p for p in (cfg.get("order") or []) if p in FETCHERS]
    ordered_ids = saved_order
    results = {}
    cfg_dirty = False

    def _work(pid: str) -> tuple[str, dict, bool]:
        """Fetch one provider. Returns (pid, result, cfg_dirty)."""
        fetcher = FETCHERS[pid]
        pconf = pcfg.get(pid, {})
        if not pconf.get("enabled", False):
            return pid, {"enabled": False}, False
        # oauth account pool: fetchers read the flat fields of the ACTIVE account
        oauth_pool = pid in ("grok", "codex")
        if oauth_pool:
            pconf = _materialize_oauth(pconf)
        # subscription renewal-day rotation (day passed -> switch to renewed key).
        # Runs before the cache check and its dirty flag is returned even when
        # the status itself comes from cache, so the switch always persists.
        pconf, reset_dirty = _maybe_reset_day_rotate(pid, pconf)
        if reset_dirty:
            pcfg[pid] = pconf
            _cache.pop(pid, None)   # force a fresh fetch with the new key
        cached = cached_status(pid)
        pool_n = len([k for k in (pconf.get("pool") or []) if k])
        acct_n = len(_oauth_accounts(pconf)) if oauth_pool else 0
        if cached is not None and not (
            (pid in ROTATABLE and pool_n > 1 and _exhausted(pid, cached))
            or (oauth_pool and acct_n > 1 and _exhausted(pid, cached))
        ):
            cached = dict(cached)
            cached.setdefault("quotas", _probe_quota_lines(cached))
            return pid, cached, reset_dirty
        if only is not None and pid not in only:
            # Not requested: never refetch. Serve last-good even if stale.
            if pid in _last_good:
                out = dict(_last_good[pid]); out["stale"] = True
                return pid, out, reset_dirty
            return pid, {"enabled": True, "id": pid, "ok": False,
                         "error": "not refreshed yet"}, reset_dirty
        try:
            status = fetcher(pconf)
            if status.get("ok", False):
                dirty = reset_dirty   # renewal-day rotation may have switched keys
                if pid in ROTATABLE:
                    status, pconf, rotated = _maybe_rotate(pid, pconf, status, fetcher)
                    if rotated:
                        pcfg[pid] = pconf
                        dirty = True
                elif oauth_pool:
                    status, pconf, rotated = _maybe_rotate_oauth(pid, pconf, status, fetcher)
                    if rotated:
                        pcfg[pid] = pconf
                        dirty = True
                status["enabled"] = True
                status["id"] = pid
                status["name"] = PROVIDER_META[pid]["name"]
                rem = _display_remaining(pid, status)
                if rem is not None:
                    status["remaining"] = rem
                status["quotas"] = _probe_quota_lines(status)
                status["pool_index"] = int(pconf.get("pool_index") or 0)
                status["pool_size"] = pool_n
                status["fetched_at"] = time.time()
                store_status(pid, status)
                proj = burn_projection(pid)
                if proj:
                    status["burn"] = proj
                return pid, status, dirty
            else:
                # Provider-level error (auth, no key, HTTP...). Transient/network errors
                # and any error before 3 repeats: keep serving last good data.
                err_text = str(status.get("error", ""))
                fallback = record_failure(pid)
                if _is_transient(err_text) or fallback is not None:
                    if fallback is not None:
                        return pid, fallback, False
                    return pid, {"enabled": True, "id": pid,
                                 "name": PROVIDER_META[pid]["name"],
                                 "ok": False, "error": err_text}, False
                else:
                    status["enabled"] = True
                    status["id"] = pid
                    status["name"] = PROVIDER_META[pid]["name"]
                    return pid, status, False
        except Exception as e:
            # Fetcher raised (network down etc). Before threshold: stale last-good.
            err_text = str(e)[:80]
            fallback = record_failure(pid) if _is_transient(err_text) else None
            if fallback is not None:
                return pid, fallback, False
            n = _fail_counts.get(pid, 0)
            if n < FAIL_THRESHOLD and pid in _last_good:
                out = dict(_last_good[pid]); out["stale"] = True
                return pid, out, False
            return pid, {"enabled": True, "id": pid, "ok": False, "error": err_text}, False

    # All providers in parallel — each hits a different host.
    with ThreadPoolExecutor(max_workers=max(1, len(ordered_ids))) as pool:
        for pid, result, dirty in pool.map(_work, ordered_ids):
            results[pid] = result
            cfg_dirty = cfg_dirty or dirty
    if cfg_dirty:
        src = cfg.get("providers") or {}
        def _m(c: dict) -> None:
            _merge_pool_fields(c, src, list(ROTATABLE))
            # oauth rotations: persist the rotated provider's oauth fields only
            for pid in ("grok", "codex"):
                src_p = src.get(pid) or {}
                if "account_index" in src_p:
                    prev = dict(c.get("providers", {}).get(pid) or {})
                    for f in ("account_index",) + _OAUTH_FIELDS:
                        if f in src_p:
                            prev[f] = src_p[f]
                    c["providers"][pid] = prev
        mutate_config(_m)
    return results

# Hermes config.yaml provider name -> plugin chip id. The active model's
# provider gets highlighted in the statusbar.
_HERMES_TO_PID = {
    "zai": "glm", "z_ai": "glm", "glm": "glm",
    "deepseek": "deepseek",
    "xai": "grok", "grok": "grok",
    "openai": "codex", "codex": "codex",
    "opencode": "opencode", "opencode-go": "opencode",
    "openrouter": "openrouter",
    "tavily": "tavily",
}


@router.get("/active")
def get_active():
    """Which provider backs Hermes' current default model. Best effort —
    unknown providers map to none."""
    import yaml  # hermes env has pyyaml
    try:
        with open(HERMES_HOME / "config.yaml", "r", encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        prov = str((y.get("model") or {}).get("provider") or "").strip().lower()
        model = str((y.get("model") or {}).get("default") or "")
        return {"provider": prov or None, "model": model or None,
                "pid": _HERMES_TO_PID.get(prov)}
    except Exception as e:
        return {"provider": None, "model": None, "pid": None, "error": str(e)[:80]}


@router.get("/meta")
def get_meta():
    # Per-provider flag: does an API key resolve from env/.env chain right now?
    try:
        cfg = load_config().get("providers", {})
    except Exception:
        cfg = {}
    out = {}
    for pid, meta in PROVIDER_META.items():
        m = dict(meta)
        try:
            m["has_env"] = bool(resolve_key(meta["env"], cfg.get(pid, {}).get("pool"))) if meta["env"] else False
        except Exception:
            m["has_env"] = False
        out[pid] = m
    return out

@router.get("/config")
def get_config():
    return load_config()

@router.post("/config")
def update_config(body: ConfigUpdate):
    def _m(cfg: dict) -> None:
        providers = cfg.setdefault("providers", {})
        secret_keep = ("access_token", "refresh_token", "email", "client_id", "issuer")
        skip = set(body.remove or [])
        for pid, pv in (body.providers or {}).items():
            if pid in skip:
                continue
            model = pv if isinstance(pv, ProviderConfig) else ProviderConfig(**pv)
            # Merge ONLY fields the caller actually sent: model_dump() would
            # include pydantic defaults (enabled=False, pool=[], pool_index=0)
            # and a partial save would silently disable the provider and wipe
            # its key pool. This bit a real config once already.
            incoming = model.model_dump(exclude_unset=True)
            if not incoming:
                continue
            prev = dict(providers.get(pid) or {})
            merged = {**prev, **incoming}
            for field in secret_keep:
                # freshest-token guard: a refresh may have rotated tokens after
                # the dialog read its copy. Never write an older/blank secret
                # over a newer one (expires_at is the clock).
                if field in ("access_token", "refresh_token") and not merged.get(field) and prev.get(field):
                    merged[field] = prev[field]
                elif not merged.get(field) and prev.get(field):
                    merged[field] = prev[field]
                elif (field in ("access_token", "refresh_token")
                      and merged.get(field) and prev.get(field)
                      and float(merged.get("expires_at") or 0) < float(prev.get("expires_at") or 0)):
                    merged[field] = prev[field]
            if not merged.get("expires_at") and prev.get("expires_at"):
                merged["expires_at"] = prev["expires_at"]
            # explicit logout: dialog sends empty tokens WITH expires_at=0.
            # With an account pool: drop the ACTIVE account; activate the next
            # one (if any) so logging out one account switches, not nukes.
            explicit_clear = False
            if incoming.get("expires_at") == 0 and not incoming.get("access_token"):
                accounts = [a for a in (prev.get("accounts") or []) if isinstance(a, dict)]
                if len(accounts) > 1:
                    drop = int(prev.get("account_index") or 0) % len(accounts)
                    accounts.pop(drop)
                    nxt = accounts[drop % len(accounts)]
                    merged["accounts"] = accounts
                    merged["account_index"] = drop % len(accounts)
                    for f in _OAUTH_FIELDS:
                        if f in nxt:
                            merged[f] = nxt[f]
                else:
                    merged["access_token"] = ""
                    merged["refresh_token"] = ""
                    merged["expires_at"] = 0
                    merged.pop("accounts", None)
                    merged.pop("account_index", None)
                    explicit_clear = True
            # account pool is backend-managed; a dialog save never touches it
            # (but an explicit logout clear must stick)
            if not explicit_clear and "accounts" in prev and "accounts" not in merged:
                merged["accounts"] = prev["accounts"]
            # reset_days: index-aligned with the saved pool. Pad/trim to the
            # incoming pool length; keep the backend's fired-months log.
            incoming_pool = merged.get("pool") or []
            days = list(incoming.get("reset_days") or [])
            days = [d if isinstance(d, int) and 1 <= d <= 31 else None for d in days]
            if len(days) < len(incoming_pool):
                days += [None] * (len(incoming_pool) - len(days))
            days = days[:len(incoming_pool)]
            if any(d is not None for d in days):
                merged["reset_days"] = days
            else:
                merged.pop("reset_days", None)
            if "reset_days_fired" in prev and "reset_days_fired" not in merged:
                merged["reset_days_fired"] = prev["reset_days_fired"]
            # Manual active-key switch (dialog radio): push the chosen key into
            # the Hermes env so the TUI/runtime picks it up immediately.
            if pid in ROTATABLE and "pool_index" in incoming:
                prev_idx = int(prev.get("pool_index") or 0)
                new_idx = int(merged.get("pool_index") or 0)
                pool = [k for k in (merged.get("pool") or []) if k]
                if new_idx != prev_idx and 0 <= new_idx < len(pool):
                    _apply_hermes_key(pid, pool[new_idx])
                    log.info("provider-status %s: manual key switch -> #%d, env updated",
                             pid, new_idx + 1)
            providers[pid] = merged
        cfg["providers"] = providers
        if body.remove:
            rm = [p for p in body.remove if p in providers]
            for p in rm:
                providers.pop(p, None)
            if rm:
                cfg["order"] = [p for p in (cfg.get("order") or []) if p not in rm]
        if body.order is not None:
            cfg["order"] = [p for p in body.order if p in FETCHERS]
        if body.poll_minutes is not None:
            cfg["poll_minutes"] = max(1, int(body.poll_minutes))
    mutate_config(_m)
    log.info("provider-status config saved: %s", sorted(load_config().get("providers", {})))
    with _cache_lock:
        _cache.clear()
    return {"ok": True}

class RefreshBody(BaseModel):
    providers: list[str] | None = None


@router.post("/refresh")
def force_refresh(body: RefreshBody | None = None):
    """Clear cache and re-fetch. With `providers`, only those pids are cleared
    and re-fetched (statusbar click refresh — only shown providers)."""
    pids: list[str] = []
    if body and body.providers:
        pids = [p for p in body.providers if p in FETCHERS]
    with _cache_lock:
        if pids:
            for p in pids:
                _cache.pop(p, None)
        else:
            _cache.clear()
    result = get_status(only=set(pids) if pids else None)
    if pids:
        result = {p: result[p] for p in result if p in pids}
    return result

class ProbeBody(BaseModel):
    provider: str = ""


# ── probe cache + background sweeper ───────────────────────────────
# The dialog used to probe every key on open, leaving all dots gray for the
# ~5s the sweep takes. Instead a background thread refreshes a cache every
# poll_minutes*5 minutes, and /probe reads from it when fresh enough.
_PROBE_FRESH_S = 120.0          # served-from-cache window after a sweep
_PROBE_SWEEP_MULT = 5           # sweep interval = poll_minutes * this


def _probe_sweep_all() -> dict:
    """Probe every enabled provider (every pool key) sequentially per provider,
    in parallel across providers. Returns {pid: probe-result}."""
    cfg = _ingest_library(load_config())
    out: dict[str, dict] = {}
    provs = cfg.get("providers") or {}
    pids = [pid for pid in FETCHERS if (provs.get(pid) or {}).get("enabled")]
    def _one(pid: str) -> tuple[str, dict]:
        return pid, _probe_one_provider(pid, cfg)
    with ThreadPoolExecutor(max_workers=max(1, len(pids))) as pool:
        for pid, res in pool.map(_one, pids):
            out[pid] = res
    return out


def _probe_quota_lines(status: dict) -> list[dict]:
    """Expose provider quota windows as remaining percentages for the dialog."""
    if not isinstance(status, dict):
        return []
    # Credit-based providers: the quota IS the dollar balance in the pool.
    if status.get("balance") is not None and status.get("ok"):
        try:
            return [{"label": "Credits", "display": f"${float(status['balance']):.2f}"}]
        except (TypeError, ValueError):
            pass
    labels = {"5h": "5-Hours", "wk": "Weekly", "weekly": "Weekly", "mo": "Monthly", "monthly": "Monthly"}
    out = []
    windows = status.get("windows")
    if isinstance(windows, list):
        for window in windows:
            if not isinstance(window, dict):
                continue
            key = str(window.get("label") or "").strip().lower()
            raw = window.get("pct")
            try:
                remaining = max(0.0, min(100.0, 100.0 - float(raw)))
            except (TypeError, ValueError):
                continue
            label = labels.get(key)
            if label:
                out.append({"label": label, "percent": round(remaining, 1)})
    if out:
        return out
    # Grok/Codex/OpenCode fetchers return compact detail arrows instead of
    # windows: ↑N% is 5h remaining; each ↓N% is weekly then monthly.
    compact = re.findall(r"([↑↓])\s*(\d+(?:\.\d+)?)%", str(status.get("detail") or ""))
    if compact:
        down = 0
        for arrow, num in compact:
            try:
                percent = max(0.0, min(100.0, float(num)))
            except ValueError:
                continue
            if arrow == "↑":
                out.append({"label": "5-Hours", "percent": round(percent, 1)})
            else:
                out.append({"label": "Weekly" if down == 0 else "Monthly", "percent": round(percent, 1)})
                down += 1
        if out:
            return out
    # Last resort: headline numeric fields (period used% or exhaust_percent).
    period = str(status.get("period") or "").lower()
    used = status.get("percent")
    exhaust = status.get("exhaust_percent")
    if used is not None and period not in ("weekly", "monthly"):
        try:
            out.append({"label": "5-Hours", "percent": round(max(0.0, min(100.0, 100.0 - float(used))), 1)})
        except (TypeError, ValueError):
            pass
    if exhaust is not None:
        try:
            out.append({"label": "Weekly", "percent": round(max(0.0, min(100.0, 100.0 - float(exhaust))), 1)})
        except (TypeError, ValueError):
            pass
    if not out and used is not None and period in ("weekly", "monthly"):
        try:
            out.append({"label": "Weekly" if period == "weekly" else "Monthly",
                        "percent": round(max(0.0, min(100.0, 100.0 - float(used))), 1)})
        except (TypeError, ValueError):
            pass
    return out


def _probe_one_provider(pid: str, cfg: dict) -> dict:
    """Probe every pool key of one provider. Keys fetch in parallel (each key
    hits the same host, but providers with large pools used to serialize into
    multi-second sweeps); results keep pool order."""
    pconf = dict((cfg.get("providers") or {}).get(pid) or {})
    fetcher = FETCHERS[pid]
    pool = [k for k in (pconf.get("pool") or []) if k]
    indexes = list(range(len(pool))) if pool else [0]

    def _one(idx: int) -> dict:
        trial = dict(pconf)
        trial["pool_index"] = idx
        try:
            st = fetcher(trial)
        except Exception as e:
            st = {"ok": False, "error": str(e)[:80]}
        classified = classify_tone(pid, st)
        return {
            "index": idx,
            "tone": classified["tone"],
            "reason": classified["reason"],
            "remaining": classified.get("remaining"),
            "quotas": _probe_quota_lines(st),
        }

    if len(indexes) == 1:
        out = [_one(indexes[0])]
    else:
        with ThreadPoolExecutor(max_workers=len(indexes)) as pool_exec:
            out = list(pool_exec.map(_one, indexes))
    return {"provider": pid, "keys": out}


_probe_cache: dict = {}          # pid -> {"result": ..., "swept_at": epoch}
_probe_pending: set[str] = set() # pids with an in-flight forced probe
_probe_lock = threading.Lock()


def _get_cached_probe(pid: str) -> dict | None:
    with _probe_lock:
        entry = _probe_cache.get(pid)
        if not entry:
            return None
        if time.time() - entry["swept_at"] > _PROBE_FRESH_S:
            return None
        return dict(entry["result"])


def _store_probe(pid: str, result: dict) -> None:
    with _probe_lock:
        _probe_cache[pid] = {"result": result, "swept_at": time.time()}


def _probe_sweeper_loop() -> None:
    """Daemon: keep the probe cache warm. First sweep at startup, then every
    poll_minutes*5 minutes (re-read from config so interval changes apply)."""
    while True:
        try:
            cfg = load_config()
            interval = max(60, int(cfg.get("poll_minutes") or 5) * _PROBE_SWEEP_MULT * 60)
            results = _probe_sweep_all()
            for pid, res in results.items():
                _store_probe(pid, res)
        except Exception:
            log.exception("provider-status probe sweeper error")
            interval = 300
        time.sleep(interval)


_probe_thread: threading.Thread | None = None


def _start_probe_sweeper() -> None:
    global _probe_thread
    if _probe_thread and _probe_thread.is_alive():
        return
    _probe_thread = threading.Thread(target=_probe_sweeper_loop, name="ps-probe-sweeper", daemon=True)
    _probe_thread.start()


@router.post("/probe")
def probe_keys(body: ProbeBody):
    """Queue a live per-key traffic light probe and return immediately. The
    fetch runs on a worker thread and lands in the probe cache; clients read
    /probe-cache (pending pids are marked) instead of holding this request
    open, so a slow provider can never stall a caller."""
    pid = str(body.provider or "").strip()
    if pid not in FETCHERS:
        return {"provider": pid, "keys": [], "error": "unknown provider"}
    with _probe_lock:
        if pid in _probe_pending:
            return {"provider": pid, "queued": True, "keys": []}
        _probe_pending.add(pid)

    def _run() -> None:
        try:
            cfg = _ingest_library(load_config())
            result = _probe_one_provider(pid, cfg)
            _store_probe(pid, result)
        except Exception:
            log.exception("provider-status probe failed: %s", pid)
        finally:
            with _probe_lock:
                _probe_pending.discard(pid)

    threading.Thread(target=_run, name=f"ps-probe-{pid}", daemon=True).start()
    return {"provider": pid, "queued": True, "keys": []}


@router.get("/probe-cache")
def probe_cache_ep():
    """Current cache state for all providers (dialog seeding + debug)."""
    with _probe_lock:
        now = time.time()
        out = {pid: {"result": e["result"], "age_s": round(now - e["swept_at"], 1)}
               for pid, e in _probe_cache.items()}
        for pid in _probe_pending:
            out.setdefault(pid, {"result": None, "age_s": None, "pending": True})
            out[pid]["pending"] = True
        return out


def _save_oauth(provider: str, result: dict, client_id: str, issuer: str) -> None:
    _upsert_oauth_account(provider, result, client_id, issuer,
                          email=str(result.get("email") or ""))

class DevicePollBody(BaseModel):
    device_code: str

@router.post("/grok/device/start")
def grok_device_start_ep():
    return _device_start("https://auth.x.ai", DEFAULT_CLIENT_ID, GROK_SCOPE)

@router.post("/grok/device/poll")
def grok_device_poll_ep(body: DevicePollBody):
    result = _device_poll("https://auth.x.ai", body.device_code, DEFAULT_CLIENT_ID)
    if result.get("ok"):
        _save_oauth("grok", result, DEFAULT_CLIENT_ID, "https://auth.x.ai")
    return result

@router.post("/codex/device/start")
def codex_device_start_ep():
    return _device_start(CODEX_ISSUER, CODEX_CLIENT_ID, CODEX_SCOPE)

@router.post("/codex/device/poll")
def codex_device_poll_ep(body: DevicePollBody):
    result = _device_poll(CODEX_ISSUER, body.device_code, CODEX_CLIENT_ID)
    if result.get("ok"):
        _save_oauth("codex", result, CODEX_CLIENT_ID, CODEX_ISSUER)
    return result

# ── Codex browser flow (authorization code + PKCE, localhost callback) ──
# OpenAI has no device endpoint and Cloudflare blocks server-side ones, so we do what
# the codex CLI does: open the authorize URL in the user's browser, catch the redirect
# on a local listener, exchange the code.

import base64
import hashlib
import secrets as _secrets

_codex_flow: dict = {}  # in-flight state: verifier -> {thread}

def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(_secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge

class CodexStartBody(BaseModel):
    port: int = 1455

_listener_state: dict = {}  # port -> {"code": str, "error": str}

def _run_listener(port: int) -> None:
    """Tiny HTTP catcher for the OAuth redirect. Runs until code arrives or 5 min."""
    import http.server
    from threading import Event

    done = Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import urlparse, parse_qs
            u = urlparse(self.path)
            if u.path == "/auth/callback":
                qs = parse_qs(u.query)
                _listener_state[str(port)] = {
                    "code": (qs.get("code") or [""])[0],
                    "error": (qs.get("error") or [""])[0],
                }
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<html><body><h2>Login complete.</h2>Return to Hermes.</body></html>")
                done.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *a):  # silence
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), Handler)
    srv.timeout = 5
    while not done.is_set() and time.time() - _listener_state.get(str(port), {}).get("start", time.time()) < 300:
        srv.handle_request()
    srv.server_close()

from threading import Thread as _Thread

@router.post("/codex/browser/start")
def codex_browser_start_ep(body: CodexStartBody):
    try:
        port = body.port
        verifier, challenge = _pkce_pair()
        redirect_uri = f"http://localhost:{port}/auth/callback"
        q = urlencode({
            "response_type": "code",
            "client_id": CODEX_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": CODEX_SCOPE,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": verifier[:16],
        })
        url = f"https://auth.openai.com/api/accounts/authorize?{q}"
        _codex_flow[str(port)] = {"verifier": verifier}
        _listener_state[str(port)] = {"code": "", "error": "", "start": time.time()}
        t = _Thread(target=_run_listener, args=(port,), daemon=True)
        t.start()
        return {"ok": True, "authorize_url": url, "redirect_uri": redirect_uri}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}

@router.get("/codex/browser/poll")
def codex_browser_poll_ep(port: int):
    st = _listener_state.get(str(port))
    if not st:
        return {"ok": False, "pending": True}
    if not st["code"]:
        return {"ok": False, "pending": True}
    flow = _codex_flow.pop(str(port), None)
    if not flow:
        return {"ok": False, "pending": True}
    try:
        disc = _oidc_discover(CODEX_ISSUER)
        ep = disc.get("token_endpoint", "https://auth.openai.com/api/accounts/oauth/token")
        d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded",
                          "Accept": "application/json"}, {
            "grant_type": "authorization_code",
            "code": st["code"],
            "client_id": CODEX_CLIENT_ID,
            "redirect_uri": f"http://localhost:{port}/auth/callback",
            "code_verifier": flow["verifier"],
        })
        if "access_token" not in d:
            return {"ok": False, "error": d.get("error", "token exchange failed")}
        _save_oauth("codex", {
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token", ""),
            "expires_in": d.get("expires_in", 3600),
        }, CODEX_CLIENT_ID, CODEX_ISSUER)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}

class CodexCallbackBody(BaseModel):
    port: int
    code: str = ""
    error: str = ""

@router.post("/codex/browser/callback")
def codex_browser_callback_ep(body: CodexCallbackBody):
    """The local listener received the redirect; exchange the code for tokens."""
    flow = _codex_flow.pop(str(body.port), None)
    if not flow:
        return {"ok": False, "error": "no login in progress"}
    if body.error or not body.code:
        return {"ok": False, "error": body.error or "no code in redirect"}
    try:
        disc = _oidc_discover(CODEX_ISSUER)
        ep = disc.get("token_endpoint", "https://auth.openai.com/api/accounts/oauth/token")
        d = api_post(ep, {"Content-Type": "application/x-www-form-urlencoded",
                          "Accept": "application/json"}, {
            "grant_type": "authorization_code",
            "code": body.code,
            "client_id": CODEX_CLIENT_ID,
            "redirect_uri": f"http://localhost:{body.port}/auth/callback",
            "code_verifier": flow["verifier"],
        })
        if "access_token" not in d:
            return {"ok": False, "error": d.get("error", "token exchange failed")}
        _save_oauth("codex", {
            "access_token": d["access_token"],
            "refresh_token": d.get("refresh_token", ""),
            "expires_in": d.get("expires_in", 3600),
        }, CODEX_CLIENT_ID, CODEX_ISSUER)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:150]}



# ── background probe sweeper autostart ─────────────────────────────
_start_probe_sweeper()
