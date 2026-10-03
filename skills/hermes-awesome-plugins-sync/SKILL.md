---
name: hermes-awesome-plugins-sync
category: hermes
description: "Use when any plugin in hermes-agent-awesome-plugins changes, backport rules, live-install sync, pack repin, per-plugin releases, and the upstream catalog listing."
version: 2.0.0
tags:
- hermes
- plugins
- sync
- catalog
- release
related_skills:
- hermes-plugin-authoring
- github
---

# Hermes Awesome Plugins

Owns every change to `apoapostolov/hermes-agent-awesome-plugins`, from editing a plugin through the live install, the pack pin, the per-plugin GitHub release, and the listing in the upstream Hermes plugin catalog.

## Where things live

| What | Path |
| --- | --- |
| Working checkout | `C:/git/hermes-agent-awesome-plugins-commands` (branch `main`) |
| Live install (source of truth for personal) | `C:/Users/theap/AppData/Local/hermes/plugins/<name>` |
| Personal tree | `personal/<name>/` |
| Public tree | `public/<name>/` |
| DR mirror | `bash C:/git/hermes-dr/workstation/sync-workstation.sh` |

There is also a `C:/git-public/hermes-agent-awesome-plugins` checkout with the same remote. It sits on a branch with no commits and is **not** where work happens. Ignore it.

`C:/git/hermes-agent-awesome-plugins-commands` and `...-migrate` are worktrees sharing one `.git`. Never `git checkout` inside `%LOCALAPPDATA%/hermes/hermes-agent`; that is the live install and mixing module versions breaks the running process. For upstream work use `git clone --shared` into `%LOCALAPPDATA%/hermes/scratch/<task>` and delete it after.

## Editions and the backport rule

`personal/` is the full edition Apo runs and may reach into Desktop internals. `public/` is the catalog edition and must stay inside the plugin SDK (`ctx.register*`, `host.state`, `ctx.request`, `ctx.storage`, `ctx.rest`).

1. **A real defect fix goes to both trees in the same change.** A real defect is a crash, data loss, path traversal, wrong result, or a security hole. Backport only when personal still has that code path.
2. **Never backport a listing cut.** Public may drop composer inject, React fiber walks, app `localStorage`, raw bridge calls, vendor-token refresh, automatic `.env` / `config.yaml` writes, and process-wide patches. Personal keeps them.
3. **One change that both fixes a defect and removes functionality:** backport the fix, leave the removal in public.
4. **Versions are one number per plugin.** If you raise public, set personal to the same number in the same commit, even when personal only received the version line. Never ship personal behind public. Do not bump without a reason.
5. **Personal is not a lesser public.** It is a different edition with more reach-in. Personal may keep `window.localStorage` while public moves to `ctx.storage`. That is correct, not drift.

Catalog blockers live in each personal plugin's `LIMITATIONS.md`. Read it before a catalog pin or before copying a personal feature into `public/`.

## Editing rules that prevent real bugs

- **`0.0` sentinels are not "no value".** When a provider API returns a subset of windows, track presence with explicit flags and emit only what was reported. The truthiness chain (`if pct or pct == 0`) is what deliberately skips a *full* window, so keep it for the rotation/exhaust value and use flags for the window list.
- **Never send `null` for an absent number JS reads.** `Number(null) === 0` and `isFinite(0)` is true, so a JSON `null` renders as a full window. Omit the key: `Number(undefined)` is NaN and the existing guard rejects it.
- **Provider `type` strings get renamed upstream.** Accept the new name alongside the old.
- **Treat stored state as untrusted.** A wrong type, null, out-of-range number, or a storage backend that throws must fall back to defaults, never throw.
- **Match house style.** If a sibling plugin already solves it (`ctx.storage` plus a `useSyncExternalStore` version counter), copy that shape.
- **Clear stale bytecode** (`__pycache__/*.pyc`, both interpreters) after editing a live plugin module.

## Verify before you commit

Syntax checks are not verification.

- **Backend:** import the module under `fastapi`/`pydantic` stubs and call the fetcher against recorded provider payloads. Cover the new shape, the legacy shape, all-unused, empty list, unknown type, and API error.
- **Frontend helpers:** lift the pure helpers into a scratch script with a fake storage backend. Assert defaults, round-trips, corrupt input, and a throwing backend.
- **Assert the output, not the absence of a crash.** A parser that reads nothing raises nothing and passes a naive check.
- **Prove an absence check can report absence.** Always use a known-missing control when a script claims something is "not listed" or "not found".
- **Check the audit itself.** Several false passes came from a check being too broad, not from the content being wrong. When an audit fails, first ask whether the check is right.

## Live install sync

The live install must end byte-identical to `personal/` on the code files:

```bash
diff -q "C:/Users/theap/AppData/Local/hermes/plugins/<name>/dashboard/plugin_api.py" \
        "C:/git/hermes-agent-awesome-plugins-commands/personal/<name>/dashboard/plugin_api.py"
```

Copy only the changed code files and `plugin.yaml`. Never copy `config.json`, `library.env`, `*.bak-*`, or `__pycache__`.

**Delete backups at the source.** A `.bak-<stamp>` file left in the live plugin dir is copied into the DR mirror on every sync, forever, and `library.env.bak-*` copies carry real API keys. Recycle them from the live install with
`[Microsoft.VisualBasic.FileIO.FileSystem]::DeleteFile(path,'OnlyErrorDialogs','SendToRecycleBin')`, never a plain unlink, then re-sync. Removing them only from the mirror does not help, because the next sync brings them back.

## Pack pin

`hermes-pack.yaml` pins each entry to `repo` + `subdir` + an exact 40-char SHA, and pins the **personal** tree. After any change shipping a pack plugin, repin that entry to the new `origin/main` sha and push. Verify every ref is still 40 hex chars and the pinned tree contains the change.

## Per-plugin release

One tag and one release per plugin, never one for the repo. Convention: `plugin-name-vX.Y.Z`, title `Plugin Name X.Y.Z`, notes compared against the **real previous release** (`gh release view <prev-tag>`). Do not file fixes to unreleased work under `Fixed`.

**`gh release create --target main` tags whatever `main` currently points at.** Releasing two plugins back to back made the first tag land on the second plugin's commit. Tag explicitly and verify:

```bash
git tag <plugin>-vX.Y.Z <the-sha-that-has-the-fix>
git push origin <plugin>-vX.Y.Z
git ls-remote --tags origin <plugin>-vX.Y.Z   # must equal the intended sha
```

If `gh release create` already pushed a wrong tag, retag, `--force` it, and re-verify.

## Upstream catalog listing

The listing lives in `NousResearch/hermes-agent` under `plugin-catalog/<name>.yaml`. It is not in this repo, and the Revell plugin index is deprecated.

Fields that must move together:

- `sha`, a commit in this repo containing the plugin
- `subdir`, `public/<name>` for a listed plugin
- `version`, must equal the plugin's own `plugin.yaml`
- `image`, `https://raw.githubusercontent.com/apoapostolov/hermes-agent-awesome-plugins/<sha>/<subdir>/docs/hero.png`
- `docs_url`, `.../tree/main/<subdir>`

**Rebuild the image URL wholesale.** Overlapping regexes that rewrote sha and subdir separately produced a mangled URL and then a half-applied move, so the hero 404'd. Compose the whole URL from the verified sha and subdir, and prove the blob exists at that sha first. Same for `docs_url`.

Before proposing a pin, verify the sha is a commit, `<sha>:<subdir>` is a tree, `<sha>:<subdir>/docs/hero.png` is a blob, and the listed version matches the repo.

**Retired layout:** some entries still point at the old `plugins/<name>` path from before the personal/public split. Those resolve at their old shas, so they install, but they cannot receive catalog fixes. Repin them to `public/<name>`.

## Opening and updating the upstream PR

`gh pr create` against `NousResearch/hermes-agent` can fail with a `createPullRequest` permission error or a bare REST 404, despite a valid `repo`-scoped token, a healthy fork, and a clean merge base. It is a repo or org-side restriction on the account, not a git problem. **Do not keep retrying**, and do not chase it with stale-fork, ancestry, branch-name, or token-scope theories.

**Update an existing open PR instead.** That needs only `git push` to the PR's head branch, which is a different permission and normally works. Push to the **fork** remote, never `origin`, since `origin` is the read-only upstream:

```bash
git push --force-with-lease=refs/heads/<branch>:<sha-you-based-on> fork HEAD:<branch>
```

`--force-with-lease` with the expected old sha is mandatory. Upstream branches drift thousands of commits per day, so a plain force risks clobbering someone else's edit.

A long-stale PR branch usually cannot be rebased; conflicts arrive on unrelated churn. Rebuild from current `origin/main` and reapply both edit sets. Rebase by hand only when the delta is small.

**Verify the change landed in the PR, not on main.** Reading `plugin-catalog/<name>.yaml` from `main` shows the old value until merge, which looks like the push failed. Read the PR's own file list and diff.

Diagnose with `gh api repos/<upstream>/compare/main...<owner>:<branch>` and read `status`/`ahead_by`/`behind_by`. A "no permissions" error is not evidence of a stale branch.

## Never do these

- Never leave a commit unpushed or claim a listing merged without reading it back.
- Never bump a version to make a number look tidy. A fix is a patch.
- Never state an unmerged change as shipped in the README. Name the PR that carries it.
- Never run `gh auth refresh` unprompted. It starts a device flow and puts a code on the user's clipboard.

## README

Counts and listing state in the root README must be derived, not remembered. Re-derive the pack count, the plugin count, per-plugin listing state, the version badge against `hermes-pack.yaml`, and every relative link, then assert the README matches. Update counts in the same commit as the plugin change.
