# Implementation Plan: Health command queries daemon HTTP endpoint instead of local singletons

## Issues
- FLI-50: health command queries local singletons instead of running daemon

## Research Context

### Current State
`cli/health.py` runs in a fresh CLI process and directly imports:
- `get_breaker()` from `circuit_breaker.py` — creates a brand-new breaker (always `closed`)
- `_scheduler` from `scheduler.py` — always `None` in CLI process (never started)
- `get_session()` from `db.py` — DB check (this one is fine in isolation, but the daemon already reports it)

### Target State
The daemon already runs an HTTP health server (`health_server.py`) on `HEALTH_PORT` (default 8080) that reports the real state of all singletons. The CLI should query this endpoint instead.

### HTTP Health Endpoint Response Format
```json
{
  "status": "healthy",
  "scanner": "idle",
  "started_at": "2026-03-14T...",
  "circuit_breaker": {
    "state": "closed",
    "consecutive_failures": 0,
    "backoff_remaining_sec": null
  },
  "last_successful_scans": { "<config_id>": "ISO-8601" },
  "next_scheduled_scan": "ISO-8601"
}
```

### Codebase Patterns
- HTTP client: `urllib.request` (stdlib, already used in `test_health_server.py`)
- Port config: `HEALTH_PORT` env var, default `8080`
- CLI output convention: status lines end with `[OK]`, `[WARN]`, `[FAIL]`
- Logging: `logging.getLogger(__name__)`

### Test Patterns
- CLI tests use `CliRunner` from Typer/Click
- Mocking: `unittest.mock.patch` on module-level imports
- Health test: `tests/test_cli.py::TestHealthCommand` — currently mocks `get_session` and `get_breaker`

## Decisions Made

1. **Use `urllib.request` (stdlib)** — no new dependencies, matches existing test patterns in `test_health_server.py`
2. **Read `HEALTH_PORT` env var** — same source as the daemon, consistent config
3. **Connection refused = daemon not running** — clear error message, exit code 1
4. **Timeout: 5 seconds** — health endpoint should respond near-instantly; 5s is generous
5. **Display all fields from JSON response** — scanner status, circuit breaker, last scans, next scan — more info than the current command shows
6. **Exit code**: 0 for healthy, 1 for unhealthy/unreachable — useful for scripts and Docker healthchecks

## Implementation Tasks

1. **Rewrite `src/flight_watcher/cli/health.py`** — Replace all singleton imports with HTTP GET to `http://localhost:{HEALTH_PORT}/health`. Parse JSON response. Display human-readable output. Handle connection errors (daemon not running), HTTP errors (503 shutting down), and timeouts.

   Key behaviors:
   - `urllib.request.urlopen(url, timeout=5)` → parse JSON
   - On `URLError` (connection refused): print "Daemon not reachable" + `[FAIL]`, raise `typer.Exit(1)`
   - On HTTP 503: print status from response body + `[WARN]`
   - On HTTP 200: print all fields + determine `[OK]` vs `[WARN]` based on circuit breaker state
   - Display: DB status (inferred from daemon being up), scanner status, circuit breaker (state, failures, backoff), last successful scans, next scheduled scan

2. **Update `tests/test_cli.py::TestHealthCommand`** — Replace singleton mocks with `urllib.request.urlopen` mock. Test three scenarios:
   - Daemon healthy (200 response) → `[OK]`
   - Daemon degraded (200 response, breaker open) → `[WARN]`
   - Daemon unreachable (URLError) → `[FAIL]`

## Acceptance Criteria
- `flight-watcher health` queries the daemon's HTTP `/health` endpoint
- Shows real daemon state (circuit breaker, scheduler, scanner)
- Handles daemon-not-running gracefully with clear error message
- No direct imports of `get_breaker()`, `_scheduler`, or `get_session()` in health.py
- Exit code 0 for healthy, 1 for unhealthy/unreachable

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-50-health-daemon
python -m pytest tests/test_cli.py::TestHealthCommand -v
python -m pytest tests/ -v
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-50`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Modifying the health server endpoint itself
- Changing Docker healthcheck configuration
