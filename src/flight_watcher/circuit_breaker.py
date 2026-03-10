"""Circuit breaker to halt searches when the upstream service is blocking us."""

import logging
import os
import time
from enum import Enum

from flight_watcher.errors import ErrorCategory

logger = logging.getLogger(__name__)

# Backoff durations in seconds: 15min, 30min, 1h, 2h
_DEFAULT_BACKOFF_LEVELS = (900, 1800, 3600, 7200)
_DEFAULT_FAILURE_THRESHOLD = 3


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Tracks consecutive failures and controls search access."""

    # Categories that trip the breaker (service-level blocks)
    TRIPPING_CATEGORIES = frozenset({ErrorCategory.BLOCKED, ErrorCategory.RATE_LIMITED})

    def __init__(
        self,
        failure_threshold: int = _DEFAULT_FAILURE_THRESHOLD,
        backoff_levels: tuple[int, ...] = _DEFAULT_BACKOFF_LEVELS,
    ):
        self.failure_threshold = failure_threshold
        self.backoff_levels = backoff_levels
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._backoff_index = 0
        self._opened_at: float = 0.0  # timestamp when state became OPEN
        self._probe_sent: bool = False

    @property
    def state(self) -> CircuitState:
        """Current state, auto-transitioning OPEN → HALF_OPEN when backoff expires."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            backoff = self.backoff_levels[self._backoff_index]
            if elapsed >= backoff:
                self._state = CircuitState.HALF_OPEN
                self._probe_sent = False
                logger.info(
                    "Circuit breaker → HALF_OPEN (backoff %.0fs elapsed)", backoff
                )
        return self._state

    def allow_request(self) -> bool:
        """Return True if a search request is allowed."""
        current = self.state  # triggers OPEN→HALF_OPEN check
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            if not self._probe_sent:
                self._probe_sent = True
                return True  # allow one probe request
            return False  # probe already in flight
        # OPEN — still in backoff
        remaining = (
            self.backoff_levels[self._backoff_index]
            - (time.monotonic() - self._opened_at)
        )
        logger.debug(
            "Circuit breaker OPEN — request denied (%.0fs remaining)", remaining
        )
        return False

    def record_success(self) -> None:
        """Record a successful search. Resets breaker if HALF_OPEN."""
        if self._state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker → CLOSED (probe succeeded)")
            self._state = CircuitState.CLOSED
            self._consecutive_failures = 0
            self._backoff_index = 0
            self._probe_sent = False
        elif self._state == CircuitState.CLOSED:
            self._consecutive_failures = 0

    def record_failure(self, category: ErrorCategory) -> None:
        """Record a search failure. Only tripping categories affect the breaker."""
        if category not in self.TRIPPING_CATEGORIES:
            return

        self._consecutive_failures += 1
        logger.warning(
            "Circuit breaker failure %d/%d (category=%s)",
            self._consecutive_failures,
            self.failure_threshold,
            category.value,
        )

        if self._state == CircuitState.HALF_OPEN:
            # Probe failed — reopen with next backoff level
            self._backoff_index = min(
                self._backoff_index + 1, len(self.backoff_levels) - 1
            )
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            self._probe_sent = False
            logger.warning(
                "Circuit breaker → OPEN (probe failed, backoff=%ds)",
                self.backoff_levels[self._backoff_index],
            )
        elif self._consecutive_failures >= self.failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            logger.warning(
                "Circuit breaker → OPEN (threshold reached, backoff=%ds)",
                self.backoff_levels[self._backoff_index],
            )


_breaker: CircuitBreaker | None = None


def get_breaker() -> CircuitBreaker:
    """Return the module-level singleton CircuitBreaker."""
    global _breaker
    if _breaker is None:
        try:
            threshold = int(os.environ.get("CB_FAILURE_THRESHOLD", _DEFAULT_FAILURE_THRESHOLD))
            if threshold <= 0:
                raise ValueError("must be positive")
        except (ValueError, TypeError):
            logger.warning(
                "CB_FAILURE_THRESHOLD invalid, using default %d", _DEFAULT_FAILURE_THRESHOLD
            )
            threshold = _DEFAULT_FAILURE_THRESHOLD
        _breaker = CircuitBreaker(failure_threshold=threshold)
    return _breaker
