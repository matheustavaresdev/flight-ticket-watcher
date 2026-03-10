# Implementation Plan: APScheduler Setup with PostgreSQL Job Store

## Issues
- FLI-25: APScheduler setup with PostgreSQL job store

## Research Context

### Codebase Patterns
- **Singleton pattern:** Module-level `_var = None` with lazy `get_var()` function (see `db.py`, `circuit_breaker.py`)
- **Config from env:** Read at module level with defaults (e.g., `float(os.environ.get("MIN_DELAY_SEC", "5"))`)
- **Context managers:** `@contextmanager` for resource lifecycle (`get_session()`)
- **Logging:** `logger = logging.getLogger(__name__)` at module top
- **Entry point:** `__main__.py` with `main()` function, `logging.basicConfig()` at top
- **Docker:** `init: true` in compose (tini handles signal forwarding), `alembic upgrade head && python -m flight_watcher` as CMD

### APScheduler 3.x (Recommended)
- **Version:** `APScheduler>=3.11,<4` — 3.x is stable/production-ready; 4.x is still pre-release
- **BackgroundScheduler** runs jobs in a thread pool, non-blocking
- **SQLAlchemyJobStore** auto-creates `apscheduler_jobs` table on first use (no Alembic migration needed)
- **Jitter:** Both `CronTrigger` and `IntervalTrigger` support `jitter` param (seconds)
- **Events:** `EVENT_JOB_EXECUTED`, `EVENT_JOB_ERROR` — listener receives event with `.job_id`, `.exception`, `.retval`
- **Shutdown:** `scheduler.shutdown(wait=True)` blocks until running jobs finish
- **Gotchas:** Always set `timezone=utc` explicitly; use `coalesce=True` to avoid thundering herd on restart; `replace_existing=True` when re-adding jobs on restart

### Test Patterns
- `unittest.mock.patch` for module-level singletons
- `patch.dict(os.environ, ...)` for env var isolation
- Helper functions prefixed with `_` (e.g., `_make_breaker()`)
- Module path constant: `SCHED_MODULE = "flight_watcher.scheduler"`
- No DB integration tests — all mocked

## Decisions Made

1. **APScheduler 3.x, not 4.x** — 4.x is pre-release with breaking API changes. 3.x is mature.
2. **Let APScheduler auto-create its table** — The `apscheduler_jobs` table is internal to APScheduler. No Alembic migration needed. It auto-creates on first scheduler start.
3. **New `scheduler.py` module** — Follows existing pattern of one module per concern. Contains scheduler factory, event listeners, and lifecycle management.
4. **CronTrigger for daily scan** — Issue specifies "daily trigger at configurable hour". Use `CronTrigger(hour=X, jitter=1800)` for ±30min jitter.
5. **`SCAN_HOUR_UTC` env var** — Integer 0-23, default `0`. Simpler than full cron expression for this use case. The existing `SCAN_SCHEDULE` env var in `.env.example` will be replaced.
6. **No placeholder job** — The scheduler module exposes `get_scheduler()` and `start()`/`stop()`. Actual scan jobs will be registered by future issues. `__main__.py` starts the scheduler and keeps the process alive.
7. **Reuse `get_database_url()` from `db.py`** — Single source of truth for DB connection string. Pass to `SQLAlchemyJobStore(url=...)`.
8. **`replace_existing=True` on `add_job()`** — Safe for container restarts since jobs persist in PostgreSQL. Avoids "job already exists" errors.

## Implementation Tasks

### Task 1: Add APScheduler dependency
- **File:** `pyproject.toml`
- Add `"APScheduler>=3.11,<4"` to `dependencies` list

### Task 2: Create `scheduler.py` module
- **File:** `src/flight_watcher/scheduler.py`
- Implement:
  - `_scheduler: BackgroundScheduler | None = None` module-level singleton
  - `create_scheduler() -> BackgroundScheduler` — builds scheduler with:
    - `SQLAlchemyJobStore(url=get_database_url(), tablename="apscheduler_jobs")`
    - `ThreadPoolExecutor(max_workers=4)`
    - `job_defaults`: `coalesce=True`, `max_instances=1`, `misfire_grace_time=300`
    - `timezone=utc`
  - `get_scheduler() -> BackgroundScheduler` — lazy singleton accessor
  - `_on_job_executed(event)` — logs job completion at INFO level
  - `_on_job_error(event)` — logs job failure at ERROR level with exception details
  - Event listeners registered in `create_scheduler()`
  - `start_scheduler()` — calls `get_scheduler().start()`, logs startup
  - `stop_scheduler()` — calls `scheduler.shutdown(wait=True)`, resets singleton, logs shutdown

### Task 3: Update `__main__.py` for scheduler lifecycle
- **File:** `src/flight_watcher/__main__.py`
- Replace one-shot search with:
  - Import `start_scheduler`, `stop_scheduler` from `scheduler`
  - Register `signal.SIGTERM` and `signal.SIGINT` handlers that call `stop_scheduler()` then `sys.exit(0)`
  - Call `start_scheduler()`
  - Main loop: `while True: time.sleep(1)` (keeps process alive for BackgroundScheduler)
  - Wrap in try/except KeyboardInterrupt for clean exit

### Task 4: Update `.env.example`
- **File:** `.env.example`
- Replace `SCAN_SCHEDULE=*/30 * * * *` with `SCAN_HOUR_UTC=0`
- Add comment explaining the value range (0-23)

### Task 5: Write tests for `scheduler.py`
- **File:** `tests/test_scheduler.py`
- Tests:
  - `test_create_scheduler_returns_background_scheduler` — verify type and config
  - `test_create_scheduler_uses_database_url` — mock `get_database_url`, verify SQLAlchemyJobStore receives it
  - `test_get_scheduler_returns_singleton` — two calls return same instance
  - `test_get_scheduler_resets_after_stop` — after `stop_scheduler()`, next `get_scheduler()` creates new instance
  - `test_on_job_executed_logs_info` — mock logger, fire event, verify INFO log
  - `test_on_job_error_logs_error` — mock logger, fire event with exception, verify ERROR log
  - `test_start_scheduler_calls_start` — mock scheduler, verify `.start()` called
  - `test_stop_scheduler_calls_shutdown_with_wait` — mock scheduler, verify `.shutdown(wait=True)` called
  - `test_scheduler_configured_with_utc` — verify timezone is UTC
  - `test_scheduler_job_defaults` — verify coalesce=True, max_instances=1

### Task 6: Write tests for `__main__.py` signal handling
- **File:** `tests/test_main.py`
- Tests:
  - `test_main_registers_signal_handlers` — mock `signal.signal`, verify SIGTERM and SIGINT registered
  - `test_main_starts_scheduler` — mock `start_scheduler`, verify called
  - `test_signal_handler_stops_scheduler` — invoke the handler, verify `stop_scheduler()` called

## Acceptance Criteria
- APScheduler configured with BackgroundScheduler and PostgreSQL job store
- Daily trigger at configurable hour (default 00:00 UTC)
- Jitter on start time (±30min) to avoid detection patterns
- Event listeners for JOB_ERROR and JOB_EXECUTED events
- Graceful shutdown on SIGTERM
- Jobs persist across container restarts (PostgreSQL store)

## Verification
```bash
# Install deps
pip install -e ".[test]"

# Run tests
pytest tests/test_scheduler.py tests/test_main.py -v

# Run full test suite (no regressions)
pytest -v

# Verify import works
python -c "from flight_watcher.scheduler import create_scheduler, start_scheduler, stop_scheduler; print('OK')"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-25`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Actual scan job functions (separate issue)
- Route configuration or management
- Price storage or alerting logic
- Alembic migration for APScheduler tables (auto-created by APScheduler)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
