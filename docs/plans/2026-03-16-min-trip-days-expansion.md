# Implementation Plan: min_trip_days Expansion (FLI-112, FLI-122, FLI-123)

## Issues
- FLI-112: Update date expansion to support min_trip_days
- FLI-122: Add CHECK constraint min_trip_days <= max_trip_days to search_configs
- FLI-123: Add CHECK constraint min_trip_days >= 1 to search_configs

## Research Context

### Current State
- `min_trip_days` column already exists in `SearchConfig` model (`models.py:99`) as `Mapped[int | None]` (nullable, no default). Migration `c7d8e9f0` added it.
- `generate_pairs()` (`date_expansion.py:72-109`) accepts `(outbound_dates, return_dates, max_trip_days)`. Filter: `ret >= out and (ret - out).days <= max_trip_days`.
- `expand_dates()` (`date_expansion.py:6-69`) accepts `(must_arrive_by, must_stay_until, max_trip_days)`. Validates max_trip_days > 0, stay_until >= arrive_by, min_stay <= max_trip_days. Calls `generate_pairs()` internally on line 65.
- Orchestrator extracts config as plain dict to avoid DetachedInstanceError. Two extraction points: `run_all_scans()` (lines 33-44) and `run_retry_scan()` (lines 84-91). Both pass config dict to `run_scan()` which calls `expand_dates()` at line 135.
- CLI `config_add()` (`cli/config.py:14-55`) calls `expand_dates()` for validation (line 29) and `generate_pairs()` for pair count (line 34). No `--min-days` option exists yet.
- No CHECK constraints exist in the codebase. Will use `op.create_check_constraint()` in migration and `CheckConstraint` in `__table_args__`.

### Test Patterns
- `test_date_expansion.py`: pytest functions, direct invocation with `date()` objects, `pytest.raises` for validation.
- `test_pair_validation.py`: pytest functions testing `generate_pairs()` output counts and ordering.
- `test_orchestrator.py`: `unittest.TestCase` with `@patch` decorators, `_make_config()` factory, `MagicMock` for sessions.
- `test_cli.py`: `CliRunner` from typer.testing, `make_session_mock()` helper.
- `test_models.py`: pytest class testing column names, indexes. No constraint tests yet.

## Decisions Made

1. **Single migration for both constraints (FLI-122 + FLI-123):** Both constraints are small, related, and should be deployed atomically. One migration file with two `create_check_constraint` calls.

2. **Constraint must handle NULL:** `min_trip_days` is nullable. Constraints use `min_trip_days IS NULL OR ...` pattern so NULL values (meaning "no minimum") pass validation.

3. **Constraint naming:** `ck_search_configs_min_trip_days_positive` and `ck_search_configs_min_le_max_trip_days` — follows `ck_<table>_<description>` convention.

4. **ORM `__table_args__`:** Add `CheckConstraint` definitions to `SearchConfig` model alongside existing index definitions to keep ORM and DB in sync.

5. **`expand_dates()` signature:** Add `min_trip_days: int | None = None` as 4th param. When `None`, no minimum filtering. Validation: if provided, must be >= 1 and <= max_trip_days.

6. **`generate_pairs()` signature:** Add `min_trip_days: int | None = None` as 4th param. Filter adds `(ret - out).days >= min_trip_days` when set. `expand_dates()` passes it through.

7. **CLI `--min-days` option:** Optional `typer.Option` defaulting to `None`. Passed to `expand_dates()` and stored on `SearchConfig`.

## Implementation Tasks

### Task 1: Add CHECK constraints migration (FLI-122 + FLI-123)
- Create `alembic/versions/<rev>_add_check_constraints_to_search_configs.py`
- `upgrade()`: two `op.create_check_constraint()` calls
  - `ck_search_configs_min_trip_days_positive`: `"min_trip_days IS NULL OR min_trip_days >= 1"`
  - `ck_search_configs_min_le_max_trip_days`: `"min_trip_days IS NULL OR min_trip_days <= max_trip_days"`
- `downgrade()`: two `op.drop_constraint()` calls
- `down_revision` = `"c7d8e9f0"` (the min_trip_days column migration)

### Task 2: Add CheckConstraint to ORM model
- Edit `src/flight_watcher/models.py` — add `__table_args__` to `SearchConfig` with both `CheckConstraint` definitions
- Keep existing `Index("ix_search_configs_origin_dest", ...)` in `__table_args__` tuple

### Task 3: Update `generate_pairs()` (FLI-112)
- Edit `src/flight_watcher/date_expansion.py`
- Add `min_trip_days: int | None = None` parameter
- Update filter: when `min_trip_days` is not None, add `(ret_date - out_date).days >= min_trip_days` check
- Add tests in `tests/test_pair_validation.py`:
  - `test_min_trip_days_filters_short_trips` — verify pairs with duration < min_trip_days are excluded
  - `test_min_trip_days_none_no_filtering` — verify None behaves like before (backward compat)
  - `test_min_trip_days_equals_max_trip_days` — only exact-duration pairs remain

### Task 4: Update `expand_dates()` (FLI-112)
- Edit `src/flight_watcher/date_expansion.py`
- Add `min_trip_days: int | None = None` parameter
- Add validation: if min_trip_days is not None, check `min_trip_days >= 1` and `min_trip_days <= max_trip_days`
- Pass `min_trip_days` through to `generate_pairs()` call (line 65)
- Add tests in `tests/test_date_expansion.py`:
  - `test_min_trip_days_validation_zero` — raises ValueError
  - `test_min_trip_days_validation_negative` — raises ValueError
  - `test_min_trip_days_exceeds_max` — raises ValueError
  - `test_min_trip_days_valid_passes_through` — no error, returns dates

### Task 5: Update orchestrator to pass min_trip_days (FLI-112)
- Edit `src/flight_watcher/orchestrator.py`
- In `run_all_scans()` config dict extraction (lines 33-44): add `"min_trip_days": orm_obj.min_trip_days`
- In `run_retry_scan()` config dict extraction (lines 84-91): add `"min_trip_days": orm_obj.min_trip_days`
- In `run_scan()` `expand_dates()` call (line 135): pass `config["min_trip_days"]`
- Update `_make_config()` in `tests/test_orchestrator.py` to include `min_trip_days=None` default
- Update existing orchestrator tests that create ORM mocks to include `min_trip_days` attribute

### Task 6: Update CLI to accept --min-days (FLI-112)
- Edit `src/flight_watcher/cli/config.py`
- Add `min_days: Annotated[int | None, typer.Option("--min-days", ...)] = None` parameter to `config_add()`
- Pass to `expand_dates()` call (line 29)
- Pass to `generate_pairs()` call (line 34)
- Set on `SearchConfig` object: `min_trip_days=min_days`
- Add tests in `tests/test_cli.py`:
  - `test_config_add_with_min_days` — verify min_trip_days stored
  - `test_config_add_without_min_days` — verify backward compat (None)

### Task 7: Update test_models.py
- Add test verifying CHECK constraints exist in `SearchConfig.__table__.constraints`

## Acceptance Criteria
- `generate_pairs()` filters out pairs shorter than `min_trip_days` when provided
- `expand_dates()` validates min_trip_days (>= 1, <= max_trip_days) when provided
- `expand_dates()` and `generate_pairs()` behave identically to before when `min_trip_days=None`
- Orchestrator passes `min_trip_days` from SearchConfig to date expansion
- CLI accepts optional `--min-days` flag
- DB CHECK constraints prevent min_trip_days < 1 or min_trip_days > max_trip_days
- All existing tests continue to pass (backward compatibility)
- New tests cover min_trip_days filtering, validation, and constraint behavior

## Verification
```bash
# Run all tests
pytest tests/ -v

# Run specific test files
pytest tests/test_date_expansion.py tests/test_pair_validation.py tests/test_orchestrator.py tests/test_cli.py tests/test_models.py -v

# Lint
ruff check src/ tests/

# Type check (if configured)
# mypy src/

# Verify migration generates cleanly
alembic check
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-112`, `Closes FLI-122`, `Closes FLI-123` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Adding CHECK constraint for max_trip_days > 0 (not in scope of these issues)
- Adding CHECK constraint for must_stay_until >= must_arrive_by (not in scope)
