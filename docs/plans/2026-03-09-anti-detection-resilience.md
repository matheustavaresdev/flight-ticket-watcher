# Implementation Plan: Anti-Detection & Resilience (FLI-33 + FLI-34)

## Issues
- FLI-33: Randomized delays between searches
- FLI-34: Error classification system

## Research Context

### Current State
- **scanner.py** (fast-flights): Has basic retry (3 attempts, `2^n` backoff), catches bare `Exception`, returns `[]` on failure. Hardcoded `time.sleep(2)` between outbound/inbound legs.
- **latam_scraper.py** (Patchright): No retry logic. Catches `Exception` and prints to stdout (not logger). Returns `None` on failure. Hardcoded `page.wait_for_timeout(1000-5000)` for UI waits.
- **No config module** — no `os.environ` reads, no `.env.example`.
- **No scheduling layer** — single-run scripts only. Schedule jitter (±30min) from FLI-33 is future work for the scheduler epic.

### Test Patterns
- pytest with `unittest.mock` (no pytest fixtures)
- Helpers as `_prefixed` module-level functions
- Patch at import location: `"flight_watcher.scanner.time.sleep"`
- Error tests use `side_effect=Exception(...)`, assert graceful degradation

### Anti-Bot Stack (for error classification)
- **Akamai**: 403 + `_abck`/`bm_sz` cookies → BLOCKED
- **429 / CAPTCHA challenge** → RATE_LIMITED
- **Timeouts, DNS, connection reset** → NETWORK_ERROR
- **Element not found, parse failure** → PAGE_ERROR

## Decisions Made

1. **Two new modules**: `src/flight_watcher/delays.py` and `src/flight_watcher/errors.py`. Small, composable, testable independently.

2. **Config via `os.environ.get()` with defaults** — no new dependency. Constants at module top level. No config class (premature for current scope).

3. **Error classification uses an Enum + classifier function**, not an exception hierarchy. Reason: we catch third-party exceptions (Playwright timeouts, HTTP errors) that we can't subclass. Classification happens after catching.

4. **Retry strategy is a dataclass** mapping each `ErrorCategory` to delay range + max retries. This replaces the hardcoded `2^n` backoff in scanner.py.

5. **`random.uniform()` for delays** — simple, sufficient. No need for normal/exponential distribution; uniform with configurable bounds already breaks bot patterns.

6. **Replace `print()` with `logger`** in latam_scraper.py only where we touch error handling code. Don't refactor all prints (out of scope).

7. **Schedule jitter (±30min on daily start time)** is NOT implemented here — no scheduler exists yet. FLI-33 scope is inter-search delays only.

## Implementation Tasks

### Task 1: Create `src/flight_watcher/errors.py`
New module with:

```python
import enum
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

class ErrorCategory(enum.Enum):
    RATE_LIMITED = "rate_limited"      # 429, CAPTCHA challenge
    NETWORK_ERROR = "network_error"    # timeout, DNS, connection
    PAGE_ERROR = "page_error"          # element not found, parse failure
    BLOCKED = "blocked"                # Akamai challenge, 403

@dataclass(frozen=True)
class RetryStrategy:
    max_retries: int
    min_delay_sec: float
    max_delay_sec: float
    skip_item: bool  # if True, skip this date/route and continue

RETRY_STRATEGIES: dict[ErrorCategory, RetryStrategy] = {
    ErrorCategory.RATE_LIMITED: RetryStrategy(max_retries=1, min_delay_sec=1800, max_delay_sec=3600, skip_item=False),
    ErrorCategory.NETWORK_ERROR: RetryStrategy(max_retries=3, min_delay_sec=60, max_delay_sec=300, skip_item=False),
    ErrorCategory.PAGE_ERROR: RetryStrategy(max_retries=0, min_delay_sec=0, max_delay_sec=0, skip_item=True),
    ErrorCategory.BLOCKED: RetryStrategy(max_retries=0, min_delay_sec=0, max_delay_sec=0, skip_item=False),
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
    network_keywords = ["dns", "connection", "reset", "refused", "unreachable", "eof", "broken pipe"]
    if any(kw in exc_msg for kw in network_keywords):
        return ErrorCategory.NETWORK_ERROR

    # CAPTCHA / bot detection in message
    if "captcha" in exc_msg or "challenge" in exc_msg:
        return ErrorCategory.RATE_LIMITED

    # Page interaction errors (element not found, selector issues)
    page_keywords = ["locator", "selector", "element", "not found", "no such", "parse", "json", "key error"]
    if any(kw in exc_msg for kw in page_keywords):
        return ErrorCategory.PAGE_ERROR

    # Default: treat unknown as network error (retry-able)
    return ErrorCategory.NETWORK_ERROR

def get_retry_strategy(category: ErrorCategory) -> RetryStrategy:
    """Get the retry strategy for an error category."""
    return RETRY_STRATEGIES[category]
```

Log format when classifying: `logger.warning("error_category=%s status=%s message=%s", category.value, status_code, exc)`

### Task 2: Create `src/flight_watcher/delays.py`
New module with:

```python
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
```

### Task 3: Integrate delays into `scanner.py`
- Replace hardcoded `time.sleep(2)` at line 54 (between outbound/inbound) with `random_delay()`.
- Keep retry backoff as-is (exponential is fine for retries; FLI-33 is about inter-search delays).

### Task 4: Integrate error classification into `scanner.py`
- Replace bare `except Exception as exc` with classification:
  ```python
  except Exception as exc:
      category = classify_error(exc)
      strategy = get_retry_strategy(category)
      if strategy.skip_item:
          logger.warning("search_one_way %s→%s %s: %s (category=%s) — skipping",
                         origin, destination, date, exc, category.value)
          return []
      if attempt < strategy.max_retries:
          wait = random.uniform(strategy.min_delay_sec, strategy.max_delay_sec)
          # Cap retry delay for fast-flights (it's fast, no need for 30min waits)
          wait = min(wait, 30)
          logger.warning("search_one_way %s→%s %s failed (attempt %d/%d, category=%s): %s — retrying in %.0fs",
                         origin, destination, date, attempt + 1, strategy.max_retries, category.value, exc, wait)
          time.sleep(wait)
      else:
          logger.error("search_one_way %s→%s %s failed after %d attempts (category=%s): %s",
                       origin, destination, date, attempt + 1, category.value, exc)
  ```
  Note: fast-flights doesn't give HTTP status codes, so `classify_error(exc)` uses exception message only.

### Task 5: Integrate error classification into `latam_scraper.py`
- At each `except Exception as e: print(...)` block, replace with:
  ```python
  except Exception as exc:
      category = classify_error(exc)
      logger.warning("latam search failed (category=%s): %s", category.value, exc)
  ```
- Add `from flight_watcher.errors import classify_error` import.
- Add `logger = logging.getLogger(__name__)` (replace print-based error reporting).
- Don't add retry logic to latam_scraper yet — that's orchestrator-level concern (future scheduler).

### Task 6: Create `.env.example`
```
# Anti-detection delays (seconds)
MIN_DELAY_SEC=5
MAX_DELAY_SEC=15
```

### Task 7: Write tests — `tests/test_delays.py`
- `test_random_delay_sleeps_within_range`: patch `time.sleep`, verify called with value in [min, max]
- `test_random_delay_uses_env_defaults`: patch `os.environ`, verify defaults applied
- `test_random_delay_uses_custom_range`: pass explicit min/max, verify range

### Task 8: Write tests — `tests/test_errors.py`
- `test_classify_429_as_rate_limited`: `classify_error(Exception(""), status_code=429)` → RATE_LIMITED
- `test_classify_403_as_blocked`: `classify_error(Exception(""), status_code=403)` → BLOCKED
- `test_classify_timeout_as_network_error`: `classify_error(Exception("Timeout 30000ms"))` → NETWORK_ERROR
- `test_classify_element_not_found_as_page_error`: `classify_error(Exception("element not found"))` → PAGE_ERROR
- `test_classify_unknown_as_network_error`: `classify_error(Exception("something weird"))` → NETWORK_ERROR
- `test_retry_strategy_rate_limited_has_long_backoff`: verify min_delay >= 1800
- `test_retry_strategy_page_error_skips`: verify `skip_item=True`
- `test_retry_strategy_blocked_no_retry`: verify `max_retries=0, skip_item=False`

### Task 9: Update existing tests in `test_scanner.py`
- Tests that mock `time.sleep` need to also handle `random_delay` import.
- `test_search_one_way_handles_exception`: verify it still returns `[]` (behavior unchanged).

## Acceptance Criteria
- [ ] `random_delay()` produces delays in configured range (verified by test)
- [ ] `MIN_DELAY_SEC` / `MAX_DELAY_SEC` env vars are respected
- [ ] Roundtrip search in scanner.py uses randomized delay between legs
- [ ] All errors are classified into one of 4 categories
- [ ] Each category maps to a concrete retry strategy
- [ ] Error classification logs include category name
- [ ] latam_scraper.py error paths use logger instead of print
- [ ] All new code has tests
- [ ] Existing tests still pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-33+34-anti-detection
python -m pytest tests/ -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-33` `Closes FLI-34` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding retry logic to latam_scraper.py (orchestrator concern)
- Schedule jitter (±30min) — no scheduler exists yet
- Circuit breaker implementation for BLOCKED category (future)
- Replacing all print() calls in latam_scraper.py (only error paths)
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
