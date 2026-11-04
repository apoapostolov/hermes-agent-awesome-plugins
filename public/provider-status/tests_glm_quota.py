"""GLM quota parsing, and the public chip's multi-window detail.

The public edition puts GLM's burst and weekly windows on the status-bar chip,
so `fetch_glm` must send the same remaining-percent arrow detail `fetch_opencode`
sends. This pins both halves: the payload shapes z.ai has returned, and the chip
convention that turns the leading arrow back into a used percentage.

Standalone: python tests_glm_quota.py
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.error import HTTPError

PLUGIN = Path(__file__).resolve().parent
API_PATH = PLUGIN / "dashboard" / "plugin_api.py"
PLUGIN_JS = PLUGIN / "desktop" / "plugin.js"

# Two rows are all z.ai sends on a Coding Plan: 5h (unit 3) and weekly (unit 6).
CREDIT_LIMIT_2ROW = {
    "success": True,
    "data": {
        "level": "pro",
        "limits": [
            {"type": "CREDIT_LIMIT", "unit": 3, "number": 5, "usage": 12000,
             "currentValue": 663, "remaining": 11336, "percentage": 5,
             "nextResetTime": 1791000052479},
            {"type": "CREDIT_LIMIT", "unit": 6, "number": 1, "usage": 60000,
             "currentValue": 49223, "remaining": 10776, "percentage": 82,
             "nextResetTime": 1791114787983},
        ],
    },
}

# The pre-rename shape, plus the monthly row some plans do return.
TOKENS_TIME_3ROW = {
    "success": True,
    "data": {
        "limits": [
            {"type": "TOKENS_LIMIT", "unit": 3, "percentage": 12, "nextResetTime": 1791000052479},
            {"type": "TOKENS_LIMIT", "unit": 4, "percentage": 40},
            {"type": "TIME_LIMIT", "unit": 5, "percentage": 88},
        ],
    },
}

# Reported, but nothing used yet: 0 must stay a reported window, not a default.
CREDIT_LIMIT_UNUSED = {
    "success": True,
    "data": {"limits": [
        {"type": "CREDIT_LIMIT", "unit": 3, "percentage": 0},
        {"type": "CREDIT_LIMIT", "unit": 6, "percentage": 0},
    ]},
}

EMPTY_LIMITS = {"success": True, "data": {"limits": []}}
UNKNOWN_TYPE = {"success": True, "data": {"limits": [
    {"type": "MYSTERY_LIMIT", "unit": 3, "percentage": 44},
]}}


def load_api():
    spec = importlib.util.spec_from_file_location("provider_status_api_glm_test", API_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def fetch(mod, payload=None, error=None):
    mod.resolve_key = lambda names, pool=None, index=0: "test-key"

    def api_get(url, headers, timeout=10):
        if error is not None:
            raise error
        return payload

    mod.api_get = api_get
    return mod.fetch_glm({})


def chip_segments(detail: str):
    """The chip's `multi` branch, reduced to what it displays.

    The backend sends remaining for every arrow; the leading ↑ becomes a used
    percentage and each ↓ stays remaining.
    """
    shown = []
    for seg in str(detail).split():
        arrow, payload = seg[0], seg[1:]
        value = float(payload.rstrip("%"))
        shown.append(("used", round(100 - value)) if arrow == "↑" else ("remaining", round(value)))
    return shown


def main() -> None:
    mod = load_api()
    failures: list[str] = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r}, want {want!r}")

    st = fetch(mod, CREDIT_LIMIT_2ROW)
    check("2row percent", st.get("percent"), 5)
    check("2row exhaust", st.get("exhaust_percent"), 82)
    check("2row detail", st.get("detail"), "↑95% ↓18%")
    check("2row windows", [(w["label"], w["pct"], w["direction"]) for w in st["windows"]],
          [("5h", 5, "increase"), ("wk", 82, "exhaust")])
    check("2row reset", st.get("resets_at"), 1791000052.479)
    check("2row chip", chip_segments(st["detail"]), [("used", 5), ("remaining", 18)])

    st = fetch(mod, TOKENS_TIME_3ROW)
    check("3row detail", st.get("detail"), "↑88% ↓60% ↓12%")
    check("3row exhaust", st.get("exhaust_percent"), 88)
    check("3row windows", [w["label"] for w in st["windows"]], ["5h", "wk", "mo"])
    check("3row chip", chip_segments(st["detail"]),
          [("used", 12), ("remaining", 60), ("remaining", 12)])

    st = fetch(mod, CREDIT_LIMIT_UNUSED)
    check("unused percent", st.get("percent"), 0)
    check("unused detail", st.get("detail"), "↑100% ↓100%")
    check("unused windows", [w["label"] for w in st["windows"]], ["5h", "wk"])

    # No reported window: no segment, no headline key, and the chip's
    # `status?.detail` gate stays false so no junk label is drawn.
    for name, payload in (("empty", EMPTY_LIMITS), ("unknown", UNKNOWN_TYPE)):
        st = fetch(mod, payload)
        check(f"{name} detail", st.get("detail"), "")
        check(f"{name} windows", st.get("windows"), [])
        check(f"{name} percent omitted", "percent" in st, False)
        check(f"{name} chip gate", bool(st.get("detail")), False)

    st = fetch(mod, error=HTTPError("https://api.z.ai/", 500, "boom", None, None))
    check("http error ok", st.get("ok"), False)
    check("http error message", st.get("error"), "HTTP 500")

    st = fetch(mod, {"success": False, "msg": "unauthorized"})
    check("api error ok", st.get("ok"), False)
    check("api error message", st.get("error"), "unauthorized")

    # Both halves must be in place: an arrow detail nothing renders is as
    # useless as an allowlist entry with nothing to split.
    source = PLUGIN_JS.read_text(encoding="utf-8")
    if "id === 'opencode' || id === 'codex' || id === 'glm') && status?.detail" not in source:
        failures.append("chip: glm is not on the multi-window allowlist")
    if '"detail": "5h"' in API_PATH.read_text(encoding="utf-8"):
        failures.append("api: the bare '5h' detail is back")

    if failures:
        for line in failures:
            print("FAIL", line)
        raise SystemExit(1)
    print("GLM quota: 6 payload shapes + chip convention + allowlist PASS")


if __name__ == "__main__":
    main()
