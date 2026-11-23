#!/usr/bin/env python3
"""Create, list, and remove git worktrees for this repository.

Worktrees are created as top-level directories in the git-public container,
named `hap-wt--<branch-slug>`, so they follow the container convention where
each top-level entry is a repository or a worktree.

Usage:
  python scripts/worktree.py new <branch> [--base REF] [--root DIR]
  python scripts/worktree.py ls
  python scripts/worktree.py rm <branch-or-path> [--force]
  python scripts/worktree.py path <branch>
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path("C:/git-public")
WORKTREE_PREFIX = "hap-wt--"
REPO_ROOT = Path(__file__).resolve().parents[1]


def run_git(*args: str, cwd: Path = REPO_ROOT, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=check,
    )


def git_stdout(*args: str, cwd: Path = REPO_ROOT, check: bool = True) -> str:
    return run_git(*args, cwd=cwd, check=check).stdout.strip()


def slugify_branch(branch: str) -> str:
    slug = branch.strip().replace("\\", "/")
    slug = slug.strip("/")
    slug = re.sub(r"[^A-Za-z0-9._/-]+", "-", slug)
    slug = slug.replace("/", "--")
    slug = re.sub(r"-{2,}", "--", slug).strip("-")
    if not slug:
        raise SystemExit("branch name produced an empty worktree slug")
    return slug


def worktree_path_for(branch: str, root: Path) -> Path:
    return root / f"{WORKTREE_PREFIX}{slugify_branch(branch)}"


def branch_exists(branch: str) -> bool:
    return run_git("show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0


def remote_branch_exists(branch: str, remote: str = "origin") -> bool:
    return (
        run_git("show-ref", "--verify", "--quiet", f"refs/remotes/{remote}/{branch}", check=False).returncode
        == 0
    )


def worktree_entries() -> list[dict[str, str]]:
    out = git_stdout("worktree", "list", "--porcelain")
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in out.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if " " in line:
            key, value = line.split(" ", 1)
        else:
            key, value = line, ""
        current[key] = value
    if current:
        entries.append(current)
    return entries


def find_worktree(target: str) -> dict[str, str]:
    entries = worktree_entries()
    target_path = Path(target)
    if not target_path.is_absolute():
        target_path = (Path.cwd() / target_path)
    try:
        resolved_target = target_path.resolve()
    except OSError:
        resolved_target = target_path

    for entry in entries:
        wt = Path(entry.get("worktree", ""))
        try:
            resolved_wt = wt.resolve()
        except OSError:
            resolved_wt = wt
        branch = entry.get("branch", "").removeprefix("refs/heads/")
        if resolved_wt == resolved_target or branch == target or wt.name == target:
            return entry
    raise SystemExit(f"no worktree matches {target!r}; run `python scripts/worktree.py ls`")


def cmd_new(args: argparse.Namespace) -> int:
    root = Path(args.root)
    branch = args.branch
    path = worktree_path_for(branch, root)
    if path.exists():
        raise SystemExit(f"worktree path already exists: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)

    if branch_exists(branch):
        run_git("worktree", "add", str(path), branch)
    elif remote_branch_exists(branch):
        run_git("worktree", "add", "--track", "-b", branch, str(path), f"origin/{branch}")
    else:
        base = args.base or "HEAD"
        run_git("worktree", "add", "-b", branch, str(path), base)

    print(path.as_posix())
    return 0


def cmd_ls(_: argparse.Namespace) -> int:
    entries = worktree_entries()
    for entry in entries:
        wt = entry.get("worktree", "")
        branch = entry.get("branch", "").removeprefix("refs/heads/")
        head = entry.get("HEAD", "")[:12]
        extra = []
        if "locked" in entry:
            reason = entry.get("locked", "").strip()
            extra.append(f"locked: {reason}" if reason else "locked")
        if "prunable" in entry:
            extra.append("prunable")
        suffix = f"  ({', '.join(extra)})" if extra else ""
        label = branch or f"detached {head}"
        marker = "*" if Path(wt).resolve() == REPO_ROOT.resolve() else " "
        print(f"{marker} {label:40} {head}  {wt}{suffix}")
    return 0


def cmd_rm(args: argparse.Namespace) -> int:
    entry = find_worktree(args.target)
    wt = entry.get("worktree", "")
    if Path(wt).resolve() == REPO_ROOT.resolve():
        raise SystemExit("refusing to remove the main worktree")
    cmd = ["worktree", "remove"]
    if args.force:
        cmd.append("--force")
    cmd.append(wt)
    proc = run_git(*cmd, check=False)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr or proc.stdout)
        return proc.returncode
    print(f"removed {Path(wt).as_posix()}")
    return 0


def cmd_path(args: argparse.Namespace) -> int:
    entry = find_worktree(args.target)
    print(Path(entry.get("worktree", "")).as_posix())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_new = sub.add_parser("new", help="Create a worktree for a branch")
    p_new.add_argument("branch", help="Branch name to check out in the worktree")
    p_new.add_argument("--base", help="Base ref when creating a new branch (default: HEAD)")
    p_new.add_argument(
        "--root",
        default=str(DEFAULT_ROOT),
        help=f"Directory where the worktree folder is created (default: {DEFAULT_ROOT})",
    )
    p_new.set_defaults(func=cmd_new)

    p_ls = sub.add_parser("ls", help="List worktrees for this repository")
    p_ls.set_defaults(func=cmd_ls)

    p_rm = sub.add_parser("rm", help="Remove a worktree by branch name or path")
    p_rm.add_argument("target", help="Branch name, worktree path, or worktree directory name")
    p_rm.add_argument("--force", action="store_true", help="Pass --force to git worktree remove")
    p_rm.set_defaults(func=cmd_rm)

    p_path = sub.add_parser("path", help="Print the path of a matching worktree")
    p_path.add_argument("target", help="Branch name, worktree path, or worktree directory name")
    p_path.set_defaults(func=cmd_path)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except subprocess.CalledProcessError as exc:
        msg = exc.stderr or exc.stdout or str(exc)
        sys.stderr.write(msg if msg.endswith("\n") else msg + "\n")
        return exc.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
