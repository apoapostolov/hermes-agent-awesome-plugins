"""Tests for the binary downloader: digests, archive safety, and the install path."""

from __future__ import annotations

import hashlib
import io
import json
import sys
import tarfile

import pytest

from hermes_agent_desktop import agentdesktop_cli as cli
from hermes_agent_desktop import agentdesktop_config as settings
from hermes_agent_desktop import agentdesktop_install as installer
from hermes_agent_desktop import agentdesktop_tools as tools

FAKE_BINARY = b"MZ" + b"\x00" * 64


def make_archive(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as handle:
        for name, payload in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


def test_pins_cover_both_windows_targets():
    pins = installer.PINS["1.0.2"]
    assert set(pins) == {"win32-x64", "win32-arm64"}
    for digest in pins.values():
        assert len(digest) == 64 and int(digest, 16) >= 0


def test_platform_key_maps_windows_targets(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "win32")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    assert installer.platform_key() == "win32-x64"
    monkeypatch.setattr(installer.platform, "machine", lambda: "ARM64")
    assert installer.platform_key() == "win32-arm64"


def test_platform_key_is_none_off_windows(monkeypatch):
    monkeypatch.setattr(installer.sys, "platform", "linux")
    assert installer.platform_key() is None


def test_extract_takes_only_the_expected_entry():
    payload = installer._extract_binary(make_archive({"agent-desktop.exe": FAKE_BINARY}))
    assert payload == FAKE_BINARY


def test_extract_refuses_an_extra_entry():
    archive = make_archive({"agent-desktop.exe": FAKE_BINARY, "evil.dll": b"MZ"})
    with pytest.raises(ValueError, match="unexpected entries"):
        installer._extract_binary(archive)


def test_extract_refuses_a_nested_path():
    archive = make_archive({"sub/agent-desktop.exe": FAKE_BINARY})
    with pytest.raises(ValueError, match="unexpected entries"):
        installer._extract_binary(archive)


def test_extract_refuses_a_non_executable():
    with pytest.raises(ValueError, match="not a Windows executable"):
        installer._extract_binary(make_archive({"agent-desktop.exe": b"#!/bin/sh\n"}))


def test_checksum_mismatch_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setattr(installer.sys, "platform", "win32")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(settings, "_settings", {**settings.DEFAULTS, "install_dir": str(tmp_path)})
    monkeypatch.setattr(installer, "_download", lambda url, timeout=120.0: make_archive({"agent-desktop.exe": FAKE_BINARY}))
    monkeypatch.setitem(installer.PINS, "1.0.2", {"win32-x64": "0" * 64, "win32-arm64": "0" * 64})

    outcome = installer.install()
    assert outcome["ok"] is False
    assert "checksum mismatch" in outcome["error"]
    assert not (tmp_path / "agent-desktop-win32-x64.exe").exists()


def test_install_writes_the_binary_and_proves_it(monkeypatch, tmp_path):
    archive = make_archive({"agent-desktop.exe": FAKE_BINARY})
    digest = hashlib.sha256(archive).hexdigest()
    monkeypatch.setattr(installer.sys, "platform", "win32")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(settings, "_settings", {**settings.DEFAULTS, "install_dir": str(tmp_path)})
    monkeypatch.setattr(installer, "_download", lambda url, timeout=120.0: archive)
    monkeypatch.setitem(installer.PINS, "1.0.2", {"win32-x64": digest, "win32-arm64": "0" * 64})
    monkeypatch.setattr(
        installer,
        "_probe",
        lambda binary, command, timeout=20.0: {
            "ok": True,
            "command": command,
            "data": {"version": "1.0.2", "platform": "windows"} if command == "version" else {"platform": "windows"},
        },
    )

    outcome = installer.install()
    assert outcome["ok"] is True
    assert outcome["checksum_source"] == "pinned"
    written = tmp_path / "agent-desktop-win32-x64.exe"
    assert written.read_bytes() == FAKE_BINARY
    assert (tmp_path / "agent-desktop-win32-x64.exe.sha256").read_text().strip() == digest
    assert [step["step"] for step in outcome["steps"]] == ["download", "checksum", "extract", "write", "verify"]


def test_second_install_reports_already_installed(monkeypatch, tmp_path):
    binary = tmp_path / "agent-desktop-win32-x64.exe"
    binary.write_bytes(FAKE_BINARY)
    monkeypatch.setattr(installer.sys, "platform", "win32")
    monkeypatch.setattr(installer.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(settings, "_settings", {**settings.DEFAULTS, "install_dir": str(tmp_path)})
    monkeypatch.setattr(installer, "verify", lambda binary=None: {"ok": True, "path": str(binary)})

    outcome = installer.install()
    assert outcome["ok"] is True
    assert outcome["already_installed"] is True


def test_resolve_binary_prefers_the_configured_path(monkeypatch, tmp_path):
    binary = tmp_path / "custom-agent-desktop.exe"
    binary.write_bytes(FAKE_BINARY)
    monkeypatch.setattr(settings, "_settings", {**settings.DEFAULTS, "bin_path": str(binary)})
    assert cli.resolve_binary() == str(binary)


def test_settings_update_ignores_blank_values(monkeypatch):
    monkeypatch.setattr(settings, "_settings", dict(settings.DEFAULTS))
    settings.update({"bin_path": "", "version": "9.9.9", "unknown": "x"})
    assert settings.get("bin_path") == ""
    assert settings.get("version") == "9.9.9"
    assert "unknown" not in settings.snapshot()


def test_hover_needs_explicit_headed():
    payload = json.loads(tools.desktop_act({"action": "hover", "ref": "@s1:e1"}))
    assert payload["error"]["code"] == "HEADED_REQUIRED"


def test_batch_process_outlives_its_own_budget(monkeypatch):
    seen = {}

    def fake_run(command, flags=(), positional=(), **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return json.dumps({"ok": True})

    monkeypatch.setattr(cli, "run", fake_run)
    tools.desktop_batch({"commands": [{"command": "status"}], "timeout_ms": 5000})
    assert seen["timeout"] == pytest.approx(35.0)


def test_apps_merges_both_halves(monkeypatch):
    replies = {
        "list-apps": json.dumps({"ok": True, "data": {"apps": [{"name": "Code.exe"}]}}),
        "list-windows": json.dumps({"ok": True, "data": [{"id": "w-1", "title": "Code"}]}),
    }
    monkeypatch.setattr(cli, "run", lambda command, *a, **k: replies[command])
    payload = json.loads(tools.desktop_apps({"include_windows": True}))
    assert payload["ok"] is True
    assert payload["data"]["apps"][0]["name"] == "Code.exe"
    assert payload["data"]["windows"][0]["id"] == "w-1"


def test_apps_surfaces_a_failed_half_instead_of_an_empty_list(monkeypatch):
    replies = {
        "list-apps": json.dumps({"ok": False, "error": {"code": "TIMEOUT", "message": "inventory timed out"}}),
        "list-windows": json.dumps({"ok": True, "data": []}),
    }
    monkeypatch.setattr(cli, "run", lambda command, *a, **k: replies[command])
    payload = json.loads(tools.desktop_apps({"include_windows": True}))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "TIMEOUT"
