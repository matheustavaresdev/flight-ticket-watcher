# Implementation Plan: Evaluate orchestrator last_successful_date advancement on search failure

## Issues
- FLI-77: Evaluate orchestrator last_successful_date advancement on search failure

## Research Context

### Current Behavior (Problem)
In `orchestrator.py`, the `run_scan()` loop calls `_search_and_store_oneway()` for each date. That function returns an `int` (count of stored snapshots), treating both `SearchResult.failure()` and empty-but-successful results as `0`. The loop then unconditionally advances `scan_run.last_successful_date`, meaning transient failures (BLOCKED, RATE_LIMITED, NETWORK_ERROR) silently skip dates that should be retried.

### Relevant Infrastructure Already in Place
- **`SearchResult[T]`** (`models.py:44-71`): Has `ok`, `error_category`, `error`, `hint` fields. Provides all the info needed to distinguish failure types.
- **`RETRY_STRATEGIES`** (`errors.py:23-37`): Maps `ErrorCategory` → `RetryStrategy(skip_item, max_retries, ...)`:
  - `PAGE_ERROR`: `skip_item=True` — structural issue, skip this date, continue scanning
  - `BLOCKED`: `skip_item=False` — circuit breaker territory, halt scan
  - `RATE_LIMITED`: `skip_item=False` — halt scan, wait
  - `NETWORK_ERROR`: `skip_item=False` — halt scan, retry later
- **Run-level retry**: `run_all_scans()` catches exceptions from `run_scan()` → registers APScheduler retry job via `register_retry_job()`. Cursor-based resumption via `_find_resumable_run()` resumes from `last_successful_date`.
- **Circuit breaker**: Already trips on BLOCKED/RATE_LIMITED inside `search_one_way()`.

### Test Patterns
- Orchestrator tests use `unittest.TestCase` + `@patch(f"{MODULE}.function_name")`
- Factory helpers: `_make_config()`, `_make_flight_result()`, `_make_scan_run()`
- Session mocking: `MagicMock()` with `__enter__`/`__exit__` lambdas, `add()` side_effect for state capture
- Import `MODULE = "flight_watcher.orchestrator"` at module top

## Decisions Made

1. **Change `_search_and_store_oneway()` return type from `int` to `SearchResult[int]`**: The caller needs to know whether the search succeeded or failed, not just how many snapshots were stored. On success, `data` is the count. On failure, the original `SearchResult` metadata passes through.

2. **Cursor advancement logic**:
   - `ok=True` (even with 0 results): advance cursor — legitimate empty result
   - `ok=False` + `skip_item=True` (PAGE_ERROR): advance cursor — retrying won't help, date is "processed"
   - `ok=False` + `skip_item=False` (BLOCKED/RATE_LIMITED/NETWORK_ERROR): **do NOT advance cursor**, raise exception to halt scan and trigger retry job

3. **Use a dedicated `SearchFailedError`** exception raised from the loop when a non-skippable failure occurs. This integrates cleanly with the existing `except Exception` handler that sets `FAILED` status and re-raises to trigger `register_retry_job()`. The error message includes the `SearchResult.error` and `error_category` for debugging.

4. **Both directions must succeed to advance cursor**: If outbound search succeeds but return search fails with a non-skippable error, cursor is NOT advanced for that date. The retry will re-scan both directions for that date.

5. **Short-circuit on non-skippable failure**: If the outbound search fails with skip_item=False, don't attempt the return search — halt immediately. The circuit breaker is likely tripped anyway.

## Implementation Tasks

1. **Add `SearchFailedError` to `errors.py`** — affects `src/flight_watcher/errors.py`
   - Simple exception class with `error_category` attribute for downstream inspection
   - Placed alongside existing error types

2. **Change `_search_and_store_oneway()` return type** — affects `src/flight_watcher/orchestrator.py`
   - Return `SearchResult[int]` instead of `int`
   - On success: `SearchResult.success(len(snapshots))`
   - On failure: return the `SearchResult` from `search_one_way()` re-typed (data=0, preserve error fields)
   - Differentiate logging: `logger.debug` for empty success, `logger.warning` for failure with category/hint

3. **Update `run_scan()` loop to handle failures** — affects `src/flight_watcher/orchestrator.py`
   - After each `_search_and_store_oneway()` call, check `result.ok`
   - If `ok=False`: look up `get_retry_strategy(result.error_category)`
     - `skip_item=True`: log warning, continue
     - `skip_item=False`: raise `SearchFailedError` (halts loop, caught by existing except)
   - Only advance `last_successful_date` if both directions were ok or skippable
   - Extract counts from `result.data` for the debug log

4. **Add tests for failure-halts-cursor** — affects `tests/test_orchestrator.py`
   - Test: `SearchResult.failure(error_category=BLOCKED)` → cursor NOT advanced, scan FAILED
   - Test: `SearchResult.failure(error_category=NETWORK_ERROR)` → cursor NOT advanced, scan FAILED
   - Test: `SearchResult.failure(error_category=PAGE_ERROR)` → cursor advanced, scan continues
   - Test: `SearchResult.success([])` (empty result) → cursor advanced (regression guard)
   - Test: outbound fails with BLOCKED → return search NOT attempted
   - Test: outbound succeeds, return fails with RATE_LIMITED → cursor NOT advanced

5. **Add test for SearchFailedError** — affects `tests/test_errors.py`
   - Verify exception carries `error_category` attribute

## Acceptance Criteria
- When `search_one_way()` returns a failure with `skip_item=False` category (BLOCKED, RATE_LIMITED, NETWORK_ERROR), the scan halts and `last_successful_date` is NOT advanced past the failing date
- When `search_one_way()` returns a failure with `skip_item=True` category (PAGE_ERROR), the scan continues and cursor advances
- When `search_one_way()` returns success with empty data, cursor advances (existing behavior preserved)
- The existing retry job mechanism (`register_retry_job`) is triggered on non-skippable failures
- Resumption via `_find_resumable_run()` correctly resumes from the last successfully scanned date

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-77-failure-advancement
python -m pytest tests/test_orchestrator.py tests/test_errors.py -v
python -m pytest tests/ -v  # full suite
python -m pyright src/flight_watcher/orchestrator.py src/flight_watcher/errors.py
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-77` line
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Modifying `scanner.py` (already returns structured SearchResult correctly)
- Adding new error categories or retry strategies
- Modifying the circuit breaker or retry job scheduler
