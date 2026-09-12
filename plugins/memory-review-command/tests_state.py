"""Checks for memory-review-command state reads."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

API = Path(__file__).resolve().parent / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("mrc_plugin_api", API)
mod = importlib.util.module_from_spec(spec)
sys.modules["mrc_plugin_api"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_clean_home(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    state = mod.read_state(tmp_path)
    assert state == {
        "ok": True,
        "pending": 0,
        "memory_full": False,
        "user_full": False,
    }


def test_pending_and_full(tmp_path: Path) -> None:
    pending = tmp_path / "pending" / "memory"
    pending.mkdir(parents=True)
    (pending / "abcd1234.json").write_text("{}", encoding="utf-8")
    (pending / "efgh5678.json").write_text("{}", encoding="utf-8")
    (pending / "skip.txt").write_text("no", encoding="utf-8")
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


def test_memory_at_limit(tmp_path: Path) -> None:
    memories = tmp_path / "memories"
    memories.mkdir(parents=True)
    (memories / "MEMORY.md").write_text("m" * 2200, encoding="utf-8")
    state = mod.read_state(tmp_path)
    assert state["memory_full"] is True
    assert state["user_full"] is False
    assert state["pending"] == 0


if __name__ == "__main__":
    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as raw:
        root = Path(raw)
        test_clean_home(root / "clean")
        test_pending_and_full(root / "busy")
        test_memory_at_limit(root / "cap")
    print("ok")
