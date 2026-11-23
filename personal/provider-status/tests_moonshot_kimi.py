"""Kimi Code membership keys and moonshot fetch error paths (issue #24).

An `sk-kimi-` key is a Kimi Code membership key: core routes it to
api.kimi.com/coding, while the Moonshot balance endpoint answers 401. The
fetcher must follow that route and must never fall through to an unassigned
`d` after an error. Standalone: python tests_moonshot_kimi.py
"""

from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError

PLUGIN = Path(__file__).resolve().parent
API_PATH = PLUGIN / "dashboard" / "plugin_api.py"

KIMI_PAYLOAD = {
    "limits": [{"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                "detail": {"limit": "100", "used": "100", "remaining": "0",
                           "resetTime": "2026-11-23T23:46:43.489099Z"}}],
    "usages": {
        "limit_5h": {"used_ratio": 1, "reset_time": "2026-11-23T23:46:43Z"},
        "limit_month_total": {"used_ratio": 0.6524, "reset_time": "2026-12-22T00:00:00Z"},
        "limit_month_code": {"used_ratio": 0.6495, "reset_time": "2026-12-22T00:00:00Z"},
    },
}

BALANCE_PAYLOAD = {"code": 0, "data": {"available_balance": 12.5}}


def load_api():
    spec = importlib.util.spec_from_file_location("provider_status_api_kimi_test", API_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch(mod, key, responses):
    """Stub the two seams; return (status, [(url, auth)], env names read)."""
    calls: list[tuple[str, str]] = []
    names_seen: list[list[str]] = []

    def resolve(names, pool=None, index=0):
        names_seen.append(list(names))
        return key

    def api_get(url, headers, timeout=10):
        calls.append((url, headers.get("Authorization")))
        n = len(calls) - 1
        behavior = responses[n] if n < len(responses) else responses[-1]
        if isinstance(behavior, Exception):
            raise behavior
        return behavior

    mod.resolve_key = resolve
    mod.api_get = api_get
    return mod.fetch_moonshot({}), calls, names_seen


def epoch(iso: str) -> float:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def main() -> None:
    mod = load_api()
    real_resolve = mod.resolve_key
    failures: list[str] = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    # 1. Membership key takes the coding route with the bearer key, first host.
    st, calls, names = fetch(mod, "sk-kimi-abc123", [KIMI_PAYLOAD])
    check("kimi ok", st.get("ok"), True)
    check("kimi url", [u for u, _ in calls], ["https://api.kimi.com/coding/v1/usages"])
    check("kimi auth", [a for _, a in calls], ["Bearer sk-kimi-abc123"])
    check("kimi percent", st.get("percent"), 65.2)
    check("kimi exhaust", st.get("exhaust_percent"), 65.2)
    check("kimi reset", st.get("resets_at"), epoch("2026-12-22T00:00:00Z"))
    check("kimi windows", [(w["label"], w["pct"]) for w in st["windows"]],
          [("5h", 100.0), ("mo", 65.2)])
    check("kimi remaining", mod._display_remaining("moonshot", st), 34.8)
    check("kimi dialog rows", mod._probe_quota_lines(st),
          [{"label": "5-Hours", "percent": 0.0}, {"label": "Monthly", "percent": 34.8}])
    check("kimi env names", names[0], ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "MOONSHOT_API_KEY"])

    # 2. HTTP error on the primary host falls back to the overseas host.
    st, calls, _ = fetch(mod, "sk-kimi-abc123", [
        HTTPError("https://api.kimi.com/coding/v1/usages", 503, "busy", None, None),
        KIMI_PAYLOAD,
    ])
    check("fallback ok", st.get("ok"), True)
    check("fallback urls", [u for u, _ in calls],
          ["https://api.kimi.com/coding/v1/usages", "https://api.kimi.ai/coding/v1/usages"])

    # 3. 401/403 is an auth problem, not a generic error.
    for code in (401, 403):
        st, calls, _ = fetch(mod, "sk-kimi-abc123", [
            HTTPError("https://api.kimi.com/coding/v1/usages", code, "no", None, None),
            HTTPError("https://api.kimi.ai/coding/v1/usages", code, "no", None, None),
        ])
        check(f"{code} ok", st.get("ok"), False)
        check(f"{code} needs_auth", st.get("needs_auth"), True)
        check(f"{code} error", st.get("error"), f"HTTP {code}")
        check(f"{code} hosts tried", len(calls), 2)

    # 4. Network errors return a status; no UnboundLocalError into the chip.
    st, calls, _ = fetch(mod, "sk-kimi-abc123", [OSError("connection refused")])
    check("network ok", st.get("ok"), False)
    check("network error", st.get("error"), "connection refused")
    check("network hosts", len(calls), 2)

    # 5. Weekly window and code-only monthly row.
    payload = {"usages": {
        "limit_5h": {"used_ratio": 0.1},
        "limit_7d": {"used_ratio": 0.2},
        "limit_month_code": {"used_ratio": 0.3, "reset_time": "2026-12-01T00:00:00Z"},
    }}
    st, _, _ = fetch(mod, "sk-kimi-abc123", [payload])
    check("code month ok", st.get("ok"), True)
    check("code month percent", st.get("percent"), 30.0)
    check("code month windows", [(w["label"], w["pct"]) for w in st["windows"]],
          [("5h", 10.0), ("wk", 20.0), ("mo", 30.0)])
    check("code month reset", st.get("resets_at"), epoch("2026-12-01T00:00:00Z"))

    # 6. A reported 0% stays a window; it is not a missing value.
    zero = {"usages": {"limit_month_total": {"used_ratio": 0,
                                             "reset_time": "2026-12-22T00:00:00Z"}}}
    st, _, _ = fetch(mod, "sk-kimi-abc123", [zero])
    check("zero percent", st.get("percent"), 0.0)
    check("zero window", [(w["label"], w["pct"]) for w in st["windows"]], [("mo", 0.0)])

    # 7. Other keys keep the Moonshot balance path unchanged.
    st, calls, _ = fetch(mod, "sk-paygo-key", [BALANCE_PAYLOAD])
    check("balance ok", st.get("ok"), True)
    check("balance amount", st.get("balance"), 12.5)
    check("balance url", [u for u, _ in calls], ["https://api.moonshot.ai/v1/users/me/balance"])
    check("balance auth", [a for _, a in calls], ["Bearer sk-paygo-key"])

    # 8. The two error arms used to `break` and leave `d` unassigned.
    st, calls, _ = fetch(mod, "sk-paygo-key", [
        HTTPError("https://api.moonshot.ai/v1/users/me/balance", 500, "boom", None, None),
    ])
    check("500 ok", st.get("ok"), False)
    check("500 error", st.get("error"), "HTTP 500")
    check("500 hosts", len(calls), 1)

    st, calls, _ = fetch(mod, "sk-paygo-key", [OSError("timed out")])
    check("balance network ok", st.get("ok"), False)
    check("balance network error", st.get("error"), "timed out")

    st, calls, _ = fetch(mod, "sk-paygo-key", [
        HTTPError("https://api.moonshot.ai/v1/users/me/balance", 401, "no", None, None),
        HTTPError("https://api.moonshot.cn/v1/users/me/balance", 401, "no", None, None),
    ])
    check("balance 401 needs_auth", st.get("needs_auth"), True)
    check("balance 401 error", st.get("error"), "HTTP 401")
    check("balance 401 hosts", len(calls), 2)

    # 9. Hermes-held Kimi keys make has_env true via PROVIDER_META.
    check("moonshot env names", mod.PROVIDER_META["moonshot"]["env"],
          ["KIMI_API_KEY", "KIMI_CODING_API_KEY", "MOONSHOT_API_KEY"])

    # 10. With no pool, a Hermes-held Kimi key wins; the no-key label names it.
    mod.resolve_key = real_resolve
    urls: list[str] = []

    def env_api_get(url, headers, timeout=10):
        urls.append(url)
        return KIMI_PAYLOAD

    mod.api_get = env_api_get
    mod._env_cache.clear()
    with patch.dict(os.environ, {"KIMI_API_KEY": "sk-kimi-FIXTURE",
                                 "MOONSHOT_API_KEY": "sk-paygo-FIXTURE"}):
        st = mod.fetch_moonshot({})
    check("kimi env priority", st.get("ok"), True)
    check("kimi env url", urls, ["https://api.kimi.com/coding/v1/usages"])
    mod._env_cache.clear()
    with patch.dict(os.environ, {"KIMI_API_KEY": "", "KIMI_CODING_API_KEY": "",
                                 "MOONSHOT_API_KEY": ""}):
        st = mod.fetch_moonshot({})
    check("no key label", st, {"ok": False, "error": "no key", "label": "KIMI_API_KEY"})
    js = (PLUGIN / "desktop" / "plugin.js").read_text(encoding="utf-8")
    check("renderer kimi env", "env: ['KIMI_API_KEY', 'KIMI_CODING_API_KEY', 'MOONSHOT_API_KEY']" in js, True)

    if failures:
        for line in failures:
            print("FAIL", line)
        raise SystemExit(1)
    print("Moonshot Kimi: 10 scenarios + error paths PASS")


if __name__ == "__main__":
    main()
