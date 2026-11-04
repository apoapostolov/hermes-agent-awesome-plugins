"""Fail when the committed style pack no longer matches rules.py.

The pack is generated, so a rule added to ``rules.py`` without regenerating it
leaves Vale judging an older list. This compares what the generator would write
against what is on disk and exits nonzero on any difference.

    python scripts/check_style_pack.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    generator = _load(HERE / "scripts" / "gen_style_pack.py", "vg_gen")
    rules = _load(HERE / "rules.py", "vg_rules")
    stale = []
    for path, text in generator.build(rules).items():
        target = HERE / path
        if not target.is_file() or target.read_text(encoding="utf-8") != text:
            stale.append(str(path))
    if stale:
        print("style pack is stale, run scripts/gen_style_pack.py:")
        for path in stale:
            print("  " + path)
        return 1
    print("style pack matches rules.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
