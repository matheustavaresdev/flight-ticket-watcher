# Implementation Plan: Pair Validation for Roundtrip Searches

## Issues
- FLI-22: Pair validation for roundtrip searches

## Research Context

### Existing Codebase
- `src/flight_watcher/date_expansion.py` contains `expand_dates()` (FLI-21) which produces two independent date lists: `outbound_dates` and `return_dates` as YYYY-MM-DD strings.
- `_date_range(start, end)` helper generates inclusive date ranges.
- `scanner.py` has `search_roundtrip()` accepting a single `(departure_date, return_date)` pair.
- All dates are YYYY-MM-DD strings at API boundaries, `datetime.date` internally.

### Test Patterns
- Tests in `tests/test_<module>.py`, pytest, no external deps for pure logic.
- Validation errors use `ValueError` with descriptive messages.
- Pattern: canonical example test, edge cases, validation error tests.

### Pair Math Verification
Canonical example: outbound June 13-21 (9 dates), return June 28-July 6 (9 dates), max_trip_days=15.
- June 13 pairs with 1 return date (June 28 only, delta=15)
- June 14 → 2, June 15 → 3, ..., June 21 → 9 (all, max delta=15)
- Total: 1+2+...+9 = 45 valid pairs. Confirmed.

## Decisions Made

- **Location:** Add `generate_pairs()` to `date_expansion.py` rather than a new module. It's a natural companion to `expand_dates()` — same domain, same file, avoids module proliferation for a single function.
- **Return type:** `list[tuple[str, str]]` — list of (outbound_date, return_date) tuples as YYYY-MM-DD strings. Consistent with existing string-based date convention.
- **Input:** Accept `list[str]` for both date lists plus `int` for max_trip_days. This decouples from `expand_dates()` — callers can pass any date lists, not just ones from `expand_dates()`.
- **Validation:** Raise `ValueError` for empty lists or non-positive max_trip_days. Do NOT re-validate date format (caller's responsibility, matching existing pattern).
- **Ordering:** Pairs sorted by (outbound_date, return_date) — natural lexicographic order of YYYY-MM-DD strings.

## Implementation Tasks

1. **Add `generate_pairs()` to `date_expansion.py`** — affects `src/flight_watcher/date_expansion.py`
   ```python
   def generate_pairs(
       outbound_dates: list[str],
       return_dates: list[str],
       max_trip_days: int,
   ) -> list[tuple[str, str]]:
   ```
   - Parse each date string to `datetime.date` for delta calculation.
   - For each (out, ret) combination: include if `(ret - out).days <= max_trip_days` and `ret >= out`.
   - Return sorted list of (outbound, return) string tuples.
   - Raise `ValueError` if max_trip_days <= 0, or if either list is empty.

2. **Add tests in `tests/test_pair_validation.py`** — new file
   - `test_canonical_45_pairs`: expand_dates(June 21, June 28, 15) → generate_pairs → assert len == 45, check first/last pair.
   - `test_tight_constraint_single_pair`: max_trip_days equals exact stay → only 1 pair.
   - `test_same_day_turnaround`: outbound and return on same day → valid pair (0-day trip).
   - `test_return_before_outbound_excluded`: pairs where return < outbound are excluded.
   - `test_validation_empty_outbound`: empty outbound list → ValueError.
   - `test_validation_empty_return`: empty return list → ValueError.
   - `test_validation_non_positive_max_trip_days`: 0 or negative → ValueError.
   - `test_pairs_sorted`: verify output ordering.

## Acceptance Criteria
- `generate_pairs()` produces exactly 45 valid pairs for the June 21-28 / 15-day scenario.
- All pairs satisfy `return_date - outbound_date <= max_trip_days`.
- No pairs where return_date < outbound_date.
- ValueError raised for invalid inputs.
- All tests pass.

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-22-pair-validation
pytest tests/test_pair_validation.py -v
pytest tests/ -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-22` line
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Modifying `scanner.py` to use pairs (that's a separate integration task)
