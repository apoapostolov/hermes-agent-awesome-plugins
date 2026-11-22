"""Junk a model leaves beside the chips: a printed classifier call, a dead attribute.

A model that means to ask the classifier but does not call `next_steps_recommend`
sometimes prints the call it wanted to make as a fenced JSON block under the
directive. It reaches the reader as a code block while the chips stay unmarked, which
is the worst of both: an internal detail shown and the feature it was meant to drive
missing.

The numbers a model writes this way are a guess, not an answer. `recommend.py` marks
only what the classifier returned, so the block is dropped rather than turned into a
Recommended tag that also starts the chip picked. The `recommend` attribute is dropped
from the directive for the same reason: it is the tool's argument name, the renderer
reads `rec`, and an attribute nothing reads sits in the stored reply looking as if it
did something.
"""

from __future__ import annotations

import json
import re

# A printed call carries the tool's own argument names. A block with any key outside
# this set is somebody's example rather than a call that failed to happen.
CALL_KEYS = frozenset({"recommend", "rec", "recommended"})
CALL_ARGS = CALL_KEYS | {"options", "context", "alternates", "risky", "multi", "subtitles"}

# A line that is nothing but a fence, with an optional language tag.
_FENCE_RE = re.compile(r"^[ \t]*```[ \t]*[A-Za-z0-9_+.-]*[ \t]*$")


def strip_call(text: str) -> str:
    """Drop a fenced classifier call that ends the reply, and nothing else.

    Only the last block is a candidate, and only when its closing fence is the last
    thing in the reply: an example quoted mid-reply sits above prose that follows it
    and is left alone.
    """
    if not isinstance(text, str) or "```" not in text:
        return text
    block = _ending_block(text)
    if block is None:
        return text
    start, body = block
    if _payload(body) is None:
        return text
    return "\n".join(text.rstrip().splitlines()[:start]).rstrip()


def _ending_block(text: str) -> tuple[int, str] | None:
    """(index of the opening fence, body) for the block that closes the reply."""
    lines = text.rstrip().splitlines()
    if not lines or not _FENCE_RE.match(lines[-1]):
        return None
    for index in range(len(lines) - 2, -1, -1):
        if _FENCE_RE.match(lines[index]):
            return index, "\n".join(lines[index + 1 : -1])
    return None


def _payload(body: str) -> dict | None:
    """The parsed call, or None when the block is anything else."""
    snippet = body.strip()
    if not snippet.startswith("{"):
        return None
    try:
        payload = json.loads(snippet)
    except ValueError:
        return None
    if not isinstance(payload, dict) or not payload:
        return None
    keys = {str(key).strip().lower() for key in payload}
    if not keys & CALL_KEYS or not keys <= CALL_ARGS:
        return None
    return payload
