# Implementation Plan: Date Expansion Algorithm (FLI-21)

## Issues
- FLI-21: Date expansion algorithm

## Research Context

### Codebase Patterns
- **Package layout:** `src/flight_watcher/` with one module per concern (`scanner.py`, `models.py`, `display.py`, `latam_scraper.py`)
- **Date convention:** Dates stored as `YYYY-MM-DD` strings throughout (`FlightResult.date`, scanner params). Stdlib `datetime` used for all date ops.
- **Data models:** Plain `@dataclass` classes in `models.py`
- **Function style:** Type-hinted, snake_case, docstrings, private helpers prefixed `_`
- **Tests:** `pytest` in `tests/test_*.py`, helper factories like `_make_flight()`, `unittest.mock` for external deps

### Architecture Context
- FLI-21 is a child of FLI-8 (Epic: Flexible Date Engine). Sibling issues: FLI-24 (unit tests — separate issue), FLI-22 (pair validation), FLI-23 (CLI for search configs)
- FLI-24 explicitly covers unit tests for date expansion, so this task focuses on the function itself. Include basic smoke tests only to verify correctness during development.
- No existing date utilities — this is net-new code
- No external dependencies needed — stdlib `datetime` + `timedelta` only

### Design Decision
- **Module location:** New file `src/flight_watcher/date_expansion.py` — keeps it isolated, testable, and consistent with one-module-per-concern pattern
- **Input types:** `datetime.date` for date params (type-safe, stdlib), `int` for `max_trip_days`
- **Output type:** `tuple[list[str], list[str]]` — YYYY-MM-DD strings matching existing API contracts in scanner/scraper
- **Validation:** Raise `ValueError` for invalid inputs (must_stay_until before must_arrive_by when gap > max_trip_days, negative max_trip_days). Keep it simple — this is a pure function, not a user-facing API.

## Implementation Tasks

1. **Create `src/flight_watcher/date_expansion.py`** — new module with `expand_dates()` function:
   ```python
   def expand_dates(
       must_arrive_by: date,
       must_stay_until: date,
       max_trip_days: int,
   ) -> tuple[list[str], list[str]]:
   ```
   Formula from issue:
   - `earliest_departure = must_stay_until - timedelta(days=max_trip_days)`
   - `latest_return = must_arrive_by + timedelta(days=max_trip_days)`
   - `outbound_dates = [earliest_departure .. must_arrive_by]` (inclusive)
   - `return_dates = [must_stay_until .. latest_return]` (inclusive)

   Input validation:
   - `max_trip_days` must be positive
   - `must_stay_until` must be on or after `must_arrive_by`
   - The minimum trip length (`must_stay_until - must_arrive_by`) must not exceed `max_trip_days`

2. **Create `tests/test_date_expansion.py`** — basic smoke tests:
   - Test the example from the issue: arrive June 21, stay until June 28, max 15 days → outbound June 13-21, return June 28-July 6
   - Test edge case: `must_arrive_by == must_stay_until` (same-day turnaround)
   - Test edge case: `max_trip_days` equals exact stay duration (no expansion beyond stay)
   - Test validation: negative `max_trip_days` raises `ValueError`
   - Test validation: `max_trip_days` < stay duration raises `ValueError`

## Acceptance Criteria
- Pure function with no side effects or external dependencies
- Given (must_arrive_by=June 21, must_stay_until=June 28, max_trip_days=15) → outbound [June 13..June 21], return [June 28..July 6]
- Returns YYYY-MM-DD string lists matching codebase convention
- Type-hinted, docstring present
- All tests pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-21-date-expansion
python -m pytest tests/test_date_expansion.py -v
python -m pytest tests/ -v  # full suite still passes
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-21`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified (FLI-24 covers comprehensive tests)
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- CLI integration (FLI-23)
- Pair validation logic (FLI-22)
