# Implementation Plan: Typer CLI Entry Point + Structured Logging

## Issues
- FLI-47: Add Typer CLI entry point
- FLI-48: Replace print() with structured logging

## Research Context

### Current State
- **CLI framework:** Click >=8.1 with a single `cli.py` containing a `config` group (add/list/deactivate) and a `scheduler` command.
- **Entry point:** `__main__.py` sets up `logging.basicConfig()`, imports `cli` from `cli.py`, invokes it. No `[project.scripts]` in pyproject.toml.
- **Logging:** All core modules already use `logger = logging.getLogger(__name__)`. However, `latam_scraper.py` has 17 `print()` calls mixed with logger calls. `display.py` has 5 `print()` calls (CLI-only formatter — acceptable).
- **Scripts:** `scripts/find_cheapest.py`, `best_combinations.py`, `roundtrip_vs_oneway.py` use argparse + print. `find_cheapest.py` is superseded by the new `search latam` command.
- **Tests:** Use `click.testing.CliRunner`, `unittest.TestCase`, `@patch` for mocking. No conftest.py. Helpers are `_make_*()` functions in each test file.

### Typer Library
- **Version:** `typer[all]>=0.24.0` (includes Rich; requires Python 3.10+, project needs 3.12 ✓)
- **Built on Click:** Drop-in upgrade. Typer wraps Click internally.
- **Subcommands:** Use `typer.Typer()` sub-apps with `app.add_typer(sub_app, name="group")`.
- **Testing:** `from typer.testing import CliRunner` — same API as Click's CliRunner.
- **Gotcha:** Rich startup adds ~0.5s cold start. Can disable with `TYPER_USE_RICH=false`.

### Architecture Decision: CLI Package Structure
Use a `cli/` package with submodules instead of a single file. The issue describes 5 command groups (search, config, runs, scheduler, health) — a single file would grow unwieldy.

```
src/flight_watcher/
├── __main__.py          # imports app, calls app()
├── cli/
│   ├── __init__.py      # main Typer app + add_typer() calls
│   ├── search.py        # search latam, search fast
│   ├── config.py        # config list, config add, config toggle
│   ├── runs.py          # runs list
│   ├── scheduler.py     # scheduler start
│   └── health.py        # health
└── display.py           # CLI-only formatters (print_results, print_offers)
```

### Logging Decision
- Replace `print()` with `logger.info()`/`logger.debug()` in core modules only.
- Keep `display.py` and `print_offers()` as CLI-only formatters using `typer.echo()` / Rich console.
- Configure logging level via CLI callback: `--verbose` → DEBUG, default → INFO, `--quiet` → WARNING.
- The `logging.basicConfig()` call stays in the CLI callback (not module level).

## Decisions Made

1. **Typer over Click:** FLI-47 spec explicitly requires Typer. Type-hint-based commands are cleaner.
2. **`cli/` package:** 5 command groups warrant submodules. Each submodule exports a `typer.Typer()` sub-app.
3. **`typer[all]`:** Include Rich for better table output and help formatting.
4. **Remove `click` dependency:** Typer includes Click internally; no need for separate `click>=8.1`.
5. **Keep `display.py` using print/echo:** It's CLI-only formatting, not core logic. Migrate its `print()` to `typer.echo()`.
6. **Don't delete scripts/ yet:** FLI-47 says remove `find_cheapest.py` only. Keep `best_combinations.py` and `roundtrip_vs_oneway.py` for now — they query DB directly and aren't superseded yet.
7. **Status line convention:** Every command ends with `[OK]`, `[FAIL]`, or `[WARN]` status line per FLI-47 spec.
8. **Verbosity via app callback:** `--verbose`/`-v` flag on the root app sets logging level globally.

## Implementation Tasks

### Task 1: Update dependencies in pyproject.toml
- Replace `click>=8.1` with `typer[all]>=0.24.0` in `[project.dependencies]`
- Add `[project.scripts]` section: `flight-watcher = "flight_watcher.cli:app"`

### Task 2: Create `cli/` package with main app
- Create `src/flight_watcher/cli/__init__.py`:
  - Define root `app = typer.Typer(help="Flight ticket price monitoring CLI")`
  - Add callback for `--verbose`/`-v` flag that configures `logging.basicConfig()`
  - Import and register all sub-apps via `app.add_typer()`
- Rename existing `src/flight_watcher/cli.py` → delete after migrating logic to submodules

### Task 3: Create `cli/config.py` — config subcommands
- Migrate from existing `cli.py` Click commands to Typer equivalents:
  - `config list [--all]` — list active (or all) search configs
  - `config add <origin> <dest> <arrive-by> <stay-until> [--max-days N]` — create config
  - `config toggle <id>` — toggle active/inactive (replaces `deactivate`)
- Use `typer.echo()` for output, status line at end
- Validation: IATA codes (3 uppercase letters), dates (YYYY-MM-DD), max-days > 0

### Task 4: Create `cli/search.py` — search subcommands
- `search latam --origin FOR --dest GRU --out 2026-04-12 [--in 2026-04-17] [--headless]`
  - Calls `search_latam_oneway()` or `search_latam_roundtrip()` based on `--in` presence
  - Parses offers with `parse_offers()`, displays with `print_offers()` from display.py
  - Shows status line: `[OK] 12 flights found (3.2s)` or `[FAIL] ...`
- `search fast --origin FOR --dest GRU --date 2026-04-12 [--return-date 2026-04-17]`
  - Calls `search_one_way()` or `search_roundtrip()` from scanner.py
  - Displays with `print_results()` from display.py
  - Shows status line

### Task 5: Create `cli/runs.py` — runs subcommand
- `runs list [--config-id N] [--last N]`
  - Queries ScanRun table, shows recent scan runs with status, timing, error info
  - Default: last 10 runs across all configs

### Task 6: Create `cli/scheduler.py` — scheduler subcommand
- `scheduler start`
  - Replicates current `__main__.py` scheduler behavior (signal handlers, health server, APScheduler)
  - This is the "long-running daemon" mode

### Task 7: Create `cli/health.py` — health subcommand
- `health`
  - DB connection check (try `get_session()`, execute `SELECT 1`)
  - Circuit breaker state via `get_breaker().status_info()`
  - Scheduler status (if running)
  - Formats as readable table with status indicators

### Task 8: Update `__main__.py`
- Simplify to just import and run the Typer app:
  ```python
  from flight_watcher.cli import app
  app()
  ```
- Remove old Click import, old `logging.basicConfig()` (moved to CLI callback), old `main()` function

### Task 9: Replace print() in `latam_scraper.py` (FLI-48)
- Line 103, 158, 304: `print(f"Search completed in {elapsed:.1f}s")` → `logger.info("Search completed in %.1fs", elapsed)`
- Line 199: `print(f"  [BFF] captured {count} offers")` → `logger.info("BFF captured %d offers", count)`
- Line 201: `print(f"  [BFF] error: {e}")` → `logger.warning("BFF error: %s", e)`
- Line 232: `print(f"Outbound: {count} offers")` → `logger.info("Outbound: %d offers", count)`
- Line 287: `print(f"Return BFF captured")` → `logger.debug("Return BFF response captured")`
- Line 298: `print(f"Return: {count} offers")` → `logger.info("Return: %d offers", count)`
- Line 363: `print(f"Response saved to {filename}")` → `logger.info("Response saved to %s", filename)`
- Lines 374-401 (if __name__ block): Remove or convert to a thin CLI wrapper that calls search functions

### Task 10: Audit and fix remaining print() in core modules
- Check `scanner.py`, `scheduler.py`, `circuit_breaker.py`, `orchestrator.py`, `db.py` for any stray `print()`
- Replace with appropriate logger level
- Verify `display.py` print() calls are acceptable (CLI-only formatter)

### Task 11: Update `display.py` to use typer.echo()
- Replace `print()` calls with `typer.echo()` for proper stdout handling
- Keep as CLI-only formatter module (not imported by core logic)

### Task 12: Delete `scripts/find_cheapest.py`
- Superseded by `flight-watcher search latam`
- Keep `best_combinations.py` and `roundtrip_vs_oneway.py` (not yet superseded)

### Task 13: Update tests
- Migrate `tests/test_cli.py` from `click.testing.CliRunner` to `typer.testing.CliRunner`
- Update imports: `from flight_watcher.cli import app` (now Typer app)
- Add tests for new commands:
  - `test_search_latam_invokes_scraper` — mock `search_latam_oneway`, verify CLI output
  - `test_search_fast_invokes_scanner` — mock `search_one_way`, verify CLI output
  - `test_health_shows_status` — mock `get_session`, `get_breaker`, verify output
  - `test_runs_list_shows_recent` — mock session, verify table output
  - `test_scheduler_start_calls_main` — mock scheduler functions, verify called
  - `test_verbose_flag_sets_debug` — invoke with `-v`, verify logging level
- Verify existing config tests still pass after migration
- Add test: `test_no_print_in_core_modules` — grep for `print(` in core modules, assert zero hits (excluding display.py and cli/)

### Task 14: Verify no print() leaks
- Run: `grep -rn "print(" src/flight_watcher/ --include="*.py" | grep -v "cli/" | grep -v "display.py" | grep -v "print_offers\|print_results"`
- Should return zero results

## Acceptance Criteria

### FLI-47
- `flight-watcher --help` shows all commands with descriptions
- `flight-watcher search latam` triggers a real LATAM search and outputs results
- `flight-watcher search fast` triggers a fast-flights search
- `flight-watcher health` reports DB connection, circuit breaker state, scheduler status
- `flight-watcher scheduler start` replicates current `__main__.py` behavior
- `flight-watcher config list/add/toggle` work as before
- `flight-watcher runs list` shows recent scan runs
- Consistent `[OK]`/`[FAIL]`/`[WARN]` status line on all command outputs

### FLI-48
- Zero `print()` calls in `scanner.py`, `latam_scraper.py`, `scheduler.py`, `circuit_breaker.py`
- `print()` only in CLI layer (`cli/`) and display formatters (`display.py`)
- All debug/progress info goes through logging
- Logging config respects level (`--verbose` → DEBUG, default → INFO)

## Verification

```bash
# Build check
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-47+48-cli-logging
pip install -e .

# Unit tests
python -m pytest tests/ -v

# CLI smoke tests
flight-watcher --help
flight-watcher config list
flight-watcher health

# Print() audit
grep -rn "print(" src/flight_watcher/ --include="*.py" | grep -v "cli/" | grep -v "display.py" | grep -v "# noqa"
# Expected: zero results (or only display formatting functions)

# Lint
python -m ruff check src/flight_watcher/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes (`pip install -e .`)
- [ ] Tests pass (`pytest tests/ -v`)
- [ ] Print audit clean (zero print() in core modules)
- [ ] PR created with `Closes FLI-47` and `Closes FLI-48`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding Rich tables/formatting beyond basic `typer.echo()` (future enhancement)
- Adding tests for scripts/ (they're standalone utilities)
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Migrating `best_combinations.py` or `roundtrip_vs_oneway.py` to CLI commands
