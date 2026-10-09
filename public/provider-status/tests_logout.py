from __future__ import annotations

import json
import sys
import types
from pathlib import Path

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


def test_logout_clears_every_account(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    pa.CONFIG_PATH.write_text(
        json.dumps(
            {
                "providers": {
                    "grok": {
                        "enabled": True,
                        "access_token": "tok-active",
                        "refresh_token": "ref-active",
                        "expires_at": 9_999_999_999,
                        "email": "first@example.com",
                        "account_index": 0,
                        "accounts": [
                            {
                                "access_token": "tok-active",
                                "refresh_token": "ref-active",
                                "expires_at": 9_999_999_999,
                                "email": "first@example.com",
                            },
                            {
                                "access_token": "tok-next",
                                "refresh_token": "ref-next",
                                "expires_at": 9_999_999_999,
                                "email": "second@example.com",
                            },
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    body = pa.ConfigUpdate(
        providers={
            "grok": pa.ProviderConfig(access_token="", expires_at=0),
        }
    )
    pa.update_config(body)
    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    grok = saved["providers"]["grok"]
    assert grok.get("access_token") == ""
    assert grok.get("refresh_token") == ""
    assert grok.get("expires_at") == 0
    assert grok.get("email") == ""
    assert "accounts" not in grok
    assert "account_index" not in grok
    # control: a string we know is absent must report absent
    assert "tok-next" not in json.dumps(grok)


def test_partial_save_keeps_account_pool(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    pa.CONFIG_PATH.write_text(
        json.dumps(
            {
                "providers": {
                    "grok": {
                        "enabled": True,
                        "access_token": "tok-active",
                        "refresh_token": "ref-active",
                        "expires_at": 9_999_999_999,
                        "email": "first@example.com",
                        "account_index": 0,
                        "accounts": [
                            {"access_token": "tok-active", "email": "first@example.com"},
                            {"access_token": "tok-next", "email": "second@example.com"},
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    body = pa.ConfigUpdate(
        providers={
            "grok": pa.ProviderConfig(enabled=True),
        }
    )
    pa.update_config(body)
    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    grok = saved["providers"]["grok"]
    assert len(grok["accounts"]) == 2
    assert grok["email"] == "first@example.com"


if __name__ == "__main__":
    import tempfile

    root = Path(tempfile.mkdtemp())
    logout = root / "logout"
    keep = root / "keep"
    logout.mkdir()
    keep.mkdir()
    test_logout_clears_every_account(logout)
    test_partial_save_keeps_account_pool(keep)
    print("logout: clear-all + keep-pool PASS")
