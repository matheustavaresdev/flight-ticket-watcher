# Implementation Plan: Graceful Shutdown + Health Check Endpoint

## Issues
- FLI-31: Graceful shutdown handling
- FLI-37: Health check endpoint

## Research Context

### Current State
- **Signal handling** already exists in `__main__.py`: SIGTERM/SIGINT → `stop_scheduler()` → `sys.exit(0)`
- **APScheduler** already uses `shutdown(wait=True)` — blocks until running jobs finish
- **Browser** is context-manager scoped per search in `latam_scraper.py` — no persistent instance to clean up. `shutdown(wait=True)` lets the running job (and its browser session) finish naturally.
- **DB engine** has no disposal mechanism — connections leak on shutdown
- **Circuit breaker** is an in-memory singleton with state/backoff/failure tracking
- **Docker** uses `init: true` (tini) for signal forwarding, no healthcheck on scanner service
- **No HTTP server** exists — project has no web framework dependency

### Test Patterns
- pytest with `unittest.mock`, no conftest.py
- Helper functions prefixed `_` (e.g., `_make_breaker()`)
- Singleton reset in `setUp()`/`tearDown()`
- Patch at import location: `"flight_watcher.module.func"`
- Patch `time.monotonic()` for time-dependent state transitions

### Codebase Conventions
- One module per concern, singleton pattern with `_var` + `get_var()`
- Logging: `logger = logging.getLogger(__name__)` per module
- Environment config with defaults: `os.environ.get("VAR", "default")`
- Context managers for resource lifecycle

## Decisions Made

1. **HTTP server**: Use stdlib `http.server.HTTPServer` in a daemon thread. The health endpoint is a single GET route returning JSON — no need for FastAPI/Starlette. Zero new dependencies.

2. **Scanner status tracking**: New module `scanner_state.py` with a thread-safe status tracker (enum: IDLE, SCANNING, SHUTTING_DOWN). APScheduler job listeners update it. Follows the existing singleton pattern (`_state` + `get_state()`).

3. **"Save cursor to DB"**: Not needed as a separate step. `shutdown(wait=True)` lets the running job finish its natural DB writes (ScanRun completion). APScheduler's SQLAlchemyJobStore already persists job schedule state to PostgreSQL.

4. **DB engine disposal**: Add `dispose_engine()` to `db.py`, called during shutdown after scheduler stops.

5. **Health endpoint port**: Default `8080`, configurable via `HEALTH_PORT` env var.

6. **Unhealthy criteria**: Return HTTP 503 when scanner status is SHUTTING_DOWN. Return 200 otherwise with full status payload. Docker healthcheck uses HTTP status code.

## Implementation Tasks

### Task 1: Scanner state tracker — `src/flight_watcher/scanner_state.py` (new)

Thread-safe module tracking scanner status for the health endpoint.

```python
import threading
from enum import Enum
from datetime import datetime, timezone

class ScannerStatus(Enum):
    IDLE = "idle"
    SCANNING = "scanning"
    SHUTTING_DOWN = "shutting_down"

class ScannerState:
    def __init__(self):
        self._lock = threading.Lock()
        self._status = ScannerStatus.IDLE
        self._started_at: datetime  # when the app started

    # Properties: status (get/set), started_at
    # Method: to_dict() for JSON serialization
```

Singleton: `_state` + `get_scanner_state()`.

### Task 2: Wire scanner state into scheduler — modify `src/flight_watcher/scheduler.py`

Update `_on_job_executed` and `_on_job_error` listeners to set scanner state to IDLE after job completes. The job function itself (once it exists) will set SCANNING at the start. For now, add a `_on_job_started` listener using `EVENT_JOB_SUBMITTED` to set SCANNING.

Actually — simpler: add `EVENT_JOB_SUBMITTED` listener → set SCANNING; existing `_on_job_executed` / `_on_job_error` → set IDLE.

### Task 3: DB engine disposal — modify `src/flight_watcher/db.py`

Add `dispose_engine()`:
```python
def dispose_engine() -> None:
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        SessionLocal = None
        logger.info("Database engine disposed")
```

### Task 4: Health server — `src/flight_watcher/health_server.py` (new)

Stdlib `HTTPServer` running in a daemon thread. Single route: `GET /health`.

Response body (JSON):
```json
{
  "status": "healthy",
  "scanner": "idle",
  "started_at": "2026-03-13T10:00:00Z",
  "circuit_breaker": {
    "state": "closed",
    "consecutive_failures": 0,
    "backoff_remaining_sec": null
  },
  "last_successful_scans": {
    "1": "2026-03-13T09:30:00Z"
  },
  "next_scheduled_scan": "2026-03-13T10:30:00Z"
}
```

- HTTP 200 when operational, HTTP 503 when SHUTTING_DOWN
- `last_successful_scans`: query `scan_runs` table for latest completed_at per search_config_id
- `next_scheduled_scan`: query APScheduler's `get_jobs()` for nearest `next_run_time`
- Functions: `start_health_server()`, `stop_health_server()`

### Task 5: Enhanced graceful shutdown — modify `src/flight_watcher/__main__.py`

Replace the simple `_handle_signal` with a proper shutdown sequence:

```python
def _handle_signal(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    get_scanner_state().status = ScannerStatus.SHUTTING_DOWN
    stop_health_server()
    stop_scheduler()       # blocks until running jobs finish
    dispose_engine()       # clean up DB connections
    logger.info("Shutdown complete")
    sys.exit(0)
```

Update `main()` to start health server before scheduler:
```python
def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    start_health_server()
    start_scheduler()
    ...
```

Also update the `KeyboardInterrupt` handler in the while loop to follow the same sequence.

### Task 6: Docker healthcheck — modify `docker-compose.yml`

Add to scanner service:
```yaml
ports:
  - "8080:8080"
healthcheck:
  test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"]
  interval: 30s
  timeout: 5s
  retries: 3
  start_period: 30s
```

### Task 7: Environment config — modify `.env.example`

Add `HEALTH_PORT=8080`.

### Task 8: Tests — `tests/test_scanner_state.py` (new)

- Status transitions (IDLE → SCANNING → IDLE)
- Thread safety (concurrent set/get)
- `to_dict()` serialization
- Singleton behavior

### Task 9: Tests — `tests/test_health_server.py` (new)

- Server starts and responds on configured port
- GET /health returns 200 with expected JSON structure
- Returns 503 when SHUTTING_DOWN
- Non-/health paths return 404
- `stop_health_server()` shuts down cleanly

### Task 10: Tests — update `tests/test_main.py`

- Signal handler calls shutdown sequence in correct order: set SHUTTING_DOWN → stop health server → stop scheduler → dispose engine → sys.exit(0)
- `main()` starts health server before scheduler

### Task 11: Tests — update `tests/test_db.py`

- `dispose_engine()` disposes engine and resets globals

### Task 12: Tests — update `tests/test_scheduler.py`

- Job listeners update scanner state (SUBMITTED → SCANNING, EXECUTED/ERROR → IDLE)

## Acceptance Criteria

From FLI-31:
- [x] SIGTERM/SIGINT finish current in-progress search (APScheduler `wait=True`)
- [x] Shutdown APScheduler cleanly
- [x] Close browser instance (handled by context manager in running job)
- [x] DB connections disposed
- [x] Exit with code 0

From FLI-37:
- [x] GET /health returns last successful scan time per config
- [x] Returns current scanner status (idle/scanning/shutting_down)
- [x] Returns circuit breaker state
- [x] Returns next scheduled scan time
- [x] Docker healthcheck configured to use /health

## Verification

```bash
# Unit tests
python -m pytest tests/ -v

# Type checking (if configured)
# python -m mypy src/flight_watcher/

# Lint
ruff check src/ tests/

# Docker build
docker compose build scanner
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-31` and `Closes FLI-37` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Persisting circuit breaker state to DB (separate future issue)
- Browser lifecycle management beyond what context managers already handle
