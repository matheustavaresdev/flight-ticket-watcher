# Implementation Plan: Circuit Breaker Pattern

## Issues
- FLI-35: Circuit breaker pattern

## Research Context

### Existing Error Classification (errors.py)
The codebase already has `ErrorCategory.BLOCKED` (403/Akamai) with a comment: *"BLOCKED: circuit breaker — stop all searches, don't just skip one"*. Current `RetryStrategy` for BLOCKED is `max_retries=0, skip_item=False` — it stops retrying the current search but doesn't halt other searches.

### Two Search Implementations
- **scanner.py** (fast-flights): Has retry loop with `classify_error()` + `get_retry_strategy()`. Returns `[]` on failure.
- **latam_scraper.py** (Patchright): Uses `classify_error()` for logging only. No retry logic. Catches bare `Exception`.

### Patterns & Conventions
- Config: `os.environ.get(var, default)` at module level
- Logging: `logging.getLogger(__name__)` everywhere
- Delays: `random_delay()` from `delays.py`, uses `time.sleep()`
- Tests: pytest + `unittest.mock`, `_make_*` helpers, patch at import site, no fixtures
- All sync code, single-process

### Integration Points
- `ErrorCategory.BLOCKED` and `ErrorCategory.RATE_LIMITED` should trip the breaker
- Both `scanner.py` and `latam_scraper.py` need to check breaker state before searching
- No scheduler exists yet — breaker tracks state across calls within the same process lifetime

## Decisions Made

1. **New module** `src/flight_watcher/circuit_breaker.py` — keeps state machine isolated from error classification
2. **Global breaker** (not per-route) — BLOCKED/RATE_LIMITED means the entire service is blocked, not a specific route
3. **In-memory state** — no persistence needed (no scheduler yet; process restarts reset to CLOSED, which is safe)
4. **Backoff levels as a tuple** — `(900, 1800, 3600, 7200)` seconds (15min → 30min → 1h → 2h). Index increments on each HALF_OPEN failure, capped at last level.
5. **`CircuitBreaker` class** with methods: `allow_request() -> bool`, `record_success()`, `record_failure(category: ErrorCategory)` — simple API for callers
6. **Module-level singleton** — `get_breaker() -> CircuitBreaker` returns a shared instance. Callers import and use it.
7. **Only BLOCKED and RATE_LIMITED trip the breaker** — NETWORK_ERROR and PAGE_ERROR are transient/local, not service-level blocks

## Implementation Tasks

### Task 1: Create `circuit_breaker.py` module
**File:** `src/flight_watcher/circuit_breaker.py`

```python
"""Circuit breaker to halt searches when the upstream service is blocking us."""

import logging
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

    @property
    def state(self) -> CircuitState:
        """Current state, auto-transitioning OPEN → HALF_OPEN when backoff expires."""
        if self._state == CircuitState.OPEN:
            elapsed = time.monotonic() - self._opened_at
            backoff = self.backoff_levels[self._backoff_index]
            if elapsed >= backoff:
                self._state = CircuitState.HALF_OPEN
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
            return True  # allow one probe request
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
        threshold = int(os.environ.get("CB_FAILURE_THRESHOLD", _DEFAULT_FAILURE_THRESHOLD))
        _breaker = CircuitBreaker(failure_threshold=threshold)
    return _breaker
```

Note: Add `import os` at the top. The env var `CB_FAILURE_THRESHOLD` overrides the default threshold.

### Task 2: Integrate into `scanner.py`
**File:** `src/flight_watcher/scanner.py`

In `search_one_way()`, before the retry loop:
```python
from flight_watcher.circuit_breaker import get_breaker

breaker = get_breaker()
if not breaker.allow_request():
    logger.warning("Circuit breaker OPEN — skipping search %s→%s on %s", origin, destination, date)
    return []
```

After a successful search (results obtained):
```python
breaker.record_success()
```

In the exception handler, after classifying the error:
```python
breaker.record_failure(category)
if not breaker.allow_request():
    logger.warning("Circuit breaker tripped — aborting remaining retries")
    break
```

### Task 3: Integrate into `latam_scraper.py`
**File:** `src/flight_watcher/latam_scraper.py`

In `search_latam_roundtrip()`, before launching browser:
```python
from flight_watcher.circuit_breaker import get_breaker

breaker = get_breaker()
if not breaker.allow_request():
    logger.warning("Circuit breaker OPEN — skipping LATAM search %s→%s", origin, destination)
    return None, None
```

After successful response capture:
```python
breaker.record_success()
```

In exception handler:
```python
category = classify_error(exc, status_code=getattr(exc, 'status', None))
breaker.record_failure(category)
```

### Task 4: Add `CB_FAILURE_THRESHOLD` to `.env.example`
**File:** `.env.example`

Add:
```
CB_FAILURE_THRESHOLD=3
```

### Task 5: Write tests for `circuit_breaker.py`
**File:** `tests/test_circuit_breaker.py`

Tests to write (following existing test patterns):

```python
"""Tests for circuit_breaker module."""

from unittest.mock import patch

from flight_watcher.circuit_breaker import CircuitBreaker, CircuitState
from flight_watcher.errors import ErrorCategory

CB_MODULE = "flight_watcher.circuit_breaker"


def _make_breaker(threshold=3, backoff_levels=(10, 20, 40)):
    """Create a breaker with short backoffs for testing."""
    return CircuitBreaker(failure_threshold=threshold, backoff_levels=backoff_levels)


def test_initial_state_is_closed():
    cb = _make_breaker()
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_failures_below_threshold_stay_closed():
    cb = _make_breaker(threshold=3)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.CLOSED
    assert cb.allow_request() is True


def test_threshold_reached_opens_circuit():
    cb = _make_breaker(threshold=3)
    for _ in range(3):
        cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN
    assert cb.allow_request() is False


def test_non_tripping_categories_ignored():
    cb = _make_breaker(threshold=1)
    cb.record_failure(ErrorCategory.NETWORK_ERROR)
    cb.record_failure(ErrorCategory.PAGE_ERROR)
    assert cb.state == CircuitState.CLOSED


def test_rate_limited_trips_breaker():
    cb = _make_breaker(threshold=2)
    cb.record_failure(ErrorCategory.RATE_LIMITED)
    cb.record_failure(ErrorCategory.RATE_LIMITED)
    assert cb.state == CircuitState.OPEN


def test_success_resets_failure_count():
    cb = _make_breaker(threshold=3)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_failure(ErrorCategory.BLOCKED)
    cb.record_success()
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.CLOSED  # only 1 consecutive failure


def test_open_transitions_to_half_open_after_backoff():
    cb = _make_breaker(threshold=1, backoff_levels=(5,))
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN

    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 5):
        assert cb.state == CircuitState.HALF_OPEN
        assert cb.allow_request() is True


def test_half_open_success_closes_circuit():
    cb = _make_breaker(threshold=1, backoff_levels=(0,))
    cb.record_failure(ErrorCategory.BLOCKED)
    # Force transition to HALF_OPEN
    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 1):
        _ = cb.state  # trigger transition
    cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert cb._backoff_index == 0


def test_half_open_failure_reopens_with_higher_backoff():
    cb = _make_breaker(threshold=1, backoff_levels=(10, 20, 40))
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb._backoff_index == 0

    # Transition to HALF_OPEN
    with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 10):
        _ = cb.state
    # Probe fails
    cb.record_failure(ErrorCategory.BLOCKED)
    assert cb.state == CircuitState.OPEN
    assert cb._backoff_index == 1  # escalated


def test_backoff_index_capped_at_max():
    cb = _make_breaker(threshold=1, backoff_levels=(1, 2))
    # Trip → HALF_OPEN → fail → Trip → HALF_OPEN → fail → Trip
    for i in range(5):
        cb.record_failure(ErrorCategory.BLOCKED)
        with patch(f"{CB_MODULE}.time.monotonic", return_value=cb._opened_at + 9999):
            _ = cb.state  # force HALF_OPEN
    assert cb._backoff_index == len(cb.backoff_levels) - 1


def test_get_breaker_returns_singleton():
    with patch.dict("os.environ", {"CB_FAILURE_THRESHOLD": "5"}):
        # Reset the module-level singleton
        import flight_watcher.circuit_breaker as mod
        mod._breaker = None
        b1 = mod.get_breaker()
        b2 = mod.get_breaker()
        assert b1 is b2
        assert b1.failure_threshold == 5
        mod._breaker = None  # cleanup
```

## Acceptance Criteria
- Circuit breaker tracks consecutive BLOCKED/RATE_LIMITED failures
- After N failures (default 3), circuit opens and denies requests
- Backoff escalates: 15min → 30min → 1h → 2h
- HALF_OPEN state allows one probe; success → CLOSED, failure → OPEN with escalated backoff
- Both `scanner.py` and `latam_scraper.py` check breaker before searching
- All state transitions logged
- Threshold configurable via `CB_FAILURE_THRESHOLD` env var

## Verification
```bash
python -m pytest tests/ -v
python -m pytest tests/test_circuit_breaker.py -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-35`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Persistent circuit breaker state (DB/file) — future work when scheduler lands
