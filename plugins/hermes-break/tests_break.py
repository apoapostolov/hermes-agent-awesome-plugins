"""Local checks for hermes-break rewrite helpers."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")
spec = importlib.util.spec_from_file_location("hermes_break_plugin", PLUGIN)
mod = importlib.util.module_from_spec(spec)
sys.modules["hermes_break_plugin"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_fmt():
    assert mod._fmt_duration(900) == "0s"
    assert mod._fmt_duration(4000) == "4s"
    assert mod._fmt_duration(65000) == "1m05s"


def test_rewrite_break():
    text = mod._rewrite(
        {
            "name": "terminal",
            "args": {"command": "sleep 999"},
            "started_at": time.monotonic() - 12,
            "hint": "try page=1",
            "again": False,
        },
        "partial",
    )
    assert "Broken by /break" in text
    assert "Do not retry" in text
    assert "try page=1" in text
    assert "partial" in text
    assert "Partial output (last 8KB):" in text


def test_salvage_truncates():
    blob = "x" * (mod.SALVAGE_MAX + 50)
    out = mod._salvage(blob)
    assert len(out) == mod.SALVAGE_MAX
    assert out == blob[-mod.SALVAGE_MAX:]


def test_rewrite_again():
    text = mod._rewrite(
        {
            "name": "terminal",
            "args": {"command": "curl x"},
            "started_at": time.monotonic() - 3,
            "hint": "add a 30s timeout",
            "again": True,
        },
        "",
    )
    assert "Broken by /again" in text
    assert "Reissue this exact call once" in text
    assert "curl x" in text
    assert "add a 30s timeout" in text


def test_idle_commands():
    assert "Nothing in flight" in mod._handle_break("")
    assert "normal message" in mod._handle_break("hello")
    assert "Nothing in flight to reissue" in mod._handle_again("")


def test_oldest_break_without_children():
    with mod._lock:
        mod._inflight.clear()
        mod._broken.clear()
    mod._on_pre_tool_call(tool_name="web_search", tool_call_id="tc-test", args={"query": "x"})
    msg = mod._break_oldest(hint="stop", again=False)
    assert "Nothing in flight" in msg
    assert mod._on_transform_tool_result(tool_call_id="tc-test", result="hi") is None
    mod._on_post_tool_call(tool_call_id="tc-test")


def test_status_payload():
    with mod._lock:
        mod._inflight.clear()
        mod._broken.clear()
        mod._again_by_fp.clear()
    idle = json.loads(mod._handle_status(""))
    assert idle["inflight"] is False
    mod._on_pre_tool_call(tool_name="web_search", tool_call_id="ws-1", args={"query": "x"})
    assert json.loads(mod._handle_status(""))["inflight"] is False
    mod._on_post_tool_call(tool_call_id="ws-1")
    mod._on_pre_tool_call(tool_name="terminal", tool_call_id="st-1", args={"command": "sleep 180"})
    shown = json.loads(mod._handle_status(""))
    assert shown["inflight"] is True
    assert shown["name"] == "terminal"
    assert "sleep 180" in shown["label"]
    assert shown["id"] == "st-1"
    assert len(shown["tools"]) == 1
    assert shown["again_disabled"] is False
    mod._on_post_tool_call(tool_call_id="st-1")
    assert json.loads(mod._handle_status(""))["inflight"] is False


def test_newest_is_default():
    with mod._lock:
        mod._inflight.clear()
        mod._broken.clear()
        mod._again_by_fp.clear()
    mod._on_pre_tool_call(tool_name="terminal", tool_call_id="old", args={"command": "sleep 1"})
    time.sleep(0.02)
    mod._on_pre_tool_call(tool_name="terminal", tool_call_id="new", args={"command": "sleep 2"})
    shown = json.loads(mod._handle_status(""))
    assert shown["id"] == "new"
    assert [row["id"] for row in shown["tools"]] == ["new", "old"]
    broke = mod._handle_break("")
    assert "sleep 2" in broke or "terminal" in broke
    assert "new" in mod._broken
    mod._on_post_tool_call(tool_call_id="old")
    mod._on_post_tool_call(tool_call_id="new")


def test_again_cap():
    with mod._lock:
        mod._inflight.clear()
        mod._broken.clear()
        mod._again_by_fp.clear()
    mod._on_pre_tool_call(tool_name="terminal", tool_call_id="st-1", args={"command": "sleep 180"})
    first = mod._handle_again("")
    second = mod._handle_again("")
    third = mod._handle_again("")
    assert "Broke" in first
    assert "Broke" in second
    assert "twice" in third.lower()
    status = json.loads(mod._handle_status(""))
    assert status["again_disabled"] is True
    assert status["again_count"] == 2
    broke = mod._handle_break("")
    assert "Broke" in broke
    mod._on_post_tool_call(tool_call_id="st-1")


def test_parse_args():
    assert mod._parse_args("") == (None, None)
    assert mod._parse_args("try page=1") == (None, "try page=1")
    assert mod._parse_args("--id tc-1") == ("tc-1", None)
    assert mod._parse_args("--id tc-1 add timeout") == ("tc-1", "add timeout")


def test_descendants_of_self():
    kids = mod._descendants(os.getpid())
    assert isinstance(kids, list)


if __name__ == "__main__":
    test_fmt()
    test_rewrite_break()
    test_salvage_truncates()
    test_rewrite_again()
    test_idle_commands()
    test_oldest_break_without_children()
    test_parse_args()
    test_descendants_of_self()
    test_status_payload()
    test_newest_is_default()
    test_again_cap()
    print("ok")
