# Implementation Plan: Retry Scheduler (daily → hourly on failure)

## Issues
- FLI-30: Retry scheduler (daily → hourly on failure)

## Research Context

### Current Architecture
- **Daily scan**: `register_scan_job()` in `scheduler.py` adds a cron job (`daily_scan`) that calls `run_all_scans()` at `SCAN_HOUR_UTC`.
- **`run_all_scans()`**: Loads all active `SearchConfig` records, calls `run_scan(config)` for each. Catches per-config exceptions and continues to the next config.
- **`run_scan(config)`**: Creates/resumes a `ScanRun`, iterates dates, stores `PriceSnapshot` rows. On failure: sets `ScanRun.status = FAILED`, saves `error_message`, preserves cursor, then re-raises.
- **Event listeners**: `_on_job_executed` / `_on_job_error` fire for the entire `daily_scan` job, not per-config. Since `run_all_scans()` swallows per-config errors, these listeners won't detect individual config failures.
- **APScheduler**: BackgroundScheduler with PostgreSQL `SQLAlchemyJobStore`. Jobs persisted across restarts. `max_instances=1`, `coalesce=True`.

### Key Constraints
- APScheduler serializes job kwargs via pickle to PostgreSQL — only pass scalars (config_id), never ORM objects.
- `max_instances` applies per-function, not per-job-ID. Since each retry job calls the same function with different kwargs, this is fine — the function itself is fast (just dispatches to `run_scan`). But set `max_instances=1` on each retry job to prevent overlap for the same config.
- The retry job function must be a module-level importable function (no lambdas/closures).

### Test Patterns
- `unittest.TestCase` classes with `@patch` decorators
- `_make_*()` helper factories (no conftest.py)
- Module path constants: `MODULE = "flight_watcher.module"` for patch targets
- Session mocking: context manager mock pattern with `__enter__`/`__exit__`
- Singleton reset in `setUp`/`tearDown`
- `self.assertLogs()` for verifying log output

## Decisions Made

1. **Retry logic triggered from `run_all_scans()`**, not from APScheduler event listeners. Reason: `run_all_scans()` catches per-config errors, so the job-level error event never fires for individual config failures. After catching a config failure, `run_all_scans()` will call `register_retry_job(config_id)`.

2. **Retry state stored on `SearchConfig` model** via two new columns: `retry_count` (int, default 0) and `needs_attention` (bool, default False). Simpler than a separate table — retry state is inherently per-config.

3. **New module-level function `run_retry_scan(config_id)`** in `orchestrator.py` as the retry job callable. Loads config from DB, calls `run_scan()`, handles success/failure transitions (reset retry_count on success, increment on failure, mark needs_attention at max).

4. **Retry job management functions in `scheduler.py`**: `register_retry_job(config_id)` and `cancel_retry_job(config_id)`. Job ID convention: `retry_config_{config_id}`.

5. **On daily scan success for a config**: cancel any active retry job and reset retry_count. This handles the case where the daily scan succeeds before a retry fires.

6. **Config via env vars**: `RETRY_MAX_ATTEMPTS` (default 24), `RETRY_INTERVAL_MINUTES` (default 60).

## Implementation Tasks

### Task 1: Add retry columns to SearchConfig model
- **File:** `src/flight_watcher/models.py`
- Add `retry_count: Mapped[int]` with `server_default="0"` to `SearchConfig`
- Add `needs_attention: Mapped[bool]` with `server_default="false"` to `SearchConfig`

### Task 2: Create Alembic migration for new columns
- **File:** `alembic/versions/<hash>_add_retry_columns_to_search_configs.py`
- Add `retry_count` (Integer, nullable=False, server_default="0") and `needs_attention` (Boolean, nullable=False, server_default="false") to `search_configs` table
- Generate via: `cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-30-retry-scheduler && python -m alembic revision --autogenerate -m "add retry columns to search_configs"`
- Verify the generated migration is correct

### Task 3: Add retry job management to scheduler.py
- **File:** `src/flight_watcher/scheduler.py`
- Add env var constants: `RETRY_MAX_ATTEMPTS`, `RETRY_INTERVAL_MINUTES`
- Add `_retry_job_id(config_id: int) -> str` — returns `f"retry_config_{config_id}"`
- Add `register_retry_job(config_id: int) -> None`:
  - Lazy import `run_retry_scan` from orchestrator (circular import avoidance, same pattern as `register_scan_job`)
  - `scheduler.add_job(run_retry_scan, trigger="interval", minutes=RETRY_INTERVAL_MINUTES, id=_retry_job_id(config_id), kwargs={"config_id": config_id}, replace_existing=True, misfire_grace_time=300)`
  - Log the registration
- Add `cancel_retry_job(config_id: int) -> None`:
  - Try `scheduler.remove_job(_retry_job_id(config_id))`
  - Catch `JobLookupError` silently (job may not exist)
  - Log the cancellation

### Task 4: Add run_retry_scan to orchestrator.py
- **File:** `src/flight_watcher/orchestrator.py`
- Add `run_retry_scan(config_id: int) -> None`:
  - Load `SearchConfig` by id from DB (with `get_session`)
  - If config is None or `needs_attention` is True, log warning and return
  - Build config dict (same format as `run_all_scans` builds)
  - Try `run_scan(config_dict)`
  - **On success**:
    - Reset `retry_count = 0` on the SearchConfig in DB
    - Call `cancel_retry_job(config_id)` from scheduler
    - Log transition: "Retry succeeded for config {id}, resuming daily schedule"
  - **On failure**:
    - Increment `retry_count` on the SearchConfig in DB
    - If `retry_count >= RETRY_MAX_ATTEMPTS`:
      - Set `needs_attention = True`
      - Call `cancel_retry_job(config_id)` from scheduler
      - Log: "Config {id} marked as needs_attention after {count} retries"
    - Else:
      - Log: "Retry {count}/{max} failed for config {id}, next retry in {interval}min"

### Task 5: Integrate retry triggering into run_all_scans
- **File:** `src/flight_watcher/orchestrator.py`
- In `run_all_scans()`, after the `try/except` block for each config:
  - On `run_scan()` success: call `cancel_retry_job(config["id"])` and reset `retry_count = 0` (in case a retry was active)
  - On `run_scan()` failure (in the except block): call `register_retry_job(config["id"])`
- Import `register_retry_job`, `cancel_retry_job` from scheduler (lazy imports to avoid circular)

### Task 6: Write tests for retry job management (scheduler)
- **File:** `tests/test_scheduler.py`
- Test `register_retry_job`: verifies `scheduler.add_job()` called with correct args (interval trigger, correct ID, kwargs)
- Test `cancel_retry_job`: verifies `scheduler.remove_job()` called with correct ID
- Test `cancel_retry_job` when job doesn't exist: no exception raised (JobLookupError caught)
- Test `_retry_job_id`: returns expected format

### Task 7: Write tests for run_retry_scan (orchestrator)
- **File:** `tests/test_orchestrator.py`
- Test success path: `run_scan` succeeds → `retry_count` reset to 0, `cancel_retry_job` called
- Test failure path (under max): `run_scan` fails → `retry_count` incremented, retry job stays active
- Test failure path (at max): `retry_count` reaches `RETRY_MAX_ATTEMPTS` → `needs_attention = True`, retry job cancelled
- Test with missing config: logs warning, returns without action
- Test with `needs_attention=True` config: logs warning, returns without action

### Task 8: Write tests for run_all_scans retry integration
- **File:** `tests/test_orchestrator.py`
- Test: config scan succeeds → `cancel_retry_job` called, `retry_count` reset
- Test: config scan fails → `register_retry_job` called with config id
- Test: multiple configs, one fails one succeeds → correct retry jobs registered/cancelled

### Task 9: Log all transitions
- Verify all state transitions have appropriate log messages (already addressed in tasks 3-5):
  - daily → hourly (on failure): INFO log in `register_retry_job` + `run_all_scans`
  - hourly retry attempt: INFO log in `run_retry_scan`
  - hourly → daily (on retry success): INFO log in `run_retry_scan`
  - max retries → needs_attention: WARNING log in `run_retry_scan`

## Acceptance Criteria
- On scan SUCCESS: keep daily schedule, remove any hourly retry job
- On scan FAILURE: add hourly interval job for that config
- On retry SUCCESS: cancel hourly job, resume daily
- Max hourly retries: 24 (configurable via `RETRY_MAX_ATTEMPTS`) — after that, mark config as `needs_attention`
- Log all transitions for debugging

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-30-retry-scheduler
python -m pytest tests/ -x -q
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-30`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Health server changes to expose retry state (separate ticket)
- CLI commands to manage needs_attention flag (separate ticket)
