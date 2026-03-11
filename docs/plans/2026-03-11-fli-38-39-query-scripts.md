# Implementation Plan: Best Flight Combinations & Roundtrip vs One-Way Comparison

## Issues
- FLI-38: Best flight combinations query
- FLI-39: Roundtrip vs 2x one-way comparison

## Research Context

### Codebase Patterns
- **ORM models** in `src/flight_watcher/models.py`: `SearchConfig`, `ScanRun`, `PriceSnapshot`
- **DB access** via `from flight_watcher.db import get_session` context manager (auto-commit/rollback)
- **Existing script** `scripts/find_cheapest.py` queries live LATAM API — new scripts query the DB instead
- **Script convention**: argparse CLI, `scripts/` directory, stdout output, `_make_*()` test helpers
- **Test convention**: `tests/test_<module>.py`, class-grouped, `MagicMock` for DB sessions, `_make_*()` factories

### Key Model Fields (PriceSnapshot)
- `origin`, `destination` (IATA, String(3))
- `flight_date` (Date)
- `price` (Numeric(10,2)), `currency` (String(3))
- `brand` (String(30)) — LIGHT, STANDARD, FULL, PREMIUM ECONOMY
- `search_type` — SearchType enum: `oneway` or `roundtrip`
- `scan_run_id` → `ScanRun.search_config_id` → `SearchConfig`
- `fetched_at` (DateTime with timezone)

### Key Model Fields (SearchConfig)
- `origin`, `destination`, `must_arrive_by`, `must_stay_until`, `max_trip_days`

### Indexes Available
- `ix_price_snapshots_route_date` on (origin, destination, flight_date)
- `ix_price_snapshots_run_id` on scan_run_id
- `ix_scan_runs_config_id` on search_config_id

## Decisions Made

1. **Query module location**: New module `src/flight_watcher/queries.py` containing pure query functions. Scripts in `scripts/` call these functions. This keeps logic testable without mocking argparse.

2. **"Latest prices" definition**: For each (origin, destination, flight_date, brand, search_type) combination, take the snapshot with the highest `fetched_at`. This uses a SQLAlchemy subquery with `func.max(PriceSnapshot.fetched_at)`.

3. **Brand filter**: Default to LIGHT (cheapest tier) for combination ranking. Accept optional `--brand` CLI arg.

4. **Output format**: Plain text to stdout, matching the display style in `find_cheapest.py` (Unicode box chars, formatted prices).

5. **Script entry points**: `scripts/best_combinations.py` (FLI-38) and `scripts/roundtrip_vs_oneway.py` (FLI-39). Both accept `search_config_id` as primary arg.

## Implementation Tasks

### Task 1: Create query functions module — `src/flight_watcher/queries.py`

Contains three functions:

#### `get_latest_snapshots(session, search_config_id, search_type=None, brand="LIGHT")`
- Join PriceSnapshot → ScanRun → SearchConfig filtering by config ID
- Subquery to get max `fetched_at` per (origin, destination, flight_date, flight_code, brand, search_type)
- Filter to only completed scan runs (`ScanStatus.COMPLETED`)
- Return list of PriceSnapshot objects with latest prices

#### `best_combinations(session, search_config_id, brand="LIGHT", limit=20)`
FLI-38 core logic:
- Get SearchConfig to read `max_trip_days`, `must_arrive_by`, `must_stay_until`
- Get latest ONEWAY outbound snapshots: origin→destination, flight_date <= must_arrive_by
- Get latest ONEWAY return snapshots: destination→origin, flight_date >= must_stay_until
- Cross-join: for each (outbound, return) pair:
  - Calculate trip_days = (return.flight_date - outbound.flight_date).days
  - Filter: trip_days <= max_trip_days and trip_days > 0
  - Calculate total_price = outbound.price + return.price
- Group by trip_days, keep cheapest per group
- Sort by total_price ascending
- Return list of dicts: `{outbound_date, return_date, trip_days, outbound_price, return_price, total_price, currency}`

#### `roundtrip_vs_oneway(session, search_config_id, brand="LIGHT")`
FLI-39 core logic:
- Get latest ROUNDTRIP snapshots for both legs (outbound + return on same date pairs)
- Get latest ONEWAY snapshots for both directions
- For each date pair that has BOTH roundtrip and oneway data:
  - roundtrip_total = cheapest roundtrip outbound + cheapest roundtrip return (for that date pair)
  - oneway_total = cheapest oneway outbound + cheapest oneway return (for that date pair)
  - savings_pct = abs(roundtrip_total - oneway_total) / max(roundtrip_total, oneway_total) * 100
  - recommendation = "roundtrip" if roundtrip_total <= oneway_total else "2x one-way"
  - flag = savings_pct > 5
- Return list of dicts: `{outbound_date, return_date, roundtrip_total, oneway_total, savings_pct, recommendation, significant}`

### Task 2: Create script `scripts/best_combinations.py`

- argparse: positional `search_config_id` (int), optional `--brand` (default LIGHT), `--limit` (default 20)
- Call `best_combinations()` from queries module
- Display output matching issue format:
  ```
  Stay 7 days (Jun 21 → Jun 28): R$ 3,000
  Stay 10 days (Jun 18 → Jun 28): R$ 3,200
  ```
- Handle no-results gracefully

### Task 3: Create script `scripts/roundtrip_vs_oneway.py`

- argparse: positional `search_config_id` (int), optional `--brand` (default LIGHT), `--threshold` (default 5.0 for significant %)
- Call `roundtrip_vs_oneway()` from queries module
- Display comparison table with recommendation
- Flag significant savings (> threshold %)

### Task 4: Tests — `tests/test_queries.py`

Test the query functions with mocked sessions:

#### `test_best_combinations`
- Mock session.execute to return fake PriceSnapshot rows
- Test cross-join logic: correct pairing, trip_days filtering, price ranking
- Test max_trip_days constraint filters out long trips
- Test grouping by trip_days keeps only cheapest

#### `test_roundtrip_vs_oneway`
- Mock session returning both roundtrip and oneway snapshots
- Test comparison calculation: correct savings_pct
- Test recommendation logic: roundtrip cheaper → "roundtrip", oneway cheaper → "2x one-way"
- Test significant flag threshold

#### `test_get_latest_snapshots`
- Test that only latest fetched_at per unique flight is returned
- Test filtering by search_type and brand

## Acceptance Criteria

From FLI-38:
- Given a search_config_id, find cheapest (outbound, return) pairs using latest prices
- Cross-join latest outbound snapshots with latest return snapshots
- Filter by max_trip_days constraint
- Rank by total price (outbound + return)
- Group by trip_duration to show best price per stay length
- Output: `Stay N days (Mon DD → Mon DD): R$ X,XXX`

From FLI-39:
- For each date pair with both roundtrip and one-way data: compare totals
- Calculate savings percentage
- Flag pairs where one method is significantly cheaper (>5%)
- Output recommendation: "Book as roundtrip" or "Book as 2 one-ways"

## Verification

```bash
# Unit tests
python -m pytest tests/test_queries.py -v

# All tests still pass
python -m pytest tests/ -v

# Type check (if mypy configured)
# python -m mypy src/flight_watcher/queries.py

# Scripts parse args correctly (--help)
python scripts/best_combinations.py --help
python scripts/roundtrip_vs_oneway.py --help
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-38` and `Closes FLI-39` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Database migrations (no schema changes needed)
- Modifying existing scripts like find_cheapest.py
