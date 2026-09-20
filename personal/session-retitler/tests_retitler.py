"""Local checks for session-retitler user-message counting."""
from __future__ import annotations

import importlib.util
import os
import sys

PLUGIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "__init__.py")
spec = importlib.util.spec_from_file_location("session_retitler_plugin", PLUGIN)
mod = importlib.util.module_from_spec(spec)
sys.modules["session_retitler_plugin"] = mod
assert spec.loader is not None
spec.loader.exec_module(mod)


def test_count_user_messages():
    history = [
        {"role": "user", "content": "first real prompt"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "second real prompt"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "[SYSTEM ignore me]"},
    ]
    assert mod._count_user_messages(history) == 2
    assert mod._count_user_messages(history, "second real prompt") == 2
    assert mod._count_user_messages(history, "third real prompt") == 3
    assert mod._count_user_messages([], "hello there") == 1
    assert mod._count_user_messages([], "[SYSTEM x]") == 0


if __name__ == "__main__":
    test_count_user_messages()
    print("ok")
