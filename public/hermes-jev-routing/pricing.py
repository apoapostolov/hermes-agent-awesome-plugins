"""Catalog edition: no host pricing. Every row stays unpriced and un-flagged.

Personal edition reads ``agent.usage_pricing`` for real per-million rates and
``agent.model_metadata`` for reasoning support. A missing cost makes the cache
penalty 0, which never holds a turn, so this stub fails safe.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def cost_for(provider: str, model: str) -> Optional[dict]:
    return None


def supports_reasoning(provider: str, model: str) -> bool:
    return False


def forget() -> None:
    return None
