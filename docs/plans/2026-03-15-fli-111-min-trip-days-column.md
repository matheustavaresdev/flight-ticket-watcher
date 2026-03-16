# Implementation Plan: Add min_trip_days column to SearchConfig

## Issues
- FLI-111: Add min_trip_days column to SearchConfig

## Research Context

### Current State
- `SearchConfig` model at `src/flight_watcher/models.py:85-113` has `max_trip_days: Mapped[int]` (non-nullable).
- Alembic head: `b5c6d7e8` (added retry columns).
- Migration pattern: `op.add_column()` / `op.drop_column()` with explicit `server_default` for non-nullable, no default needed for nullable.
- Model uses `Mapped[type]` with `mapped_column()` throughout.
- Test at `tests/test_models.py:14-28` asserts exact column set — must be updated.

### Pattern Reference
The `b5c6d7e8` migration (retry columns) is the closest precedent — it adds columns to `search_configs` with server defaults. For a nullable column, the pattern is simpler: no `server_default` needed.

## Decisions Made
- **Nullable with no default:** Issue says "nullable, default NULL (meaning no minimum beyond the mandatory stay)." This means `Mapped[int | None]` with `nullable=True`, no `server_default`.
- **Column placement in model:** After `max_trip_days` (line 93) for logical grouping.
- **Migration ID:** Use `c7d8e9f0` as the revision slug (follows hex pattern of existing migrations).

## Implementation Tasks

1. **Add `min_trip_days` column to SQLAlchemy model** — `src/flight_watcher/models.py`
   - After line 93 (`max_trip_days`), add:
     ```python
     min_trip_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
     ```

2. **Create Alembic migration** — `alembic/versions/c7d8e9f0_add_min_trip_days_to_search_configs.py`
   - `down_revision = "b5c6d7e8"`
   - `upgrade()`: `op.add_column("search_configs", sa.Column("min_trip_days", sa.Integer(), nullable=True))`
   - `downgrade()`: `op.drop_column("search_configs", "min_trip_days")`

3. **Update model test** — `tests/test_models.py`
   - Add `"min_trip_days"` to the expected column set in `test_columns_exist()`.

## Acceptance Criteria
- Alembic migration adds `min_trip_days INTEGER NULL` to `search_configs` table.
- `SearchConfig` model exposes `min_trip_days` as `Mapped[int | None]`.
- Existing rows get `NULL` for `min_trip_days` (no backfill needed).
- All tests pass including the updated column assertion.

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-111-min-trip-days
python -m pytest tests/test_models.py -v
alembic check  # verify no drift between model and migrations
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-111` line
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Updating queries.py, cli/config.py, or orchestrator logic (separate issues in the epic)
