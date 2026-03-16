# Implementation Plan: Orchestrator Post-FLI-96 Fixes

## Issues
- FLI-97: fix(orchestrator): cross-midnight retries re-scan already-committed dates causing duplicate snapshots
- FLI-98: fix(orchestrator): add explicit session.commit() after setting COMPLETED status
- FLI-99: chore(tests): remove pre-existing unused ScanRun import in test_outbound_blocked_short_circuits_return_search
- FLI-100: fix(orchestrator): persist RUNNING status transition for resumed scan runs

## Research Context

### Codebase Structure
- **orchestrator.py** (~388 lines): `run_scan()` is the main entry (line 127). `_find_resumable_run()` at line 256. `_search_and_store_oneway()` at line 287.
- **models.py**: `ScanRun` model (line 116), `ScanStatus` enum (line 74: RUNNING/COMPLETED/FAILED).
- **db.py**: `get_session()` context manager (line 55) — auto-commits on clean exit, rollbacks on exception.
- **tests/test_orchestrator.py** (~1093 lines): Uses `@patch` decorators, `MagicMock` sessions, `_make_scan_run()` helper (line 55), `_setup_session_mock()` (line 142).

### Key Code Flow (run_scan)
1. Expand dates → try `_find_resumable_run()`
2. If resumable: reuse ScanRun, set status=RUNNING, clear error_message (**no commit** — FLI-100)
3. If new: create ScanRun, add, flush, **commit** (line 163)
4. Filter remaining dates after cursor
5. Per-date loop: search outbound → search return → update cursor → **commit** (line 232)
6. On success: set COMPLETED + completed_at (**no commit** — FLI-98)
7. On exception: rollback → set FAILED → **commit** (line 249)

### Session/Commit Pattern
Per-date commits (FLI-96) already exist. The pattern is: mutate state → `session.commit()`. FLI-98 and FLI-100 just add missing commits at two transition points to match this pattern.

### Test Patterns
- Commit count assertions: `mock_session.commit.call_count` (e.g., line 856: 1 initial + N dates + 1 final)
- Rollback assertions: `mock_session.rollback.assert_called_once()`
- `_make_scan_run()` helper for resumable runs with configurable status/cursor/started_at
- `add_side_effect` pattern to capture ScanRun at `session.add()` time

## Decisions Made

### FLI-97: Extend `_find_resumable_run()` lookback window
Change the query from "today only" to "last 48 hours". Rationale:
- 48h covers any midnight-spanning scan with generous margin (retry delays, long scans)
- No need for configurable N-day lookback — scans run at most daily per config
- Keep `.order_by(started_at.desc()).limit(1)` so we always get the most recent
- No deduplication logic needed — preventing the re-scan is cleaner than deduplicating after

### FLI-98: Add `session.commit()` after COMPLETED
Single line addition after line 242 (after `logger.info`). Matches the per-date commit pattern.

### FLI-99: Remove `ScanRun` from import
Change `from flight_watcher.models import SearchResult, ScanRun` to `from flight_watcher.models import SearchResult` at line 807.

### FLI-100: Add `session.commit()` after resumed RUNNING transition
Single line addition after the resumed run's status/error_message update (after line 149, before the logger.info). Matches the new-run creation pattern (line 163).

## Implementation Tasks

### Task 1: Fix `_find_resumable_run()` lookback window (FLI-97)
**File:** `src/flight_watcher/orchestrator.py` (~line 258-259)

Change:
```python
today = datetime.now(tz=timezone.utc).date()
today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
```
To:
```python
cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
```

And update the query filter:
```python
.where(ScanRun.started_at >= cutoff)
```

Update the docstring from "Find today's failed/running ScanRun" to "Find recent failed/running ScanRun".

Ensure `timedelta` is imported (check existing imports).

### Task 2: Add `session.commit()` after COMPLETED status (FLI-98)
**File:** `src/flight_watcher/orchestrator.py` (~line 242)

Add `session.commit()` after the `logger.info("Scan run %d completed", scan_run.id)` line.

### Task 3: Add `session.commit()` after resumed RUNNING transition (FLI-100)
**File:** `src/flight_watcher/orchestrator.py` (~line 149)

Add `session.commit()` after `scan_run.error_message = None` (line 149), before the `logger.info` call.

### Task 4: Remove unused ScanRun import (FLI-99)
**File:** `tests/test_orchestrator.py` (~line 807)

Change:
```python
from flight_watcher.models import SearchResult, ScanRun
```
To:
```python
from flight_watcher.models import SearchResult
```

### Task 5: Add test for cross-midnight resumption (FLI-97)
**File:** `tests/test_orchestrator.py`

Add a test `test_cross_midnight_resumption_finds_yesterdays_failed_run` in the appropriate test class. Setup:
- Create a `_make_scan_run()` with `started_at` set to yesterday (e.g., 23:55 UTC)
- Set `mock_find.return_value` to this run (Note: `_find_resumable_run` is already mocked via `@patch`, so this test needs to test the actual `_find_resumable_run()` function directly)

Actually, since `_find_resumable_run` is patched in all `RunScanTests`, this test should be a **separate unit test** for `_find_resumable_run()` itself. Create a new test class `FindResumableRunTests` that:
- Creates real ScanRun records via the mock session's `scalars` return
- Tests that a run from yesterday (within 48h) is found
- Tests that a run from 3 days ago (outside 48h) is NOT found

### Task 6: Update commit count assertions in existing tests (FLI-98, FLI-100)
**File:** `tests/test_orchestrator.py`

Adding commits in FLI-98 and FLI-100 changes the commit counts in existing tests:
- FLI-100 adds 1 commit for resumed runs → update any resumption test that checks `commit.call_count`
- FLI-98 adds 1 commit for COMPLETED status → update success-path tests that check `commit.call_count`

Scan all tests that assert on `mock_session.commit.call_count` and adjust counts:
- Success path (non-resumed): +1 for COMPLETED commit (FLI-98)
- Success path (resumed): +1 for RUNNING commit (FLI-100) + 1 for COMPLETED commit (FLI-98)
- Failure path (non-resumed): no change (COMPLETED commit not reached)
- Failure path (resumed): +1 for RUNNING commit (FLI-100)

### Task 7: Add test for explicit COMPLETED commit (FLI-98)
**File:** `tests/test_orchestrator.py`

Add a test that verifies `session.commit()` is called after COMPLETED status is set. Can verify by checking commit count includes the COMPLETED commit (may already be covered by Task 6 adjustments).

### Task 8: Add test for resumed RUNNING commit (FLI-100)
**File:** `tests/test_orchestrator.py`

Add a test `test_resumed_run_commits_running_status` that:
- Sets up a resumable FAILED run via `mock_find`
- Runs `run_scan()` successfully
- Verifies commit count includes the RUNNING transition commit
- Verifies `scan_run.status` was set to RUNNING before the date loop

## Acceptance Criteria
- `_find_resumable_run()` finds runs from the past 48 hours, not just today (FLI-97)
- `session.commit()` is called after setting COMPLETED status (FLI-98)
- Unused `ScanRun` import removed from test (FLI-99)
- `session.commit()` is called after transitioning resumed run to RUNNING (FLI-100)
- All existing tests pass with updated commit counts
- New tests cover cross-midnight resumption and explicit status commits

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-97+98+99+100-orchestrator-fixes
python -m pytest tests/test_orchestrator.py -v
python -m pytest tests/ -v
ruff check src/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-97`, `Closes FLI-98`, `Closes FLI-99`, `Closes FLI-100` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
