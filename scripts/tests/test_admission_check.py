"""The floor has to run for both package shapes.

A portable Agent Plugins v1 package carries `plugin.json` and no `plugin.yaml`.
Before this file existed, the checker stopped at `no plugin.yaml` and exited 2,
so the one rule set that a submission is checked against silently did not run
for those editions.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "admission_check.py"


def run(path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(path)],
        capture_output=True,
        text=True,
        timeout=120,
    )


def write_portable(root: Path, version: str = "0.2.0") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.json").write_text(
        json.dumps({"name": root.name, "version": version}), encoding="utf-8"
    )
    (root / "server.py").write_text(
        "import urllib.request\n\n\ndef get(url):\n    return urllib.request.urlopen(url, timeout=5).read()\n",
        encoding="utf-8",
    )


def write_hermes_plugin(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "plugin.yaml").write_text(
        "name: sample\nversion: 1.0.0\n", encoding="utf-8"
    )
    (root / "plugin.py").write_text(
        "from hermes_plugins import Plugin\n", encoding="utf-8"
    )


def test_portable_package_is_checked(tmp_path: Path) -> None:
    write_portable(tmp_path / "portable")
    result = run(tmp_path / "portable")
    assert result.returncode == 0, result.stdout
    assert "portable package" in result.stdout
    # The source scan still runs: the server's network call is reported.
    assert "third-party network call" in result.stdout


def test_directory_without_a_manifest_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    result = run(empty)
    assert result.returncode == 2
    assert "no plugin.yaml or plugin.json" in result.stdout


def test_plugin_yaml_edition_still_uses_its_own_rules(tmp_path: Path) -> None:
    write_hermes_plugin(tmp_path / "classic")
    (tmp_path / "classic" / "plugin.py").write_text(
        "from hermes_plugins import Plugin\n"
        "\n"
        "\n"
        "def register(ctx):\n"
        "    return ctx.get_secret('TOKEN')\n",
        encoding="utf-8",
    )
    result = run(tmp_path / "classic")
    assert result.returncode == 1, result.stdout
    assert "rule-11" in result.stdout
    assert "portable package" not in result.stdout
