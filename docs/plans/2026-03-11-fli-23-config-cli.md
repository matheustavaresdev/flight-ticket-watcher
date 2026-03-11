# Implementation Plan: CLI for Managing Search Configs

## Issues
- FLI-23: CLI for managing search configs

## Research Context

### Database Model
`SearchConfig` in `src/flight_watcher/models.py` (lines 49-66) has: `id`, `origin` (String(3)), `destination` (String(3)), `must_arrive_by` (Date), `must_stay_until` (Date), `max_trip_days` (Integer), `active` (Boolean, default true), `created_at`, `updated_at`.

### Session Pattern
`src/flight_watcher/db.py` provides `get_session()` context manager — auto-commits on clean exit, auto-rollbacks on exception.

### Date Expansion
`src/flight_watcher/date_expansion.py` provides `expand_dates(must_arrive_by, must_stay_until, max_trip_days)` and `generate_pairs()`. Already validates: max_trip_days > 0, must_stay_until >= must_arrive_by, min_stay <= max_trip_days.

### Current Entry Point
`src/flight_watcher/__main__.py` runs the scheduler (long-running process). CLI needs to coexist — `__main__.py` will dispatch based on `sys.argv`.

### Test Patterns
- `tests/test_*.py`, no conftest.py
- `_make_*` helper functions for test objects
- `unittest.mock.patch` for DB sessions
- `patch.dict(os.environ, ...)` for env vars
- Mix of class-based and function-based tests

### No CLI Framework Installed
No Click/Typer in dependencies. Need to add one.

## Decisions Made

1. **CLI framework: Click.** It's the standard Python CLI framework, well-established, zero extra dependencies beyond itself. Typer adds unnecessary complexity for 3 commands. Click is also what Flask/other major projects use.

2. **Module structure: single `src/flight_watcher/cli.py` file.** Only 3 commands — a package would be over-engineering.

3. **Entry point: modify `__main__.py` to dispatch.** When invoked as `python -m flight_watcher config ...`, route to Click CLI. When invoked with no args or `scheduler` subcommand, run the existing scheduler. This matches the issue's specified invocation pattern.

4. **Output: simple formatted tables using Click's `echo`.** No need for rich/tabulate — Click's built-in formatting is sufficient. Use fixed-width columns for `config list`.

5. **Validation strategy: reuse `expand_dates()` validation + IATA code check (3 uppercase alpha chars).** Click callback validates dates as YYYY-MM-DD. Catch `ValueError` from `expand_dates()` and print friendly error via `click.ClickException`.

6. **`config add` shows date pair count after creation** as a confirmation of what was configured.

## Implementation Tasks

### Task 1: Add Click dependency
- **File:** `pyproject.toml`
- Add `"click>=8.1"` to `dependencies` list

### Task 2: Create `src/flight_watcher/cli.py`
- **File:** `src/flight_watcher/cli.py` (new)
- Click group `cli` as top-level
- Subgroup `config` with commands: `add`, `list`, `deactivate`

**`config add` command:**
```
python -m flight_watcher config add FOR MIA 2026-06-21 2026-06-28 --max-days 15
```
- Arguments: `origin` (str), `destination` (str), `must_arrive_by` (date), `must_stay_until` (date)
- Option: `--max-days` (int, required)
- Validation:
  - IATA codes: uppercase, exactly 3 alpha chars. Auto-uppercase the input.
  - Dates: parse as `date` objects via Click's `DateTime` type or custom callback
  - Call `expand_dates()` to validate date/max_days consistency — catch `ValueError`
- On success: create `SearchConfig`, save to DB, print confirmation with ID and date pair count

**`config list` command:**
```
python -m flight_watcher config list
```
- Option: `--all` flag to include inactive configs (default: active only)
- Query `SearchConfig` from DB, order by `id`
- Print table: ID | Origin | Dest | Arrive By | Stay Until | Max Days | Active

**`config deactivate` command:**
```
python -m flight_watcher config deactivate <id>
```
- Argument: `config_id` (int)
- Set `active = False` on the matching `SearchConfig`
- If not found, raise `click.ClickException`
- Print confirmation

### Task 3: Wire `__main__.py` to dispatch to CLI
- **File:** `src/flight_watcher/__main__.py`
- When `sys.argv` has subcommands (e.g., `config`), invoke the Click CLI
- When no args or `scheduler` subcommand, run existing scheduler logic
- Implementation: add `scheduler` as a Click command too, make it the default when no subcommand given

Actually, cleaner approach: make the Click group the main entry point. Add `scheduler` as a command alongside `config`. When invoked with no subcommand, show help (standard Click behavior). The scheduler is invoked as `python -m flight_watcher scheduler`.

### Task 4: Write tests — `tests/test_cli.py`
- **File:** `tests/test_cli.py` (new)
- Use Click's `CliRunner` for testing (built-in test utility)
- Test cases:
  - `config add` with valid inputs → creates SearchConfig in DB (mock session)
  - `config add` with invalid IATA code → error message
  - `config add` with must_stay_until < must_arrive_by → error message
  - `config add` with max_days too small → error message
  - `config list` with active configs → table output
  - `config list --all` → includes inactive
  - `config deactivate` with valid ID → sets active=False
  - `config deactivate` with non-existent ID → error message
- Mock `get_session()` to avoid real DB dependency (matches project pattern)

### Task 5: Install and verify
- Run `pip install -e ".[test]"` to install click dependency
- Run `pytest tests/test_cli.py` to verify tests pass
- Run `python -m flight_watcher config add --help` to verify CLI works

## Acceptance Criteria
- `python -m flight_watcher config add FOR MIA 2026-06-21 2026-06-28 --max-days 15` stores config in `search_configs` table
- `python -m flight_watcher config list` shows active configs in table format
- `python -m flight_watcher config deactivate <id>` sets config as inactive
- Validates dates: `must_stay_until > must_arrive_by`, `max_days >= min_stay`
- IATA codes validated (3 alpha chars)
- All tests pass

## Verification
```bash
pip install -e ".[test]"
pytest tests/ -v
python -m flight_watcher config add --help
python -m flight_watcher config list --help
python -m flight_watcher config deactivate --help
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-23`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Adding rich/tabulate for output formatting
- `config edit` or `config delete` commands (not in issue)
