#!/usr/bin/env python3
"""Tests for scripts/worktree.py.

Run from the repo root with:
    python -m unittest discover -s scripts/tests -t scripts -v
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "worktree.py"


class WorktreeScriptTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.wt_root = Path(self.tmp.name) / "wt-root"
        self.wt_root.mkdir()
        (self.root / "scripts").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / SCRIPT.name)
        self._git("init", "-b", "main")
        self._git("config", "user.email", "test@example.com")
        self._git("config", "user.name", "test")
        (self.root / "README.md").write_text("hello\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "init")

    def tearDown(self):
        # git worktree remove may leave locks on Windows; be lenient.
        self._git("worktree", "prune", check=False)
        self.tmp.cleanup()

    def _git(self, *args, check=True):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            check=check,
        )

    def _run(self, *args, check=False):
        proc = subprocess.run(
            [sys.executable, "scripts/worktree.py", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
        )
        if check and proc.returncode != 0:
            self.fail(f"command failed: {args}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}")
        return proc

    def test_new_creates_worktree_for_new_branch(self):
        proc = self._run("new", "feat/test-thing", "--root", str(self.wt_root), check=True)
        wt_path = Path(proc.stdout.strip())
        self.assertTrue(wt_path.exists(), wt_path)
        self.assertEqual(wt_path.parent, self.wt_root)
        self.assertIn("hap-wt--feat--test-thing", wt_path.name)
        # Branch exists and is checked out in the worktree.
        head = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(head, "feat/test-thing")

    def test_new_uses_existing_local_branch(self):
        self._git("branch", "fix/existing")
        proc = self._run("new", "fix/existing", "--root", str(self.wt_root), check=True)
        wt_path = Path(proc.stdout.strip())
        head = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=wt_path,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        self.assertEqual(head, "fix/existing")

    def test_new_refuses_existing_path(self):
        target = self.wt_root / "hap-wt--feat--exists"
        target.mkdir()
        proc = self._run("new", "feat/exists", "--root", str(self.wt_root))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already exists", proc.stderr + proc.stdout)

    def test_new_with_base(self):
        self._git("checkout", "-b", "base-branch")
        (self.root / "base.txt").write_text("base\n", encoding="utf-8")
        self._git("add", "base.txt")
        self._git("commit", "-m", "base")
        self._git("checkout", "main")
        proc = self._run(
            "new", "feat/from-base", "--base", "base-branch", "--root", str(self.wt_root), check=True
        )
        wt_path = Path(proc.stdout.strip())
        self.assertTrue((wt_path / "base.txt").exists())

    def test_ls_lists_main_and_worktrees(self):
        self._run("new", "feat/one", "--root", str(self.wt_root), check=True)
        proc = self._run("ls", check=True)
        self.assertIn("main", proc.stdout)
        self.assertIn("feat/one", proc.stdout)

    def test_rm_removes_by_branch(self):
        self._run("new", "feat/remove-me", "--root", str(self.wt_root), check=True)
        proc = self._run("rm", "feat/remove-me", check=True)
        self.assertIn("removed", proc.stdout)
        ls = self._run("ls", check=True)
        self.assertNotIn("feat/remove-me", ls.stdout)

    def test_rm_refuses_main_worktree(self):
        main_entry = self._run("ls", check=True).stdout
        self.assertIn("main", main_entry)
        proc = self._run("rm", "main")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("main worktree", proc.stderr + proc.stdout)

    def test_path_returns_worktree_path(self):
        created = self._run("new", "feat/path-me", "--root", str(self.wt_root), check=True)
        expected = created.stdout.strip()
        proc = self._run("path", "feat/path-me", check=True)
        self.assertEqual(proc.stdout.strip(), expected)

    def test_slugify_collapses_slashes(self):
        proc = self._run("new", "feat/deep/nested/branch", "--root", str(self.wt_root), check=True)
        wt_path = Path(proc.stdout.strip())
        self.assertIn("hap-wt--feat--deep--nested--branch", wt_path.name)


if __name__ == "__main__":
    unittest.main()
