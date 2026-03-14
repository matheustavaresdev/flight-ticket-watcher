# Implementation Plan: Harden parse_date + Add Clarifying Comment

## Issues
- FLI-53: Harden parse_date to strictly enforce YYYY-MM-DD format
- FLI-54: Add comment clarifying str(parse_date()) pattern in search.py

## Research Context

### Current State
- `parse_date` in `validators.py:17-21` uses `date.fromisoformat()` which on Python 3.11+ accepts extended ISO formats (`2026-04-01T00:00:00`, `+002026-04-01`, `2026-4-1`). The function's contract is strict `YYYY-MM-DD` but it doesn't enforce that.
- `parse_iata` already follows a guard-then-parse pattern: length check + `isalpha()` before returning.
- `search.py` calls `str(parse_date(out))` at lines 28, 30, 75, 77 — the pattern validates then normalizes back to string. No comment explains why.
- `config.py:25-26` also uses `parse_date()` but keeps the `date` object (no `str()` roundtrip).

### Test Coverage
- `tests/test_cli.py:311-318` tests invalid date format `"2026/04/01"` is rejected.
- `tests/test_cli.py:329-336` same for `search fast`.
- No test currently verifies that extended ISO formats like `"2026-4-1"` or `"2026-04-01T00:00:00"` are rejected.

### Codebase Pattern
Validators raise `typer.BadParameter` with descriptive messages. Guard-first style (see `parse_iata`).

## Decisions Made

**FLI-53 — Use regex pre-check** over `len() == 10` guard alone. A regex `^\d{4}-\d{2}-\d{2}$` is a single check that enforces both length and format, rejecting `2026-4-1` (single-digit month/day) and `2026-04-01T00:00:00` (trailing content). This is more explicit than a length-only guard and matches the validator's stated contract. Keep the `date.fromisoformat()` call after the regex to validate actual date values (e.g., reject `2026-02-30`).

**FLI-54 — Add comment at all `str(parse_date(...))` call sites** in `search.py` (lines 28, 30, 75, 77). The issue mentions lines 28 and 30, but lines 75 and 77 follow the identical pattern and should get the same comment for consistency. Use: `# validate and normalize to YYYY-MM-DD`.

## Implementation Tasks

1. **Add regex guard to `parse_date`** — `src/flight_watcher/cli/validators.py`
   - Import `re` at top of file
   - Add `_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")` module-level constant
   - Add guard before `date.fromisoformat()`: if not matching, raise `typer.BadParameter`

2. **Add inline comments in search.py** — `src/flight_watcher/cli/search.py`
   - Add `# validate and normalize to YYYY-MM-DD` above or inline at lines 28, 30, 75, 77

3. **Add test cases for strict format enforcement** — `tests/test_cli.py`
   - Test that `"2026-4-1"` (single-digit components) is rejected
   - Test that `"2026-04-01T00:00:00"` (datetime string) is rejected
   - Test that `"+002026-04-01"` (extended year) is rejected
   - Follow existing pattern: invoke CLI command, assert `exit_code != 0` and error contains `"Invalid date"`

## Acceptance Criteria
- `parse_date("2026-04-01")` succeeds (valid YYYY-MM-DD)
- `parse_date("2026-4-1")` raises `typer.BadParameter` (single-digit month/day)
- `parse_date("2026-04-01T00:00:00")` raises `typer.BadParameter` (datetime format)
- `parse_date("+002026-04-01")` raises `typer.BadParameter` (extended year)
- `str(parse_date(...))` calls in search.py have clarifying comments
- All existing tests still pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-53+54-date-parsing
python -m pytest tests/ -v
python -m ruff check src/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-53` and `Closes FLI-54` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
