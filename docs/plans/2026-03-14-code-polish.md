# Implementation Plan: Code Polish (FLI-66, FLI-79, FLI-80, FLI-82, FLI-83)

## Issues
- FLI-66: Differentiate parse_date error messages: format vs calendar validation
- FLI-79: Tighten _make_bff_intercept return type annotation
- FLI-80: Fix stdlib import ordering after adding collections.abc
- FLI-82: Make cb_backoff float() cast robust against non-numeric strings
- FLI-83: Move get_error_hint import to top-level in cli/search.py

## Research Context

All 5 issues are small code polish items from automated code reviews. Each touches a single file with a 1-5 line change.

**Codebase patterns found:**
- **Error messages:** `typer.BadParameter()` for validation errors. Existing pattern in `parse_iata` shows descriptive messages.
- **Type annotations:** Project uses Python 3.12+ modern syntax (`T | None`). No existing parameterized `Callable` usage — this will be the first.
- **Import ordering:** Strict groups: `import X` then `from X import Y`, alphabetical within each, blank lines between stdlib/third-party/local.
- **Defensive casting:** `health.py:17-21` has exact pattern for env var casting: `try/except ValueError` with user-friendly error + `typer.Exit(1)`.
- **Lazy imports:** Only used for circular dependency avoidance (e.g., `health_server.py:30`). `errors.py` has no circular deps — lazy import unnecessary.

## Decisions Made

1. **FLI-66 error messages:** Regex failure → "expected format YYYY-MM-DD". Calendar failure → "not a valid calendar date" (e.g., Feb 30). Keeps the pattern of `typer.BadParameter` with descriptive text.
2. **FLI-79 type:** Use `Callable[[Response], None]` with `from patchright.async_api import Response` since `on_response` receives a Patchright Response object. If the import would be heavy or cause issues, fall back to `Callable[[Any], None]` with `Any` from typing.
3. **FLI-80 ordering:** Move `from collections.abc import Callable` before `from datetime import datetime` (alphabetical by module name: `collections` < `datetime` < `pathlib`).
4. **FLI-82 defensive cast:** Use `try/except (ValueError, TypeError)` around `float(cb_backoff)` with fallback to printing raw value. Matches existing pattern in `health.py:17-21`.
5. **FLI-83 import move:** Move `from flight_watcher.errors import get_error_hint` to top-level imports section, alongside the existing `from flight_watcher.cli.validators import ...` import.

## Implementation Tasks

1. **FLI-66** — Differentiate error messages in `src/flight_watcher/cli/validators.py`
   - Line 25-26: Change the `except ValueError` message from `"expected format YYYY-MM-DD"` to `"not a valid calendar date"` (or similar)

2. **FLI-80** — Fix import ordering in `src/flight_watcher/latam_scraper.py`
   - Move `from collections.abc import Callable` (currently line 7, after `from datetime`) to before `from datetime import datetime` (line 6)

3. **FLI-79** — Tighten return type in `src/flight_watcher/latam_scraper.py`
   - Change `def _make_bff_intercept(captured: dict) -> Callable:` to use parameterized Callable
   - Check if `patchright.async_api.Response` is importable without side effects; if so use it, otherwise use `Any`

4. **FLI-82** — Wrap float cast in `src/flight_watcher/cli/health.py`
   - Wrap `float(cb_backoff)` in try/except, fallback to printing raw value with `typer.echo(f"  backoff remaining: {cb_backoff}")`

5. **FLI-83** — Move import in `src/flight_watcher/cli/search.py`
   - Move `from flight_watcher.errors import get_error_hint` from inside `_print_search_error` to top-level imports
   - Update the function body to just call `get_error_hint()` directly

## Acceptance Criteria

- `parse_date("2026-02-30")` produces a message mentioning "valid calendar date" (not "format YYYY-MM-DD")
- `parse_date("2026-4-1")` still produces message about "format YYYY-MM-DD"
- `_make_bff_intercept` has a parameterized `Callable` return type
- stdlib imports in `latam_scraper.py` are alphabetically ordered
- `float()` cast in `health.py` handles non-numeric strings gracefully
- `get_error_hint` is imported at top-level in `search.py`

## Verification

```bash
# Type check (if mypy/pyright configured)
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-66+79+80+82+83-code-polish
python -m py_compile src/flight_watcher/cli/validators.py
python -m py_compile src/flight_watcher/latam_scraper.py
python -m py_compile src/flight_watcher/cli/health.py
python -m py_compile src/flight_watcher/cli/search.py

# Run tests
python -m pytest tests/ -x -q

# Quick import check
python -c "from flight_watcher.cli.validators import parse_date; from datetime import date; print(parse_date('2026-03-15'))"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes (py_compile on all changed files)
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-66`, `Closes FLI-79`, `Closes FLI-80`, `Closes FLI-82`, `Closes FLI-83` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
