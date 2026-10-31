"""Regression tests for OAuth account pools (grok/codex).

Grok and Codex rotate the refresh token on every refresh, so an earlier build
matched accounts by refresh_token, appended a "new" account per refresh, and
grew one Grok login to 338 entries (336 already expired).
"""

from __future__ import annotations

import base64
import json
import os
import sys
import types
from pathlib import Path

os.environ["PI_PROVIDER_STATUS_NO_AUTOSTART"] = "1"

PERSONAL_API = Path(__file__).with_name("dashboard") / "plugin_api.py"


def _stub_host_modules() -> None:
    fastapi = types.ModuleType("fastapi")

    class APIRouter:
        def get(self, *args, **kwargs):
            def deco(fn):
                return fn
            return deco

        post = get

    fastapi.APIRouter = APIRouter
    sys.modules["fastapi"] = fastapi

    pydantic = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            self.__fields_set__ = set(kwargs)
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, exclude_unset=False):
            if exclude_unset:
                return {k: getattr(self, k) for k in self.__fields_set__}
            return {k: v for k, v in self.__dict__.items() if k != "__fields_set__"}

    pydantic.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic


def _load_api(tmp_path: Path):
    _stub_host_modules()
    sys.path.insert(0, str(PERSONAL_API.parent))
    import plugin_api as pa  # type: ignore

    pa.CONFIG_PATH = tmp_path / "config.json"
    pa.LIBRARY_PATH = tmp_path / "library.env"
    pa.HERMES_ENV = tmp_path / ".env"
    pa.PLUGIN_ROOT = tmp_path
    return pa


def _jwt(payload: dict) -> str:
    def enc(obj: dict) -> str:
        raw = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).decode().rstrip("=")

    return f"{enc({'alg': 'none', 'typ': 'JWT'})}.{enc(payload)}.sig"


def _token(sub: str, exp: int) -> str:
    return _jwt({"sub": sub, "principal_id": sub, "exp": exp,
                 "client_id": "b1a00492", "iss": "https://auth.x.ai"})


def test_refresh_rotation_updates_in_place(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    sub = "fe5f1953-38a9-45b3-a5c6-4f29cacbcdbd"
    for i, exp in enumerate((1_000, 2_000, 3_000)):
        pa._upsert_oauth_account(
            "grok",
            {"access_token": _token(sub, exp), "refresh_token": f"rt-{i}", "expires_in": 3600},
            "client-b1a00492", "https://auth.x.ai",
        )
    grok = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))["providers"]["grok"]
    assert len(grok["accounts"]) == 1, grok["accounts"]
    assert grok["accounts"][0]["refresh_token"] == "rt-2"
    assert grok["account_index"] == 0
    assert grok["refresh_token"] == "rt-2"


def test_distinct_accounts_stay_separate(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    first = "fe5f1953-38a9-45b3-a5c6-4f29cacbcdbd"
    second = "0f1c2d3e-0000-4000-8000-000000000001"
    pa._upsert_oauth_account("grok", {"access_token": _token(first, 1_000),
                                      "refresh_token": "rt-a", "expires_in": 3600},
                             "client-b1a00492", "https://auth.x.ai")
    pa._upsert_oauth_account("grok", {"access_token": _token(second, 2_000),
                                      "refresh_token": "rt-b", "expires_in": 3600},
                             "client-b1a00492", "https://auth.x.ai")
    grok = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))["providers"]["grok"]
    assert len(grok["accounts"]) == 2
    assert grok["account_index"] == 1
    assert grok["refresh_token"] == "rt-b"


def test_heal_collapses_bloated_pool(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    sub = "fe5f1953-38a9-45b3-a5c6-4f29cacbcdbd"
    accounts = [{"access_token": _token(sub, 1_000 + i * 1_000),
                 "refresh_token": f"rt-{i}", "expires_at": 1_000 + i * 1_000,
                 "client_id": "client-b1a00492", "issuer": "https://auth.x.ai"}
                for i in range(5)]
    pa.CONFIG_PATH.write_text(json.dumps({
        "providers": {
            "grok": {"enabled": True, "accounts": accounts, "account_index": 4,
                     **accounts[4]},
            "codex": {"enabled": True, "accounts": [dict(a) for a in accounts[:2]],
                      "account_index": 1, **accounts[1]},
        }
    }), encoding="utf-8")

    pa._heal_oauth_pools()

    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    grok = saved["providers"]["grok"]
    codex = saved["providers"]["codex"]
    assert len(grok["accounts"]) == 1, grok["accounts"]
    assert len(codex["accounts"]) == 1, codex["accounts"]
    assert grok["accounts"][0]["refresh_token"] == "rt-4"
    assert grok["account_index"] == 0
    assert grok["refresh_token"] == "rt-4"
    assert grok["expires_at"] == 5_000


def test_heal_leaves_clean_pool_untouched(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    sub = "fe5f1953-38a9-45b3-a5c6-4f29cacbcdbd"
    pa.CONFIG_PATH.write_text(json.dumps({
        "providers": {"grok": {"enabled": True, "account_index": 0,
                               "accounts": [{"access_token": _token(sub, 1_000),
                                             "refresh_token": "rt-0",
                                             "expires_at": 1_000}]}}
    }), encoding="utf-8")
    before = pa.CONFIG_PATH.read_text(encoding="utf-8")
    pa._heal_oauth_pools()
    assert pa.CONFIG_PATH.read_text(encoding="utf-8") == before


if __name__ == "__main__":
    import tempfile

    root = Path(tempfile.mkdtemp())
    cases = [
        test_refresh_rotation_updates_in_place,
        test_distinct_accounts_stay_separate,
        test_heal_collapses_bloated_pool,
        test_heal_leaves_clean_pool_untouched,
    ]
    for index, case in enumerate(cases):
        case_dir = root / f"{index}-{case.__name__}"
        case_dir.mkdir()
        case(case_dir)
    print(f"oauth accounts: {len(cases)}/{len(cases)} PASS")
