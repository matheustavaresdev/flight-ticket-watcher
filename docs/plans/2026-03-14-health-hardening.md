# Implementation Plan: Health Command Hardening

## Issues
- FLI-67: health: guard cb_backoff format spec against non-float type
- FLI-68: test(health): assert no traceback in test_health_invalid_port_env_var
- FLI-69: health: add DB connectivity signal to health response
- FLI-70: health: distinguish circuit breaker tripped from daemon unhealthy in exit code

## Research Context

### Current Health Architecture
- **Health server** (`src/flight_watcher/health_server.py`): HTTP endpoint at `/health`, returns JSON with `status`, `scanner`, `started_at`, `circuit_breaker`, `last_successful_scans`, `next_scheduled_scan`. HTTP 200 for healthy, 503 for shutting down.
- **Health CLI** (`src/flight_watcher/cli/health.py`): Queries the daemon endpoint, displays status, exits 0 for healthy or 1 for any issue (CB open, daemon unreachable, HTTP error).
- **Circuit breaker** (`src/flight_watcher/circuit_breaker.py`): `status_info()` returns `{"state", "consecutive_failures", "backoff_remaining_sec"}`. `backoff_remaining_sec` is `float` when state=open (via `max(0.0, remaining)`), `None` otherwise. Only `BLOCKED`/`RATE_LIMITED` errors trip it.
- **DB query** in health server (lines 43-56): queries `ScanRun` for last successful scans. On exception, logs warning and returns empty dict — **no signal to CLI that DB is down**.

### Test Patterns
- CLI tests use `typer.testing.CliRunner`, check `result.exit_code` and `result.output`.
- HTTP mocking via `_make_urlopen_mock()` helper in `TestHealthCommand`.
- Health server integration tests use real HTTP server + `_find_free_port()`.
- Environment patching via `patch.dict("os.environ", ...)`.

## Decisions Made

### Exit Code Semantics (FLI-70)
Using three exit codes:
- **Exit 0**: Fully healthy (daemon up, DB reachable, CB closed)
- **Exit 2**: Degraded-but-running (CB open/half_open — daemon is correctly backing off from upstream rate limits, not itself broken). Monitoring should alert but NOT restart.
- **Exit 1**: Unhealthy (daemon unreachable, DB down, shutting down, HTTP errors). Monitoring should restart.

Rationale: CB tripped is a normal operational state (upstream blocked us), not a daemon failure. Using exit 2 prevents false restarts from liveness probes. This is the standard `degraded` pattern (Kubernetes uses exit 1 for failure but custom probes can distinguish).

### DB Connectivity Signal (FLI-69)
Adding `"db_reachable": true|false` field to the health response JSON. When `false`, the CLI shows a warning and factors it into exit code determination:
- DB unreachable + CB closed → exit 1 (unhealthy — daemon can't persist results)
- DB unreachable + CB open → exit 1 (unhealthy takes priority over degraded)
- DB reachable + CB open → exit 2 (degraded)
- DB reachable + CB closed → exit 0 (healthy)

### cb_backoff Guard (FLI-67)
Wrap with `float()` cast: `f"  backoff remaining: {float(cb_backoff):.0f}s"`. Simple defensive cast handles any numeric type from JSON deserialization.

## Implementation Tasks

### Task 1: Add `db_reachable` field to health server response (FLI-69)
**File:** `src/flight_watcher/health_server.py`

In `_get_health_data()`:
- Add `db_reachable = True` before the DB query try block (line 42)
- In the `except` block (line 55), set `db_reachable = False`
- Add `"db_reachable": db_reachable` to the response dict (after line 67)

### Task 2: Guard cb_backoff format spec (FLI-67)
**File:** `src/flight_watcher/cli/health.py`

Line 56: Change from:
```python
typer.echo(f"  backoff remaining: {cb_backoff:.0f}s")
```
To:
```python
typer.echo(f"  backoff remaining: {float(cb_backoff):.0f}s")
```

### Task 3: Add DB status display + exit code distinction to CLI (FLI-69 + FLI-70)
**File:** `src/flight_watcher/cli/health.py`

After extracting `cb_backoff` (line 47), add:
```python
db_reachable = data.get("db_reachable", True)  # default True for backward compat
```

After the circuit breaker display (line 56), add DB status line:
```python
typer.echo(f"Database:         {'reachable' if db_reachable else 'UNREACHABLE'}")
```

Replace the exit code logic (lines 64-68) with:
```python
if not db_reachable:
    typer.echo("[FAIL] database is unreachable")
    raise typer.Exit(1)
elif cb_state in ("open", "half_open"):
    typer.echo(f"[WARN] circuit breaker is {cb_state}")
    raise typer.Exit(2)
else:
    typer.echo("[OK]")
```

### Task 4: Assert no traceback in test (FLI-68)
**File:** `tests/test_cli.py`

In `test_health_invalid_port_env_var`, add after the existing assertions:
```python
assert "Traceback" not in result.output
```

### Task 5: Update existing health CLI tests for new exit codes (FLI-70)
**File:** `tests/test_cli.py`

- `test_health_daemon_degraded_breaker_open`: Change `assert result.exit_code == 1` → `assert result.exit_code == 2`
- Verify `[WARN]` is still asserted (it should be)

### Task 6: Add test for DB unreachable signal (FLI-69)
**File:** `tests/test_cli.py`

Add new test `test_health_daemon_db_unreachable` in `TestHealthCommand`:
- Mock response with `"db_reachable": False`, CB closed, status healthy
- Assert exit code 1
- Assert `"UNREACHABLE"` in output
- Assert `"[FAIL]"` in output

### Task 7: Add test for degraded exit code 2 (FLI-70)
**File:** `tests/test_cli.py`

Add new test `test_health_daemon_breaker_open_exit_code_2`:
- Mock response with CB open, `"db_reachable": True`
- Assert exit code 2 (not 1)
- Assert `"[WARN]"` in output

### Task 8: Add test for cb_backoff type guard (FLI-67)
**File:** `tests/test_cli.py`

Add new test `test_health_cb_backoff_string_type`:
- Mock response with `"backoff_remaining_sec": "45"` (string, not float)
- Assert no crash (exit code 2 since CB is open)
- Assert `"backoff remaining: 45s"` in output

### Task 9: Update health server test for db_reachable field (FLI-69)
**File:** `tests/test_health_server.py`

In existing integration tests, assert `"db_reachable"` key exists in response JSON and is `True` when DB is mocked successfully.

Add new test `test_health_db_unreachable`:
- Mock `get_session` to raise an exception
- Assert response contains `"db_reachable": False`
- Assert HTTP status is still 200 (daemon is up, just DB is down)

## Acceptance Criteria

- `cb_backoff` format string handles non-float types without crashing (FLI-67)
- `test_health_invalid_port_env_var` asserts no traceback in output (FLI-68)
- Health response includes `db_reachable` boolean field (FLI-69)
- CLI displays database connectivity status (FLI-69)
- Exit code 0 = healthy, exit code 2 = degraded (CB tripped), exit code 1 = unhealthy (FLI-70)
- DB unreachable → exit 1 regardless of CB state (FLI-69 + FLI-70)
- All existing tests updated, new tests added

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-67+68+69+70-health-hardening
python -m pytest tests/test_cli.py::TestHealthCommand -v
python -m pytest tests/test_health_server.py -v
python -m pytest tests/ -v --tb=short
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-XX` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Changing HTTP status codes from the health server (200/503 stay as-is)
- Adding health check retries or timeout configuration
