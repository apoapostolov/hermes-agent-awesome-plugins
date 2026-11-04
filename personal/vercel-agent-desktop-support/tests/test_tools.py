"""Tests for the desktop tools: argument rendering, envelope handling, live calls."""

from __future__ import annotations

import json
import subprocess

import pytest

from vercel_agent_desktop_support import agentdesktop_cli as cli
from vercel_agent_desktop_support import agentdesktop_schemas as schemas
from vercel_agent_desktop_support import agentdesktop_tools as tools


# --- schemas ---------------------------------------------------------------


def test_every_tool_has_a_schema_and_a_handler():
    for name in schemas.ALL:
        assert hasattr(tools, name), f"{name} has a schema but no handler"


def test_schemas_are_well_formed():
    for name, schema in schemas.ALL.items():
        assert schema["name"] == name
        assert len(schema["description"]) > 80, f"{name} needs a real description"
        params = schema["parameters"]
        assert params["type"] == "object"
        for prop, spec in params.get("properties", {}).items():
            assert "type" in spec, f"{name}.{prop} has no type"
            assert spec.get("description"), f"{name}.{prop} has no description"


def test_no_tool_silently_requests_headed():
    # physical input is opt-in per call, never a default
    for name, schema in schemas.ALL.items():
        headed = schema["parameters"].get("properties", {}).get("headed")
        if headed is not None:
            assert "default" not in headed or headed["default"] is False


# --- flag rendering --------------------------------------------------------


def test_flags_drop_unset_and_false():
    rendered = cli.flags(app="Discord.exe", compact=True, skeleton=False, window_id=None)
    assert rendered == ["--app=Discord.exe", "--compact"]


def test_flags_keep_zero_and_empty_string_is_dropped():
    assert cli.flags(amount=0) == ["--amount=0"]
    assert cli.flags(root="") == []


def test_build_argv_puts_positional_last():
    argv = cli.build_argv("bin", "set-value", ["--timeout-ms=5000"], ["@s1:e1", "hello"])
    assert argv == ["bin", "set-value", "--timeout-ms=5000", "@s1:e1", "hello"]


# --- envelope handling -----------------------------------------------------


def test_missing_binary_returns_an_envelope(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: None)
    payload = json.loads(cli.run("status"))
    assert payload["ok"] is False
    assert payload["error"]["code"] == "BINARY_NOT_FOUND"


def test_timeout_returns_a_safe_retry_envelope(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: "agent-desktop")

    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="agent-desktop", timeout=1)

    monkeypatch.setattr(cli.subprocess, "run", boom)
    payload = json.loads(cli.run("snapshot", timeout=1))
    assert payload["error"]["code"] == "TIMEOUT"
    assert payload["error"]["retry"] == "safe"


def test_oversized_tree_is_pruned_not_dropped(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: "agent-desktop")
    big = {
        "version": "2.5",
        "ok": True,
        "command": "snapshot",
        "data": {
            "snapshot_id": "s1",
            "tree": {"role": "window", "name": "w", "children": [{"role": "button", "name": "x" * 200, "ref_id": f"@s1:e{i}"} for i in range(400)]},
        },
    }

    class Done:
        returncode = 0
        stdout = json.dumps(big)
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: Done())
    payload = json.loads(cli.run("snapshot", max_chars=4000))
    assert payload["ok"] is True
    assert payload["data"]["snapshot_id"] == "s1"
    assert isinstance(payload["data"]["tree"], dict)
    assert payload["data"]["tree"]["role"] == "window"
    assert payload["data"]["tree_nodes_dropped"] > 0
    assert len(json.dumps(payload)) <= 4000


def test_non_json_output_is_reported_as_raw(monkeypatch):
    monkeypatch.setattr(cli, "resolve_binary", lambda: "agent-desktop")

    class Done:
        returncode = 1
        stdout = "error: unexpected argument"
        stderr = ""

    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: Done())
    payload = json.loads(cli.run("snapshot"))
    assert payload["ok"] is False
    assert payload["exit_code"] == 1
    assert "unexpected argument" in payload["raw"]


# --- argument validation ---------------------------------------------------


def test_act_rejects_an_unknown_action():
    payload = json.loads(tools.desktop_act({"action": "yeet", "ref": "@s1:e1"}))
    assert payload["error"]["code"] == "INVALID_ARGS"


def test_act_requires_a_ref():
    payload = json.loads(tools.desktop_act({"action": "click"}))
    assert payload["error"]["code"] == "INVALID_ARGS"


def test_act_requires_a_value_for_set_value():
    payload = json.loads(tools.desktop_act({"action": "set-value", "ref": "@s1:e1"}))
    assert payload["error"]["code"] == "INVALID_ARGS"


def test_window_rejects_an_unknown_action():
    payload = json.loads(tools.desktop_window({"action": "explode"}))
    assert payload["error"]["code"] == "INVALID_ARGS"


def test_batch_requires_commands():
    payload = json.loads(tools.desktop_batch({"commands": []}))
    assert payload["error"]["code"] == "INVALID_ARGS"


# --- live calls ------------------------------------------------------------

needs_binary = pytest.mark.skipif(cli.resolve_binary() is None, reason="agent-desktop is not installed")


@needs_binary
def test_live_status_reports_windows_permissions():
    payload = json.loads(tools.desktop_status({}))
    assert payload["ok"] is True
    assert payload["data"]["platform"] == "windows"
    assert payload["data"]["permissions"]["accessibility"]["state"] in {"granted", "unknown"}


@needs_binary
def test_live_apps_lists_something():
    payload = json.loads(tools.desktop_apps({}))
    assert payload["ok"] is True
    assert isinstance(payload["data"]["apps"], list)


@needs_binary
def test_live_snapshot_of_the_focused_window():
    payload = json.loads(tools.desktop_snapshot({"surface": "focused", "interactive_only": True, "compact": True}))
    # a session with no foreground window can legitimately have nothing to read
    if payload["ok"]:
        assert payload["data"]["snapshot_id"]
        assert isinstance(payload["data"]["tree"], dict)
        assert payload["data"]["tree"]["role"] == "window"
    else:
        assert payload["error"]["code"] in {"NO_FOREGROUND", "APP_NOT_FOUND", "NOT_FOUND", "SNAPSHOT_FAILED"}
