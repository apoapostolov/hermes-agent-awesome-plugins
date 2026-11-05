# Catalog and platform limitations

Reddit 1.1.0 is a standalone release. Both repository editions provide 22 tools and plugin-managed OAuth. Neither is currently admitted to the Hermes Plugin Catalog.

Catalog admission rule 11 requires Hermes to own third-party OAuth login, token storage, refresh and credential attachment. The current generic route cannot fully support Reddit:

- The token route sends client credentials as form fields. Reddit requires HTTP Basic client authentication; a read-only grant test returned HTTP 401 for the form-field method.
- The plugin OAuth declaration does not expose a fixed callback port/path, although Reddit requires an exact registered redirect URI.
- The credentialed-request helper exposes JSON bodies; Reddit writes require URL-encoded forms.

[Upstream issue #142687](https://github.com/NousResearch/hermes-agent/issues/142687) tracks Basic authentication and redirect configuration. Supported form-body transport is also needed. The current validator's safe/SDK verdict does not prove catalog admission compliance.

Before listing, verify these APIs in a released Hermes build, migrate the listed edition to declared OAuth and credentialed requests, remove its plugin-owned credentials/callback/refresh path, verify real sign-in and form requests, and update the compatibility floor. No catalog entry should claim that migration is complete yet.

Reddit has also announced the end of remaining public Data API access in March 2027. Devvit excludes personal saves, subscriptions and voting history. Local code cannot grant an API capability that Reddit does not expose. See the [API audit](docs/API-AUDIT.md).

Cleanup runs only while Hermes or an explicit maintenance command runs. Bookmark transfer excludes source content. Full-thread/linked-article ingestion and embedding-based search are not included.
