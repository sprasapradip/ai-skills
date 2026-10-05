"""Item processing."""
from __future__ import annotations

import json
import logging
from typing import Sequence

logger = logging.getLogger(__name__)


def process(items: Sequence[int]) -> str:
    """Serialize items deeper than the threshold."""
    deep = [i for i in items if i > 3]
    logger.debug("kept %d items", len(deep))
    return json.dumps(deep)
