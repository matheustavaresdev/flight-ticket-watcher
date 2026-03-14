import enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class ErrorCategory(enum.Enum):
    RATE_LIMITED = "rate_limited"  # 429, CAPTCHA challenge
    NETWORK_ERROR = "network_error"  # timeout, DNS, connection
    PAGE_ERROR = "page_error"  # element not found, parse failure
    BLOCKED = "blocked"  # Akamai challenge, 403


@dataclass(frozen=True)
class RetryStrategy:
    max_retries: int
    min_delay_sec: float
    max_delay_sec: float
    skip_item: bool  # if True, skip this date/route and continue


RETRY_STRATEGIES: dict[ErrorCategory, RetryStrategy] = {
    ErrorCategory.RATE_LIMITED: RetryStrategy(
        max_retries=1, min_delay_sec=1800, max_delay_sec=3600, skip_item=False
    ),
    ErrorCategory.NETWORK_ERROR: RetryStrategy(
        max_retries=3, min_delay_sec=60, max_delay_sec=300, skip_item=False
    ),
    ErrorCategory.PAGE_ERROR: RetryStrategy(
        max_retries=0, min_delay_sec=0, max_delay_sec=0, skip_item=True
    ),
    ErrorCategory.BLOCKED: RetryStrategy(
        max_retries=0, min_delay_sec=0, max_delay_sec=0, skip_item=False
    ),
    # BLOCKED: circuit breaker — stop all searches, don't just skip one
}


def classify_error(exc: Exception, status_code: int | None = None) -> ErrorCategory:
    """Classify an exception into an error category for retry decisions."""
    # Check status code first
    if status_code == 429:
        return ErrorCategory.RATE_LIMITED
    if status_code == 403:
        return ErrorCategory.BLOCKED

    exc_type = type(exc).__name__
    exc_msg = str(exc).lower()

    # Playwright timeout
    if "timeout" in exc_type.lower() or "timeout" in exc_msg:
        return ErrorCategory.NETWORK_ERROR

    # Network errors
    network_keywords = [
        "dns",
        "connection",
        "reset",
        "refused",
        "unreachable",
        "eof",
        "broken pipe",
    ]
    if any(kw in exc_msg for kw in network_keywords):
        return ErrorCategory.NETWORK_ERROR

    # CAPTCHA / bot detection in message
    if "captcha" in exc_msg or "challenge" in exc_msg:
        return ErrorCategory.RATE_LIMITED

    # Page interaction errors (element not found, selector issues)
    page_keywords = [
        "locator",
        "selector",
        "element",
        "not found",
        "no such",
        "parse",
        "json",
        "key error",
    ]
    if any(kw in exc_msg for kw in page_keywords):
        return ErrorCategory.PAGE_ERROR

    # Default: treat unknown as network error (retry-able)
    return ErrorCategory.NETWORK_ERROR


def get_retry_strategy(category: ErrorCategory) -> RetryStrategy:
    """Get the retry strategy for an error category."""
    return RETRY_STRATEGIES[category]
