# Reach-in

This edition switches providers the same way the personal edition does. It walks the caller stack, and if that misses, the live agent cache, then calls `switch_model`. The desktop half also asks the session to adopt the pick when the tier is not held for confirm.

Three seams stay inside Hermes and therefore personal-only: the provider catalogue read in `availability.py`, the Codex quota read in `quota_live.py`, and the rate card plus capability table in `pricing.py`. The public tree keeps its own no-op readers, so its rows stay unpriced, which makes the cache penalty zero and the guard never holds.
