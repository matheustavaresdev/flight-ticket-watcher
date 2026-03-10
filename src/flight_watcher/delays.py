import logging
import os
import random
import time

logger = logging.getLogger(__name__)

MIN_DELAY_SEC = float(os.environ.get("MIN_DELAY_SEC", "5"))
MAX_DELAY_SEC = float(os.environ.get("MAX_DELAY_SEC", "15"))


def random_delay(min_sec: float | None = None, max_sec: float | None = None) -> float:
    """Sleep for a random duration between min_sec and max_sec. Returns actual delay."""
    lo = min_sec if min_sec is not None else MIN_DELAY_SEC
    hi = max_sec if max_sec is not None else MAX_DELAY_SEC
    delay = random.uniform(lo, hi)
    logger.debug("sleeping %.1fs (range %.1f–%.1f)", delay, lo, hi)
    time.sleep(delay)
    return delay
