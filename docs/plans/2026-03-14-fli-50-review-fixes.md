# Implementation Plan: FLI-50 Code Review Fixes

## Issues
- FLI-55: health: validate HEALTH_PORT env var is numeric before int() conversion
- FLI-56: test(health): scope urlopen mock to module level instead of stdlib
- FLI-57: test(health): remove redundant MagicMock import inside _make_urlopen_mock
- FLI-58: test(health): add test for non-JSON HTTPError body fallback path

## Research Context

### Files to modify
- `src/flight_watcher/cli/health.py` — HEALTH_PORT validation (FLI-55)
- `tests/test_cli.py` — mock scope, redundant import, new test (FLI-56, FLI-57, FLI-58)

### Existing patterns
- **CLI validation:** Project uses `typer.BadParameter()` for validation errors (see `cli/validators.py` for IATA/date validation). Health command uses `typer.echo()` + `raise typer.Exit(1)` for runtime errors.
- **Env var handling:** `os.environ.get("VAR", "default")` with direct `int()` conversion, no validation layer currently exists.
- **Test framework:** pytest + `typer.testing.CliRunner`. Test classes group related commands. `MagicMock` imported at file level (line 6).
- **Mock pattern:** Tests use `patch.dict("os.environ", ...)` for env vars. urlopen currently patched at stdlib level (`"urllib.request.urlopen"`).
- **HTTPError handling in health.py:** Lines 23-30 catch `HTTPError`, attempt JSON parse of body, catch `json.JSONDecodeError` for non-JSON bodies. This fallback path has no test coverage.

### Architecture note
`health_server.py:94` has the same `int(os.environ.get("HEALTH_PORT", "8080"))` without validation. That's in a different module and out of scope for these issues — the review finding specifically targets `health.py`.

## Decisions Made
- **FLI-55 validation approach:** Use `try/except ValueError` around `int()` conversion, print a clear error via `typer.echo()` and `raise typer.Exit(1)`. This matches the health command's existing error pattern (echo + Exit) rather than `typer.BadParameter()` which is for CLI argument validation, not env var validation.
- **FLI-56 mock target:** Change from `"urllib.request.urlopen"` to `"flight_watcher.cli.health.urllib.request.urlopen"` — standard Python mock best practice (patch where imported).
- **FLI-58 test structure:** Add a new test method `test_health_daemon_http_error_non_json_body` to `TestHealthCommand` that sends an HTTPError with `fp=io.BytesIO(b"Bad Gateway")` and verifies the fallback error message is displayed.

## Implementation Tasks

1. **FLI-55: Add HEALTH_PORT validation** — `src/flight_watcher/cli/health.py`
   - Wrap `int(os.environ.get("HEALTH_PORT", "8080"))` in try/except ValueError
   - On ValueError: `typer.echo("Error: HEALTH_PORT must be numeric, got '<value>'")` + `raise typer.Exit(1)`
   - Add a test `test_health_invalid_port_env_var` that sets `HEALTH_PORT=abc` and asserts exit_code 1 and error message

2. **FLI-57: Remove redundant MagicMock import** — `tests/test_cli.py`
   - Remove `from unittest.mock import MagicMock` inside `_make_urlopen_mock()` method body (line ~300)
   - Verify the file-level import on line 6 already includes MagicMock

3. **FLI-56: Scope urlopen mock to module level** — `tests/test_cli.py`
   - Change all `patch("urllib.request.urlopen", ...)` to `patch("flight_watcher.cli.health.urllib.request.urlopen", ...)`
   - This affects all test methods in `TestHealthCommand` that use the urlopen mock

4. **FLI-58: Add non-JSON HTTPError body test** — `tests/test_cli.py`
   - Add `test_health_daemon_http_error_non_json_body` to `TestHealthCommand`
   - Create an HTTPError with `fp=io.BytesIO(b"Bad Gateway")`, code=502
   - Assert exit_code 1 and that the output contains the HTTP error status (not a JSON parse crash)

## Acceptance Criteria
- HEALTH_PORT with non-numeric value prints friendly error and exits 1 (not a traceback)
- All urlopen mocks target module-level path
- No redundant imports in `_make_urlopen_mock`
- Non-JSON HTTPError body path has test coverage
- All existing tests still pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-50-health-daemon
python -m pytest tests/test_cli.py -v -k "health" 2>&1
python -m pytest tests/ -v 2>&1
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR updated with all `Closes FLI-55`, `Closes FLI-56`, `Closes FLI-57`, `Closes FLI-58` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Fixing the same HEALTH_PORT issue in `health_server.py` (different module, different issue)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
