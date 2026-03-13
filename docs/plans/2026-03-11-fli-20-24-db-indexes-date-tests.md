# Implementation Plan: DB Indexes + Date Expansion Tests

## Issues
- FLI-20: Database indexes for query performance
- FLI-24: Unit tests for date expansion

## Research Context

### Current Index State
**PriceSnapshot** has 2 indexes: `ix_price_snapshots_run_id` (scan_run_id) and `ix_price_snapshots_route_date` (origin, destination, flight_date).
**ScanRun** has 2 indexes: `ix_scan_runs_config_id` (search_config_id) and `ix_scan_runs_status` (status).

FLI-20 requires adding:
1. `(origin, destination, flight_date, brand)` on price_snapshots — extends existing route_date index with brand for cheapest-by-brand queries
2. `(flight_date, fetched_at)` on price_snapshots — for price history/trend queries
3. `(scan_run_id)` on price_snapshots — **already exists** as `ix_price_snapshots_run_id`, skip
4. `(search_config_id, status)` on scan_runs — composite replaces the two separate single-column indexes for finding latest runs by config+status

### Date Expansion Test Coverage
`test_date_expansion.py` has smoke tests (canonical, same-day, exact-stay, validation errors).
`test_pair_validation.py` has basic pair tests (canonical 45, tight constraint, same-day, return-before-outbound, validation, sorted).

FLI-24 requires additional edge cases:
- Month boundary spanning (e.g., May 28 → June 5)
- Large windows (30+ day max trip)
- Pair count verification for various configurations
- `max_days == min_stay` with `generate_pairs` (should produce exactly 1 pair)

### Conventions
- Indexes declared in `__table_args__` tuple using `Index()` objects
- Migrations via `alembic revision --autogenerate`
- Tests: flat pytest functions, no fixtures/conftest, `pytest.raises` for errors
- Test files: `tests/test_<module>.py`

## Decisions Made

1. **Composite index replaces two single-column indexes on scan_runs**: The existing `ix_scan_runs_config_id` and `ix_scan_runs_status` will be replaced by a single composite `ix_scan_runs_config_status` (search_config_id, status). The composite index can serve queries that filter on config_id alone (leftmost prefix), making the separate config_id index redundant. The separate status-only index is low-selectivity and rarely useful on its own — queries always filter by config first.

2. **Keep existing route_date index, add new route_date_brand**: The existing 3-column `ix_price_snapshots_route_date` (origin, destination, flight_date) serves general route lookups. The new 4-column `ix_price_snapshots_route_date_brand` (origin, destination, flight_date, brand) serves cheapest-by-brand queries as a covering index extension. Both are useful.

3. **New tests go in existing test files**: FLI-24 tests extend `test_date_expansion.py` and `test_pair_validation.py` rather than creating new files.

4. **Single migration for all index changes**: One Alembic migration handles adding new indexes and dropping replaced ones.

## Implementation Tasks

### FLI-20: Database Indexes

1. **Update `ScanRun.__table_args__`** in `src/flight_watcher/models.py`:
   - Remove `Index("ix_scan_runs_config_id", "search_config_id")` and `Index("ix_scan_runs_status", "status")`
   - Add `Index("ix_scan_runs_config_status", "search_config_id", "status")`

2. **Update `PriceSnapshot.__table_args__`** in `src/flight_watcher/models.py`:
   - Add `Index("ix_price_snapshots_route_date_brand", "origin", "destination", "flight_date", "brand")`
   - Add `Index("ix_price_snapshots_date_fetched", "flight_date", "fetched_at")`

3. **Generate Alembic migration**:
   ```bash
   cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-20+24-db-indexes-tests
   alembic revision --autogenerate -m "Add composite indexes for query performance (FLI-20)"
   ```
   Verify the generated migration:
   - Creates `ix_scan_runs_config_status`, `ix_price_snapshots_route_date_brand`, `ix_price_snapshots_date_fetched`
   - Drops `ix_scan_runs_config_id` and `ix_scan_runs_status`
   - Downgrade reverses all changes

4. **Update `tests/test_models.py`**:
   - `TestScanRun.test_indexes`: assert `ix_scan_runs_config_status` present, old indexes absent
   - `TestPriceSnapshot.test_indexes`: assert all 4 indexes present (run_id, route_date, route_date_brand, date_fetched)

### FLI-24: Date Expansion Tests

5. **Add edge case tests to `tests/test_date_expansion.py`**:
   - `test_month_boundary_spanning`: must_arrive_by=May 28, must_stay_until=June 2, max_trip_days=10 → verify outbound starts in May, return ends in June
   - `test_large_window_30_plus_days`: must_arrive_by=June 1, must_stay_until=June 5, max_trip_days=35 → verify correct list lengths and boundary dates
   - `test_single_day_max_trip_equals_one`: must_arrive_by=must_stay_until=June 15, max_trip_days=1 → outbound=[June 14, June 15], return=[June 15, June 16]
   - `test_year_boundary`: must_arrive_by=Dec 30, must_stay_until=Jan 2, max_trip_days=10 → dates span 2026→2027

6. **Add edge case tests to `tests/test_pair_validation.py`**:
   - `test_month_boundary_pairs`: pairs from month-spanning expand_dates, verify all pairs valid
   - `test_large_window_pair_count`: 30+ day window, verify pair count matches expected formula
   - `test_max_trip_equals_min_stay_single_pair`: exact-stay expand_dates → generate_pairs produces exactly 1 pair
   - `test_multiple_outbound_single_return`: 3 outbound dates, 1 return date, verify filtering
   - `test_single_outbound_multiple_return`: 1 outbound, 3 return dates, verify filtering

## Acceptance Criteria

- Composite indexes defined in ORM models match FLI-20 spec
- Alembic migration correctly creates/drops indexes
- Model tests verify new index names
- Date expansion tests cover: month boundaries, large windows, year boundaries, tight constraints
- Pair validation tests cover: month-boundary pairs, large windows, exact-stay single pair, asymmetric date lists
- All existing tests continue to pass

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-20+24-db-indexes-tests
python -m pytest tests/ -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-20` and `Closes FLI-24` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
