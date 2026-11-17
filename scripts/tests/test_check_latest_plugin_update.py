#!/usr/bin/env python3
"""Dependency-free tests for scripts/check_latest_plugin_update.py.

Each case builds a throwaway git repo with real tags, then runs the shipped
checker against it. That exercises the git date lookup as well as the rule.
Run from the repo root with:

    python3 -m unittest discover -s scripts/tests -t scripts -v
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHECKER = Path(__file__).resolve().parents[1] / "check_latest_plugin_update.py"


class CheckerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(CHECKER, self.root / "scripts" / CHECKER.name)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        self.today = datetime.now(timezone.utc).date()

    def tearDown(self):
        self.tmp.cleanup()

    def _git(self, *args, when=None):
        env = os.environ.copy()
        if when is not None:
            env["GIT_AUTHOR_DATE"] = when
            env["GIT_COMMITTER_DATE"] = when
        subprocess.run(
            ["git", *args], cwd=self.root, env=env, check=True, capture_output=True
        )

    def _write(self, *entries):
        body = "## Latest plugin update\n" + "\n\n".join(entries) + "\n\n## In the app\n"
        (self.root / "README.md").write_text(body, encoding="utf-8")

    def _commit(self, when):
        self._git("add", "README.md")
        self._git("commit", "-q", "-m", "update", when=when)

    def _run(self):
        proc = subprocess.run(
            [sys.executable, "scripts/check_latest_plugin_update.py"],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        return proc.returncode, proc.stdout + proc.stderr

    def _fresh_commit_and_tag(self, path):
        self._commit(f"{self.today.isoformat()}T12:00:00+00:00")
        self._git("tag", path)

    def test_fresh_entry_passes(self):
        self._write("**Fresh Plugin 1.0.0** does a thing.")
        self._fresh_commit_and_tag("fresh-plugin-v1.0.0")
        code, out = self._run()
        self.assertEqual(code, 0, out)
        self.assertIn("OK (1 entries", out)

    def test_second_entry_for_same_plugin_fails(self):
        self._write(
            "**Fresh Plugin 1.0.0** does a thing.",
            "**Fresh Plugin 1.0.1** does another thing.",
        )
        self._fresh_commit_and_tag("fresh-plugin-v1.0.0")
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("duplicate plugin: Fresh Plugin", out)

    def test_entry_with_no_tag_fails(self):
        self._write(
            "**Fresh Plugin 1.0.0** does a thing.",
            "**Ghost Plugin 2.0.0** was never tagged.",
        )
        self._fresh_commit_and_tag("fresh-plugin-v1.0.0")
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("no tag for Ghost Plugin 2.0.0", out)

    def test_entry_older_than_seven_days_fails(self):
        old = self.today - timedelta(days=30)
        self._write("**Old Plugin 1.0.0** shipped long ago.")
        self._commit(f"{old.isoformat()}T12:00:00+00:00")
        self._git("tag", "old-plugin-v1.0.0")
        code, out = self._run()
        self.assertEqual(code, 1, out)
        self.assertIn("released 30 days ago", out)

    def test_entry_exactly_seven_days_old_passes(self):
        boundary = self.today - timedelta(days=7)
        self._write("**Edge Plugin 1.0.0** is on the boundary.")
        self._commit(f"{boundary.isoformat()}T12:00:00+00:00")
        self._git("tag", "edge-plugin-v1.0.0")
        code, out = self._run()
        self.assertEqual(code, 0, out)


if __name__ == "__main__":
    unittest.main()
