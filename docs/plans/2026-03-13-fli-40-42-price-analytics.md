# Implementation Plan: Price History Query & Price Trend Summary

## Issues
- FLI-40: Price history query — "When was FOR→MIA on June 21 last seen below R$ 1,500?"
- FLI-42: Price trend summary — Show price direction vs 7-day rolling average (↑/↓/→)

## Research Context

### Existing Patterns
- **queries.py** (FLI-38+39 branch): Contains `get_latest_snapshots`, `best_combinations`, `roundtrip_vs_oneway`. Uses SQLAlchemy 2.0 `select()` API, joins PriceSnapshot → ScanRun, returns `list[PriceSnapshot]` or `list[dict]`. Session passed as parameter (not created internally).
- **Models**: `PriceSnapshot` has `origin`, `destination`, `flight_date`, `price` (Decimal/Numeric(10,2)), `fetched_at` (DateTime tz-aware), `brand`, `search_type`, `scan_run_id`. Composite index on `(origin, destination, flight_date)`.
- **Test patterns**: `_make_snapshot()` / `_make_config()` factory helpers. MagicMock sessions. `session.execute.return_value.scalars.return_value = [...]` for query results. Class-grouped tests.
- **No conftest.py** — helpers defined per test file.

### Key Constraints
- Prices are `Decimal` — all arithmetic must use Decimal, not float (except final display percentages).
- FLI-38+39 is a parallel branch. This worktree creates its own `queries.py`. When both merge to main, they'll be reconciled. The functions here are independent (no dependency on `get_latest_snapshots`).
- Only filter completed scan runs (`ScanRun.status == ScanStatus.COMPLETED`).

## Decisions Made

1. **New functions go in `src/flight_watcher/queries.py`** — same module as FLI-38+39 functions. Merge conflict will be trivial (additive).
2. **`price_history` returns a dataclass `PriceHistoryResult`** with both the raw snapshots list and computed aggregates (min, max, avg, min_seen_at). This is cleaner than returning a dict for structured data with mixed types.
3. **`price_trend_summary` returns `list[dict]`** — consistent with the existing pattern in `best_combinations` and `roundtrip_vs_oneway`. Each dict has: `flight_date`, `current_price`, `rolling_avg_7d`, `direction` (↑/↓/→), `pct_diff`.
4. **Rolling average is computed in Python** — not SQL window functions. Keeps it portable and testable. The dataset per route is small (one price point per scan per date), so performance is not a concern.
5. **`price_trend_summary` operates per search_config_id** — consistent with existing query functions. Gets the latest price per flight_date from completed runs, then computes rolling averages over the fetched_at timeline.
6. **Direction thresholds**: ↑ when current > avg * 1.05, ↓ when current < avg * 0.95, → otherwise (matching issue spec exactly).

## Implementation Tasks

### Task 1: Create `src/flight_watcher/queries.py` with `price_history`

**Function signature:**
```python
@dataclass
class PriceHistoryResult:
    snapshots: list[PriceSnapshot]  # ordered by fetched_at ascending
    min_price: Decimal
    max_price: Decimal
    avg_price: Decimal
    min_price_seen_at: datetime  # fetched_at of the cheapest snapshot

def price_history(
    session: Session,
    origin: str,
    destination: str,
    flight_date: date,
    brand: str = "LIGHT",
    search_type: SearchType | None = None,
) -> PriceHistoryResult | None:
```

**Query logic:**
- SELECT from price_snapshots JOIN scan_runs (status=completed)
- WHERE origin, destination, flight_date, brand match
- Optional search_type filter
- ORDER BY fetched_at ASC
- Compute min/max/avg from results in Python (simple, avoids second query)
- Return None if no snapshots found

**File:** `src/flight_watcher/queries.py`

### Task 2: Create `src/flight_watcher/queries.py` with `price_trend_summary`

**Function signature:**
```python
def price_trend_summary(
    session: Session,
    search_config_id: int,
    brand: str = "LIGHT",
    search_type: SearchType = SearchType.ONEWAY,
) -> list[dict]:
```

**Returns list of dicts, each with:**
```python
{
    "flight_date": date,
    "current_price": Decimal,      # latest observed price for this date
    "rolling_avg_7d": Decimal,     # avg of last 7 price observations
    "direction": str,              # "↑", "↓", or "→"
    "pct_diff": float,             # percentage difference from rolling avg
}
```

**Logic:**
1. Query all snapshots for the search_config_id (join ScanRun for config_id + completed status), filter by brand and search_type
2. Group by flight_date: for each date, collect all (fetched_at, price) pairs ordered by fetched_at
3. For each flight_date:
   - current_price = price from most recent fetched_at
   - Collect all prices observed for this flight_date over time
   - rolling_avg_7d = average of the last 7 observations (or all if < 7)
   - Compute pct_diff = (current - rolling_avg) / rolling_avg * 100
   - direction = "↑" if pct_diff > 5, "↓" if pct_diff < -5, "→" otherwise
4. Return sorted by flight_date

### Task 3: Tests for `price_history` — `tests/test_queries.py`

Reuse `_make_snapshot` factory pattern from FLI-38+39. Tests:

- `test_price_history_returns_snapshots_ordered_by_fetched_at` — 3 snapshots with different fetched_at, verify order
- `test_price_history_computes_min_max_avg` — verify aggregates
- `test_price_history_returns_none_when_no_data` — empty result
- `test_price_history_filters_by_brand` — passes brand to query, executes without error
- `test_price_history_filters_by_search_type` — optional search_type filter
- `test_price_history_min_price_seen_at` — verify min_price_seen_at is fetched_at of cheapest snapshot

### Task 4: Tests for `price_trend_summary` — `tests/test_queries.py`

Tests:
- `test_trend_summary_rising_price` — current > avg * 1.05 → direction "↑"
- `test_trend_summary_dropping_price` — current < avg * 0.95 → direction "↓"
- `test_trend_summary_stable_price` — within ±5% → direction "→"
- `test_trend_summary_empty_when_no_data` — returns []
- `test_trend_summary_rolling_avg_uses_last_7` — verify window size
- `test_trend_summary_sorted_by_flight_date` — verify ordering
- `test_trend_summary_pct_diff_calculation` — verify math

## Acceptance Criteria

**FLI-40:**
- Can query price history for a specific route + date
- Returns chronologically ordered snapshots
- Computes min, max, avg price and when the lowest was seen
- Only includes data from completed scan runs

**FLI-42:**
- Shows price direction for each flight_date: ↑ (>5% above avg), ↓ (>5% below avg), → (within ±5%)
- Uses 7-observation rolling average (falls back to all available if < 7)
- Returns percentage difference from rolling average
- Sorted by flight_date

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-40+42-price-analytics
pip install -e ".[test]" 2>/dev/null
pytest tests/test_queries.py -v
ruff check src/flight_watcher/queries.py tests/test_queries.py
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-40` and `Closes FLI-42` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- CLI scripts to invoke these queries (separate issue)
- Display/formatting of results (separate concern)
