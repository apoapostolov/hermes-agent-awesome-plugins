# LIMITATIONS

Public edition of **Sidebar Manager** (`sidebar-manager`). This file records where the listed edition stops short of the personal edition and why. Both editions carry the same copy.

Catalog intake PR: [NousResearch/hermes-agent#115973](https://github.com/NousResearch/hermes-agent/pull/115973). Shared hook wishlist: [#116305](https://github.com/NousResearch/hermes-agent/issues/116305).

## Edition split (post-migration 2026-09-24)

The SDK hook this plugin was held on shipped: `SIDEBAR_NAV_PREFS_AREA`
(`sidebarNav.prefs`, [#116305 item 4](https://github.com/NousResearch/hermes-agent/issues/116305),
merged 2026-09-24). The public edition now uses it:

- Hide/order of the **core nav rows** (`new-session`, `capabilities`,
  `messaging`, `artifacts`, `cron`) goes through a `sidebarNav.prefs`
  contribution. No injected CSS, no DOM re-parenting, no body-wide
  `MutationObserver`, no raw `localStorage`.
- Prefs persist in `ctx.storage` under `navPrefs` (cleaned with the plugin).

**The two editions differ in implementation scope:**

- **Personal** keeps the full editor: session SECTIONS (Pinned, Recents,
  platform groups, Cron jobs) are also hideable and reorderable, via the
  legacy DOM technique. The SDK area covers nav rows only ("Session sections
  are not covered - nav rows only", SDK docs) and there is no sessions-section
  hook yet.
- **Public** covers core nav rows only, entirely through the SDK. Section
  management is not shipped in this edition because no SDK hook exists for it.

## If a sessions-section hook lands

Extend the public dialog to list sections and drive them through the new
area; then the editions can converge. Track
[#116305](https://github.com/NousResearch/hermes-agent/issues/116305).
