"""Guard the public edition's credential rules.

The 1.6.x line re-enabled vendor-store reads, token refresh and Hermes config
writes that the listed 1.5.12 pin had stubbed out. Every case below asserts a
file or env var the plugin must NOT touch, so a future feature that turns one
back on fails here instead of in review.

Run: python tests_public_edition.py
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from tests_logout import _load_api


def test_token_refresh_is_disabled(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    out = pa._token_refresh("https://auth.x.ai", "refresh-token", "client-id")
    assert out.get("ok") is False
    assert out.get("error") == "automatic token refresh disabled"


def test_vendor_cli_auth_file_is_ignored(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    home = tmp_path / "home"
    (home / ".grok").mkdir(parents=True)
    (home / ".grok" / "auth.json").write_text(
        json.dumps(
            {
                "https://auth.x.ai": {
                    "key": "cli-access-token",
                    "refresh_token": "cli-refresh-token",
                    "expires_at": "2999-01-01T00:00:00Z",
                }
            }
        ),
        encoding="utf-8",
    )
    before = (os.environ.get("HOME"), os.environ.get("USERPROFILE"))
    os.environ["HOME"] = str(home)
    os.environ["USERPROFILE"] = str(home)
    try:
        assert pa._cli_grok_entry() is None
    finally:
        for name, value in zip(("HOME", "USERPROFILE"), before):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def test_apply_helpers_write_no_env(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    pa._apply_hermes_key("deepseek", "sk-live")
    pa._apply_hermes_pool("deepseek", ["sk-a", "sk-b"])
    assert not pa.HERMES_ENV.exists()
    assert "DEEPSEEK_API_KEY" not in os.environ


def test_config_save_writes_no_env_or_hermes_config(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    pa.HERMES_HOME = tmp_path
    body = pa.ConfigUpdate(
        providers={
            "deepseek": pa.ProviderConfig(
                enabled=True,
                pool=["sk-a", "sk-b"],
                pool_index=1,
                pool_strategy="round_robin",
            )
        },
        order=["deepseek"],
        apply_hermes_env=True,
    )
    pa.update_config(body)
    assert not pa.HERMES_ENV.exists()
    assert not (tmp_path / "config.yaml").exists()
    saved = json.loads(pa.CONFIG_PATH.read_text(encoding="utf-8"))
    assert saved["providers"]["deepseek"]["pool"] == ["sk-a", "sk-b"]
    assert saved["providers"]["deepseek"]["pool_index"] == 1


def test_rotation_records_pool_index_without_env_write(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)

    def fetcher(conf: dict) -> dict:
        return {"ok": True, "percent": 10.0 if conf.get("pool_index") == 1 else 99.5}

    pconf = {"enabled": True, "pool": ["sk-a", "sk-b"], "pool_index": 0}
    status, pconf, rotated = pa._maybe_rotate(
        "deepseek", pconf, {"ok": True, "percent": 99.5}, fetcher
    )
    assert rotated is True
    assert pconf["pool_index"] == 1
    assert not pa.HERMES_ENV.exists()


def test_ingest_library_copies_nothing(tmp_path: Path) -> None:
    pa = _load_api(tmp_path)
    pa.HERMES_ENV.write_text("DEEPSEEK_API_KEY=sk-secret\n", encoding="utf-8")
    cfg = {"providers": {}}
    out = pa._ingest_library(cfg)
    assert out is cfg
    assert not (tmp_path / "library.env").exists()


if __name__ == "__main__":
    root = Path(tempfile.mkdtemp())
    for i, case in enumerate(
        (
            test_token_refresh_is_disabled,
            test_vendor_cli_auth_file_is_ignored,
            test_apply_helpers_write_no_env,
            test_config_save_writes_no_env_or_hermes_config,
            test_rotation_records_pool_index_without_env_write,
            test_ingest_library_copies_nothing,
        )
    ):
        work = root / f"case{i}"
        work.mkdir()
        case(work)
    print("public edition: credential + config write guards PASS")
