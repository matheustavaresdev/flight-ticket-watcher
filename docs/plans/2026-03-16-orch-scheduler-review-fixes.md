# Implementation Plan: Orchestrator & Scheduler Review Fixes

## Issues
- FLI-124: test: strengthen `_find_resumable_run` cutoff assertion beyond mock tautology
- FLI-125: test: add 48h boundary test for `_find_resumable_run`
- FLI-134: fix: interval trigger restart drift in scheduler (`replace_existing` resets anchor)
- FLI-135: refactor: narrow `except Exception` to `JobLookupError` in `remove_job` migration

## Research Context

### _find_resumable_run (FLI-124 & FLI-125)
- **Function:** `orchestrator.py:258-272` — queries `ScanRun` where `started_at >= cutoff` (cutoff = now - 48h), status in (FAILED, RUNNING), ordered by `started_at` DESC, limit 1.
- **Current test problem (FLI-124):** `test_find_resumable_run_returns_none_if_outside_48h` (line 402-414) sets `mock_session.scalars.return_value.first.return_value = None` directly — this is a tautology. The mock returns None regardless of what query is passed. It doesn't verify the 48h cutoff is computed correctly.
- **Boundary gap (FLI-125):** No test for a run started exactly 48h ago. The SQL uses `>=`, so exactly-48h should be found (inclusive boundary). An explicit test documents this.
- **Mock pattern:** Tests use `@patch("flight_watcher.orchestrator.datetime")` and `mock_dt.now.return_value = <fixed_time>`, with `mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)` to allow `datetime()` constructor calls. Helper `_make_scan_run()` at line 55-68.

### Scheduler (FLI-134 & FLI-135)
- **register_scan_job():** `scheduler.py:95-115`. Lines 101-103 have `try: scheduler.remove_job("daily_scan") / except Exception: pass` — migration from old job ID.
- **FLI-135:** That `except Exception` should be `except JobLookupError` (from `apscheduler.jobstores.base`), matching the pattern in `cancel_retry_job()` at line 144-152.
- **FLI-134:** `add_job(..., trigger="interval", replace_existing=True)` creates a NEW `IntervalTrigger` on every call. When `start_date` is not specified, APScheduler defaults to `datetime.now()`, so every restart resets the interval anchor. Fix: use `get_job()` to check if the job already exists; only call `add_job` if it doesn't. This avoids anchor drift while still handling first-time registration.
- **`get_job()`** returns `Job` instance or `None` (no exception). Safe to use for existence checks.

## Decisions Made

1. **FLI-124 approach:** Replace the tautological test with one that asserts on the SQL `select()` statement passed to `session.scalars()`. Capture the call args and verify the `where` clauses include the correct cutoff value (now - 48h). This tests the function's logic, not just the mock wiring.

2. **FLI-125 approach:** Add a boundary test where `started_at` is exactly `now - 48h`. Since the query uses `>=`, the run should be found. The mock should return the run to confirm inclusive boundary behavior. Also add a test at `now - 48h - 1s` where mock returns None to confirm the exclusive side.

3. **FLI-134 approach:** Use `get_job("scheduled_scan")` before `add_job()`. If the job already exists, skip re-adding. This preserves the existing trigger anchor across restarts. The migration `remove_job("daily_scan")` stays — it only runs on first upgrade. Also apply the same pattern to `register_retry_job()` for consistency.

4. **FLI-135 approach:** Import `JobLookupError` from `apscheduler.jobstores.base` and narrow the catch. Straightforward.

## Implementation Tasks

### Task 1: Narrow `except Exception` to `JobLookupError` (FLI-135)
**File:** `src/flight_watcher/scheduler.py`
- Import `JobLookupError` from `apscheduler.jobstores.base` at the top of `register_scan_job()` (local import, matching `cancel_retry_job` pattern)
- Change `except Exception:` to `except JobLookupError:` on line ~103

### Task 2: Fix interval trigger restart drift (FLI-134)
**File:** `src/flight_watcher/scheduler.py`
- In `register_scan_job()`, after the migration block, add: `if scheduler.get_job("scheduled_scan"): return` (with a log message)
- Keep the `add_job(...)` call as-is for first-time registration
- Apply the same pattern in `register_retry_job()`: check `get_job(_retry_job_id(config_id))` before adding

### Task 3: Add/update scheduler tests for FLI-134 & FLI-135
**File:** `tests/test_scheduler.py`
- Add test: `test_register_scan_job_skips_if_already_exists` — mock `get_job` to return a job, assert `add_job` not called
- Add test: `test_register_scan_job_adds_if_not_exists` — mock `get_job` to return None, assert `add_job` called
- Update existing test for migration block to verify `JobLookupError` is caught (not bare Exception)
- Add test: `test_register_retry_job_skips_if_already_exists` — same pattern for retry jobs

### Task 4: Strengthen `_find_resumable_run` cutoff assertion (FLI-124)
**File:** `tests/test_orchestrator.py`
- Rewrite `test_find_resumable_run_returns_none_if_outside_48h` (lines 402-414):
  - Keep the datetime mock at 2026-03-11 10:00 UTC
  - Keep `mock_session.scalars.return_value.first.return_value = None`
  - Add assertion: capture the `select()` statement passed to `mock_session.scalars()` and verify the cutoff datetime equals `2026-03-09 10:00 UTC` (now - 48h)
  - Use `mock_session.scalars.call_args[0][0]` to get the compiled statement, then verify the bound parameters contain the expected cutoff

### Task 5: Add 48h boundary test (FLI-125)
**File:** `tests/test_orchestrator.py`
- Add `test_find_resumable_run_includes_exactly_48h_boundary`:
  - Mock now = 2026-03-11 10:00 UTC
  - Create a run with `started_at = 2026-03-09 10:00 UTC` (exactly 48h ago)
  - Set mock to return the run
  - Assert function returns the run (documents inclusive `>=` behavior)
  - Assert the cutoff passed to the query equals `2026-03-09 10:00 UTC`

## Acceptance Criteria
- `except Exception` narrowed to `except JobLookupError` in `register_scan_job()` migration block
- `register_scan_job()` skips `add_job` when job already exists in the scheduler
- `register_retry_job()` skips `add_job` when retry job already exists
- `_find_resumable_run` outside-48h test asserts on the cutoff value, not just mock return
- Boundary test at exactly 48h documents inclusive behavior
- All existing tests continue to pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-124+125+134+135-orch-scheduler
python -m pytest tests/test_orchestrator.py tests/test_scheduler.py -v 2>&1
python -m pytest tests/ -v 2>&1
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-124`, `Closes FLI-125`, `Closes FLI-134`, `Closes FLI-135` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
