# RSS Reader

RSS Reader is a Hermes desktop plugin with reader-mode capture, feed folders,
mute rules, saved searches, and optional AI grading.

## Slash commands

The plugin registers `/rss` with these forms:

- `/rss refresh` refreshes every subscription immediately.
- `/rss refresh 30m` saves a 30-minute automatic refresh period.
- `/rss mute phrase` mutes the phrase across every feed. Articles remain saved.
- `/rss refine 30d` opens a Hermes session that reviews recent sessions, updates
  `rss-reader-grading` when the evidence supports a change, and reports what
  changed and why. Bare `/rss refine` uses 30 days.
- `/rss add https://example.com, Example to Research` discovers a common RSS or
  Atom endpoint, adds it to the folder, and refreshes it. The folder and title
  are optional.

The Python command half writes validated requests to the profile's
`rss-reader/commands.jsonl` queue. The desktop half consumes the queue and uses
the existing IndexedDB library, so slash commands and the reader page share one
state store. Requests are bounded and malformed commands are rejected before
queueing.
