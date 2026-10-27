"""Better Capabilities — Python half.

The public edition registers no slash command and no tool. The Desktop page is
the product; it snapshots and applies capability state through the plugin SDK,
and the only Python here is the file work behind ``ctx.rest`` (skill delete,
package, markdown browse) plus the preset file itself.
"""

from __future__ import annotations

from typing import Any


def register(ctx: Any = None):
    # Nothing to register. `/preset` lives in the personal edition because
    # reading or writing a profile's capability state from Python needs core
    # modules that are not a public plugin surface.
    return None
