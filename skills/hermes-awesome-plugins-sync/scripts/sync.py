#!/usr/bin/env python3
"""Sync live Hermes plugins into the hermes-agent-awesome-plugins monorepo.

Strips secrets (__pycache__, config.json, library.env, .env) and optionally
commits, pushes, and repins hermes-pack.yaml refs.

Usage:
  python sync.py                 # copy only
  python sync.py --commit --push # copy + commit + push
  python sync.py --commit --push --repin  # also update hermes-pack.yaml SHA
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import subprocess
import sys

LIVE_ROOT = pathlib.Path("C:/Users/theap/AppData/Local/hermes/plugins")
MONO_ROOT = pathlib.Path("C:/git-public/hermes-agent-awesome-plugins")
PLUGINS = ("provider-status", "hermes-break", "better-colors", "drag-to-pin-session")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "config.json", "library.env", ".env", "*.key", ".DS_Store")

def run(cmd, cwd=None):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout.rstrip())
    if r.stderr:
        print(r.stderr.rstrip(), file=sys.stderr)
    return r

def copy_plugins():
    for name in PLUGINS:
        src = LIVE_ROOT / name
        dst = MONO_ROOT / "plugins" / name
        if not src.exists():
            print(f"WARN: live {src} missing — skip", file=sys.stderr)
            continue
        # stash docs/examples that don't exist live
        keep = {}
        if dst.exists():
            for pat in ("*.md", "*.example"):
                for f in dst.glob(pat):
                    keep[f.name] = f.read_bytes()
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=IGNORE)
        for k, v in keep.items():
            p = dst / k
            if not p.exists():
                p.write_bytes(v)
                print(f"  restored {k}")
        # extra scrub
        for p in dst.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)
        for p in dst.rglob("*.pyc"):
            p.unlink(missing_ok=True)
        # Pack install looks for desktop/plugin.js. Live plugins keep
        # plugin.js at the package root so the desktop-plugins auto-on door
        # is the only loader — relocate for the pack layout only.
        root_js = dst / "plugin.js"
        desk_js = dst / "desktop" / "plugin.js"
        if root_js.exists() and not desk_js.exists():
            (dst / "desktop").mkdir(exist_ok=True)
            root_js.replace(desk_js)
            print("  moved plugin.js -> desktop/plugin.js")
        print(f"copied {name} -> {dst} ({sum(1 for _ in dst.rglob('*'))} entries)")

    # mirror skill itself into monorepo
    skill_src = pathlib.Path("C:/Users/theap/AppData/Local/hermes/skills/hermes-awesome-plugins-sync")
    skill_dst = MONO_ROOT / "skills" / "hermes-awesome-plugins-sync"
    if skill_src.exists():
        if skill_dst.exists():
            shutil.rmtree(skill_dst)
        shutil.copytree(skill_src, skill_dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
        print(f"mirrored skill -> {skill_dst}")

def git_commit_push(msg):
    st = run(["git", "status", "--porcelain"], cwd=str(MONO_ROOT))
    if not st.stdout.strip():
        print("nothing to commit")
        return None
    run(["git", "add", "-A"], cwd=str(MONO_ROOT))
    r = run(["git", "commit", "-m", msg], cwd=str(MONO_ROOT))
    if r.returncode != 0:
        return None
    r2 = run(["git", "push"], cwd=str(MONO_ROOT))
    if r2.returncode != 0:
        print("push failed", file=sys.stderr)
        return None
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(MONO_ROOT), text=True).strip()
    print(f"pushed {sha}")
    return sha

def repin_pack(sha):
    pack = MONO_ROOT / "hermes-pack.yaml"
    if not pack.exists():
        print(f"no pack at {pack}", file=sys.stderr)
        return
    text = pack.read_text(encoding="utf-8")
    # replace every 40-hex ref with sha
    import re
    new_text = re.sub(r"ref:\s*[0-9a-fA-F]{40}", f"ref: {sha}", text)
    if new_text == text:
        # placeholder zeros
        new_text = re.sub(r"0{40}", sha, text)
    if new_text != text:
        pack.write_text(new_text, encoding="utf-8")
        print(f"repin pack -> {sha}")
        run(["git", "add", "hermes-pack.yaml"], cwd=str(MONO_ROOT))
        run(["git", "commit", "-m", f"chore: repin pack to {sha[:12]}"], cwd=str(MONO_ROOT))
        run(["git", "push"], cwd=str(MONO_ROOT))
    else:
        print("pack already pinned or no ref to replace")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="git commit after copy")
    ap.add_argument("--push", action="store_true", help="git push after commit")
    ap.add_argument("--repin", action="store_true", help="repin hermes-pack.yaml refs to new SHA")
    ap.add_argument("-m", "--message", default=None, help="commit message")
    args = ap.parse_args()

    copy_plugins()

    if args.commit:
        msg = args.message or "sync: mirror live plugins (sanitized)"
        sha = git_commit_push(msg) if args.push or True else None
        # if --push not given but --commit given, git_commit_push with push flag controls
        if not args.push and sha:
            # committed but not pushed — still allow repin after push?
            pass
        if args.repin:
            # need SHA
            if not args.push:
                run(["git", "push"], cwd=str(MONO_ROOT))
            sha2 = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(MONO_ROOT), text=True).strip()
            # validate
            import re
            if not re.fullmatch(r"[0-9a-f]{40}", sha2):
                print(f"bad sha {sha2}", file=sys.stderr)
                sys.exit(1)
            repin_pack(sha2)

if __name__ == "__main__":
    main()
