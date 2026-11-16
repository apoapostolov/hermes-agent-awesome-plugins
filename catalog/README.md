# Catalog drafts

Prepared `plugin-catalog/<name>.yaml` entries for this repo's plugins, held here until
they are submitted. Nothing in this folder has been opened as a pull request against
[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), and a draft
is not a listing: the reviewer reads the tree, not this file.

Before a draft becomes a submission:

1. Move the `sha` to the commit that must be installed. Every entry pins one commit,
   and the `image` URL must carry the same sha (rule-2).
2. Run the mechanical floor against both sides:

   ```
   python scripts/admission_check.py public/<name> --entry catalog/<name>.yaml
   ```

   It fails when the entry version differs from `plugin.yaml`, when the sha is not 40
   lowercase hex, when an image is pinned to another commit, when Windows-only code is
   not declared in `platforms`, and when network calls ship without a Disclosure
   sentence in the description.
3. Walk `references/catalog-review-bar.md` in the `hermes-plugin-desk-ops` skill. The
   script is a floor; the checklist is the review.
4. Open the entry as a new file in `plugin-catalog/` on a branch, with the frames the
   review expects in the pull request body.
