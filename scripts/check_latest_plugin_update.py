#!/usr/bin/env python3
"""Check the root README's Latest plugin update block against the release rule.

Fails when the block holds two entries for one plugin, an entry with no tag,
or an entry whose release tag is older than seven days.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = re.compile(r"^\*\*(.+?) (\d+\.\d+\.\d+)\*\*", re.MULTILINE)


def section(text: str) -> str:
    start = text.index("## Latest plugin update")
    end = text.index("\n## ", start + 1)
    return text[start:end]


def tag_dates() -> dict[str, date]:
    lines = subprocess.run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname:short) %(creatordate:unix)",
            "refs/tags",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    tags = {}
    for line in lines:
        name, _, epoch = line.rpartition(" ")
        try:
            tags[name] = datetime.fromtimestamp(int(epoch), timezone.utc).date()
        except (ValueError, OSError, OverflowError):
            continue
    return tags


def key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def main() -> int:
    body = section((ROOT / "README.md").read_text(encoding="utf-8"))
    tags = tag_dates()
    today = datetime.now(timezone.utc).date()
    problems: list[str] = []
    seen: dict[str, str] = {}

    for name, version in ENTRY.findall(body):
        k = key(name)
        if k in seen:
            problems.append(f"duplicate plugin: {name} ({seen[k]} and {version})")
            continue
        seen[k] = version
        matches = [
            tag
            for tag in tags
            if tag.endswith(f"-v{version}")
            and key(tag.rsplit("-v", 1)[0]) == k
        ]
        if not matches:
            problems.append(f"no tag for {name} {version}")
            continue
        newest = max(matches, key=lambda tag: tags[tag])
        age = (today - tags[newest]).days
        if age > 7:
            problems.append(
                f"{name} {version} released {age} days ago "
                f"(tag {newest}, {tags[newest]})"
            )

    if problems:
        print("Latest plugin update: FAIL")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"Latest plugin update: OK ({len(seen)} entries, within 7 days)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
