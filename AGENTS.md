# AGENTS.md

Repo rules for `personal/` and `public/` plugin editions.

## Editions

- `personal/` is the full-featured copy Apo runs. Keep reach-in behavior he actually uses.
- `public/` is the catalog-listable edition. Stay inside the plugin SDK. Drop a surface when the hook does not exist yet.
- `plugins/` is the pack-install path until public is listing-clean. Treat it as personal bytes unless a later note says otherwise.
- Live installs hash against personal. Never copy a listing cut onto live or personal.

## Backport public fixes to personal

When a public edition gets a real defect fix, copy that same fix onto personal in the same change. Copy it onto `plugins/` too while that tree still tracks personal.

A real defect is a crash, data loss, path traversal, wrong result, or a security hole. Backport it only when personal still has that code path.

Never backport a listing cut. Public may drop composer inject, React fiber walks, app `localStorage`, raw bridge calls, vendor-token refresh, automatic Hermes `.env` / `config.yaml` writes, process-wide patches, and similar reach-in. Personal must keep those behaviors.

If one public change both fixes a defect and removes functionality, backport only the defect fix. Leave the functionality removal in public.

## Versions

Personal and public of the same plugin share one `plugin.yaml` version.

If you raise the public version because of a change, set personal to that same version in the same commit. Do this even when personal did not receive the public-only listing cuts.

Do not raise a version unless Apo asks or the change needs a bump. A public-only description, homepage, or disclosure edit is not a version bump.

Do not lower personal to match a public cut. Never ship personal behind public.

## Catalog work

Do not gut personal to get a listing. Do not restore public reach-in just to keep the two trees identical.
