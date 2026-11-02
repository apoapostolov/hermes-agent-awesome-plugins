# AGENTS.md

Repo rules for `personal/` and `public/` plugin editions.

## Editions

- `personal/` is the full-featured copy Apo runs. Keep reach-in behavior he actually uses. The pack pins this tree.
- `public/` is the catalog-listable edition. Stay inside the plugin SDK. Drop a surface when the hook does not exist yet.
- Live installs hash against personal. Never copy a listing cut onto live or personal.

## Backport public fixes to personal

When a public edition gets a real defect fix, copy that same fix onto personal in the same change.

A real defect is a crash, data loss, path traversal, wrong result, or a security hole. Backport it only when personal still has that code path.

Never backport a listing cut. Public may drop composer inject, React fiber walks, app `localStorage`, raw bridge calls, vendor-token refresh, automatic Hermes `.env` / `config.yaml` writes, process-wide patches, and similar reach-in. Personal must keep those behaviors.

If one public change both fixes a defect and removes functionality, backport only the defect fix. Leave the functionality removal in public.

## Programs and downloads

A tool that can run a program the user did not start, or fetch and run a binary, asks first.

- Register a `pre_tool_call` hook that returns `{"action": "approve", "message": ...}` for every path that starts a process: launch and close actions, the batch equivalents, installs, and an auto-install that fires inside a read-only call. The message names the program and its arguments.
- A hook sees every tool in the process. Match only this plugin's tool names before acting on a shared setting such as `auto_install`.
- Verify a download against a digest pinned in the plugin. Take the version from the plugin setting, never from a tool argument, and never trust the release's own `checksums.txt`.
- The README and CHANGELOG name the Hermes release that turns an `approve` return into the approval gate: v2026.7.7, semver 0.18.1. Core compares semver and its tags are dates, so give both, and check the claim against core tags rather than a review comment.
- Tests prove each gated path returns the directive, that an ungated call and another plugin's tool do not, and that an unpinned version is refused before the network is touched.

## Versions

Personal and public of the same plugin share one `plugin.yaml` version.

If you raise the public version because of a change, set personal to that same version in the same commit. Do this even when personal did not receive the public-only listing cuts.

Do not raise a version unless Apo asks or the change needs a bump. A public-only description, homepage, or disclosure edit is not a version bump.

Do not lower personal to match a public cut. Never ship personal behind public.

## Catalog work

Do not gut personal to get a listing. Do not restore public reach-in just to keep the two trees identical.

Each plugin that could not list as personal has `LIMITATIONS.md` in that plugin folder. Read it before a catalog pin, and before copying a personal feature into `public/`. For every blocker: still comply, or confirm the linked Hermes issue or PR is resolved and the SDK hook exists.
