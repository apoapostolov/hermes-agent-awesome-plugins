"""Checks for memory-review state reads and decide."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

API = Path(__file__).resolve().parent / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("mrc_plugin_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["mrc_plugin_api"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def _write_pending(home: Path, pid: str, target: str = "memory") -> None:
    folder = home / "pending" / "memory"
    folder.mkdir(parents=True, exist_ok=True)
    rec = {
        "id": pid,
        "subsystem": "memory",
        "action": "batch",
        "summary": f"batch on {target}",
        "origin": "background_review",
        "payload": {
            "action": "batch",
            "target": target,
            "operations": [{"action": "add", "content": "x"}],
        },
    }
    (folder / f"{pid}.json").write_text(json.dumps(rec), encoding="utf-8")


def test_clean_home(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    state = mod.read_state(tmp_path)
    assert state["ok"] is True
    assert state["pending"] == 0
    assert state["items"] == []


def test_pending_and_full(tmp_path: Path) -> None:
    _write_pending(tmp_path, "abcd1234", "memory")
    _write_pending(tmp_path, "efgh5678", "user")
    (tmp_path / "pending" / "memory" / "skip.txt").write_text("no", encoding="utf-8")
    memories = tmp_path / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text("x" * 50, encoding="utf-8")
    (memories / "USER.md").write_text("y" * 2000, encoding="utf-8")
    (tmp_path / "config.yaml").write_text(
        "memory:\n  memory_char_limit: 9000\n  user_char_limit: 1375\n",
        encoding="utf-8",
    )
    state = mod.read_state(tmp_path)
    assert state["ok"] is True
    assert state["pending"] == 2
    assert state["memory_full"] is False
    assert state["user_full"] is True
    assert state["stores"]["memory"]["entries"] == 1
    assert state["stores"]["memory"]["pct"] == 1
    assert state["stores"]["user"]["entries"] == 1
    assert state["stores"]["user"]["pct"] == 100
    ids = [row["id"] for row in state["items"]]
    assert ids == ["abcd1234", "efgh5678"]
    assert state["items"][1]["target"] == "user"
    assert state["items"][1]["ops_detail"][0]["action"] == "add"
    assert "payload" not in state["items"][0]


def test_reject(tmp_path: Path) -> None:
    _write_pending(tmp_path, "abcd1234")
    _write_pending(tmp_path, "efgh5678")
    out = mod.decide("reject", ["abcd1234"], home=tmp_path)
    assert out["ok"] is True
    assert out["rejected"] == 1
    left = mod.list_items(tmp_path)
    assert [row["id"] for row in left] == ["efgh5678"]


def test_approve_mocked(tmp_path: Path) -> None:
    _write_pending(tmp_path, "abcd1234")
    _write_pending(tmp_path, "deadbeef")

    def apply_ok(payload, store):
        return {"success": True}

    out = mod.decide("approve", ["abcd1234"], home=tmp_path, apply_fn=apply_ok, store=object())
    assert out["ok"] is True
    assert out["applied"] == 1
    assert out["failed"] == []
    left = [row["id"] for row in mod.list_items(tmp_path)]
    assert left == ["deadbeef"]


def test_approve_failure_keeps_file(tmp_path: Path) -> None:
    _write_pending(tmp_path, "abcd1234")

    def apply_bad(payload, store):
        return {"success": False, "error": "over budget"}

    out = mod.decide("approve", ["abcd1234"], home=tmp_path, apply_fn=apply_bad, store=object())
    assert out["applied"] == 0
    assert out["failed"][0]["id"] == "abcd1234"
    assert mod.list_items(tmp_path)[0]["id"] == "abcd1234"


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as raw:
        root = Path(raw)
        test_clean_home(root / "clean")
        test_pending_and_full(root / "busy")
        test_reject(root / "drop")
        test_approve_mocked(root / "ok")
        test_approve_failure_keeps_file(root / "fail")
    print("ok")
