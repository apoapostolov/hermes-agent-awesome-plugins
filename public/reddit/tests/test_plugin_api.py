"""Tests for the Desktop settings backend (dashboard/plugin_api.py).

Runs the real FastAPI router with the real plugin modules; only Reddit's network
calls are stubbed. Requires fastapi + httpx:
``uv run --with pytest --with fastapi --with httpx python -m pytest tests -q``
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PLUGIN_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PLUGIN_DIR.parent))

from reddit import client, login  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "reddit_plugin_api", PLUGIN_DIR / "dashboard" / "plugin_api.py"
)
plugin_api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plugin_api)

app = FastAPI()
app.include_router(plugin_api.router, prefix="/api/plugins/reddit")
api = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("REDDIT_CONFIG_FILE", raising=False)
    monkeypatch.delenv("REDDIT_TOKEN_FILE", raising=False)
    yield
    login._shutdown()


def test_status_reports_unconfigured(isolated_home):
    payload = api.get("/api/plugins/reddit/status").json()
    assert payload["configured"] is False
    assert payload["client_secret_set"] is False
    assert payload["logged_in"] is False
    assert payload["setup_url"] == "https://www.reddit.com/prefs/apps"
    assert "client_secret" not in payload


def test_config_saves_and_never_echoes_the_secret(monkeypatch, isolated_home):
    monkeypatch.setattr(
        client, "validate_app", lambda *a: {"app_token": "ok", "scopes": "*"}
    )
    response = api.post(
        "/api/plugins/reddit/config",
        json={
            "client_id": "web-client",
            "client_secret": "shhh-secret",
            "redirect_uri": "http://localhost:8080",
            "user_agent": "hermes-reddit/0.3 (by /u/tester)",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["validation"]["app_token"] == "ok"
    assert "shhh-secret" not in response.text
    assert client.load_config()["client_secret"] == "shhh-secret"

    status = api.get("/api/plugins/reddit/status").json()
    assert status["configured"] is True
    assert status["client_secret_set"] is True
    assert status["source"] == "config"
    assert "shhh-secret" not in json.dumps(status)


def test_config_rejects_bad_credentials(monkeypatch, isolated_home):
    def boom(*_args):
        raise client.RedditError("Reddit rejected those app credentials (401)")

    monkeypatch.setattr(client, "validate_app", boom)
    response = api.post(
        "/api/plugins/reddit/config",
        json={"client_id": "c", "client_secret": "s", "verify": True},
    )
    assert response.status_code == 400
    assert "rejected" in response.json()["detail"]


def test_config_requires_both_halves(isolated_home):
    response = api.post("/api/plugins/reddit/config", json={"client_id": "only"})
    assert response.status_code == 400
    assert "client secret" in response.json()["detail"].lower()


def test_login_start_returns_consent_url(monkeypatch, isolated_home):
    client.save_config({"client_id": "c", "client_secret": "s"})
    response = api.post("/api/plugins/reddit/login/start", json={"port": 0})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "awaiting_approval"
    assert "api/v1/authorize" in body["authorize_url"]
    assert body["redirect_uri"] == "http://localhost:8080"

    polled = api.get("/api/plugins/reddit/login/status").json()
    assert polled["status"] == "awaiting_approval"
    assert polled["listening"] is True


def test_login_status_reports_failure(monkeypatch, isolated_home):
    monkeypatch.setattr(login, "result", lambda: {"status": "failed", "error": "state mismatch"})
    assert api.get("/api/plugins/reddit/login/status").json()["error"] == "state mismatch"


def test_logout_clears_the_token(isolated_home):
    client.save_token({"refresh_token": "rt", "username": "tester"})
    response = api.post("/api/plugins/reddit/logout").json()
    assert response["token_removed"] is True
    assert client.load_token() == {}


def test_identity_without_token_is_not_an_error(isolated_home):
    payload = api.get("/api/plugins/reddit/identity").json()
    assert payload["logged_in"] is False
    assert "Log in" in payload["hint"]


def test_desktop_plugin_is_valid_esm(tmp_path):
    """The settings page ships as raw ESM the Desktop runtime imports."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    source = PLUGIN_DIR / "desktop" / "plugin.js"
    target = tmp_path / "plugin.mjs"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    result = subprocess.run([node, "--check", str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "registerSettingsPage" in target.read_text(encoding="utf-8")
