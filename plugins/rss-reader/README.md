# RSS Reader

RSS Reader is a Hermes desktop plugin with reader-mode capture, feed folders,
mute rules, saved searches, and optional AI grading.

## Slash commands

The plugin registers `/rss` with these forms:

- `/rss refresh` refreshes every subscription immediately.
- `/rss refresh 30m` saves a 30-minute automatic refresh period.
- `/rss mute phrase` mutes the phrase across every feed. Articles remain saved.
- `/rss refine 30d` opens a Hermes session that reviews recent sessions, updates
  `rss-reader-plugin` when the evidence supports a change, and reports what
  changed and why. Bare `/rss refine` uses 30 days.
- `/rss add https://example.com, Example to Research` discovers a common RSS or
  Atom endpoint, adds it to the folder, and refreshes it. The folder and title
  are optional.
- `/rss mark-read all` marks all unread articles as read. Use `feed <name>` or
  `folder <name>` for a narrower scope. Saved status is unchanged.
- `/rss digest unread [7d]` opens a Hermes session with a grouped digest of
  unread articles. `/rss digest saved` uses saved articles. The digest does not
  change read state or grading rules and includes at most 40 articles.
- `/rss health` reports feed errors, refresh age, unread counts, and feeds with
  no article in the last 7 days. It is read-only and does not refresh feeds.

The Python command half writes validated requests to the profile's
`rss-reader/commands.jsonl` queue. The desktop half consumes the queue and uses
the existing IndexedDB library, so slash commands and the reader page share one
state store. Requests are bounded and malformed commands are rejected before
queueing.
