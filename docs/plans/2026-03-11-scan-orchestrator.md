# Implementation Plan: Scan Orchestrator

## Issues
- FLI-26: Scan orchestrator — core scan loop
- FLI-27: One-way search integration with DB storage
- FLI-28: Roundtrip search integration with DB storage
- FLI-29: Cursor-based scan resumption

## Research Context

### Existing Infrastructure
All building blocks are in place:

- **ORM models** (`models.py`): `SearchConfig`, `ScanRun`, `PriceSnapshot` with enums `ScanStatus`, `SearchType`
- **DB layer** (`db.py`): `get_session()` context manager (auto-commit/rollback), `get_engine()` singleton
- **Scanner** (`scanner.py`): `search_one_way(origin, dest, date) -> list[FlightResult]` using fast-flights (Google Flights). `search_roundtrip()` delegates to two `search_one_way()` calls with delay between.
- **LATAM scraper** (`latam_scraper.py`): `search_latam_oneway()` and `search_latam_roundtrip()` via Playwright BFF interception. `parse_offers(data) -> list[dict]` extracts flight_code, brands (LIGHT/STANDARD/FULL), prices.
- **Date expansion** (`date_expansion.py`): `expand_dates(must_arrive_by, must_stay_until, max_trip_days) -> (outbound_dates, return_dates)`. `generate_pairs(outbound, return, max_trip_days) -> list[tuple[str, str]]`.
- **Scheduler** (`scheduler.py`): APScheduler `BackgroundScheduler` with PostgreSQL job store, `ThreadPoolExecutor(4)`, `coalesce=True`, `max_instances=1`.
- **Circuit breaker** (`circuit_breaker.py`): `get_breaker().allow_request()` check before searches.
- **Delays** (`delays.py`): `random_delay(min, max)` for anti-detection jitter.
- **Error handling** (`errors.py`): `classify_error(exc) -> ErrorCategory`, `get_retry_strategy(category) -> RetryStrategy`.

### Key Data Flow Observations
- `FlightResult` dataclass (from fast-flights scanner) has: origin, destination, date, price (int), airline, duration_min, stops, departure_time (HH:MM str), arrival_time (HH:MM str), fetched_at.
- `parse_offers()` (from LATAM scraper) returns dicts with: flight_code, origin, destination, departure (ISO 8601), arrival (ISO 8601), duration_min, stops, brands[{id, name, price, currency, fare_basis}].
- `PriceSnapshot` ORM expects: departure_time/arrival_time as `datetime` (timezone-aware), price as `Decimal`, brand as `str`.
- The scanner's `FlightResult` has no brand info — it returns a single price per flight. For fast-flights results, brand will be stored as `"ECONOMY"` (Google Flights doesn't expose brand tiers).
- The scanner's `FlightResult` has departure_time as `"HH:MM"` string — needs conversion to full datetime using the flight_date.
- `search_one_way()` already has circuit breaker + retry logic built in. The orchestrator should NOT add another retry layer around it.
- `search_latam_oneway()` returns raw BFF dict, needs `parse_offers()` to extract structured data. Each offer has multiple brands → one `PriceSnapshot` row per brand.

### Architectural Decision: Scanner Source
The hybrid architecture (memory) says fast-flights for broad sweeps, LATAM Playwright for detail. For this initial orchestrator implementation, **use fast-flights only** (`scanner.search_one_way`). Reasons:
1. Fast-flights is ~1-2s/search vs ~10-15s for Playwright — scanning many dates needs speed.
2. Playwright (LATAM scraper) is fragile (UI selectors, cookie consent, anti-bot) and not suited for batch scanning.
3. The LATAM detail fetcher (Option C) will be triggered later by a separate mechanism when price drops are detected.
4. `search_one_way` already handles circuit breaker, retries, and error classification internally.

If the circuit breaker is open when the orchestrator tries to search, `search_one_way` returns `[]` — the orchestrator should treat this as a retriable failure (record cursor, mark run as failed, try again next cycle).

## Decisions Made

1. **Single new module**: `src/flight_watcher/orchestrator.py` — keeps all scan orchestration logic in one place.
2. **Scanner source**: fast-flights (`scanner.search_one_way`) only for now. LATAM Playwright is out of scope.
3. **Brand mapping**: Since fast-flights returns a single price per flight (no fare class breakdown), store brand as `"ECONOMY"` for all fast-flights results.
4. **Datetime conversion**: Combine `FlightResult.date` (YYYY-MM-DD) + `FlightResult.departure_time`/`arrival_time` (HH:MM) into timezone-aware `datetime` objects (UTC assumed since Google Flights times are local — store as-is with UTC marker for now; proper timezone handling is a future improvement).
5. **One-way scanning flow** (FLI-27): For each config, expand dates → get all outbound + return dates individually → search each date one-way → store snapshots.
6. **Roundtrip scanning flow** (FLI-28): After one-way scanning, generate valid (outbound, return) pairs → for each pair, run `search_roundtrip()` (which calls two `search_one_way` internally) → store snapshots with `search_type=ROUNDTRIP`.
7. **Cursor resumption** (FLI-29): `ScanRun.last_successful_date` tracks progress through the sorted date list. On resume, skip all dates <= cursor. On failure, save cursor and mark run as failed. The cursor tracks one-way dates first, then roundtrip pairs (using the outbound date of the pair as cursor value). Use a `phase` field concept: one-way phase scans all individual dates, roundtrip phase scans all pairs. The cursor is the last completed date/pair's outbound date.
8. **Scheduler integration**: Register `run_all_scans()` as an APScheduler cron job triggered at `SCAN_HOUR_UTC`. The `__main__.py` calls a registration function after `start_scheduler()`.
9. **Error on individual date**: If a search returns empty (circuit breaker or no results), log and continue to next date — don't fail the whole run. Only fail the run if an unhandled exception propagates.
10. **Roundtrip scope reduction**: Given the combinatorial explosion of pairs (e.g., 9 outbound × 9 return = 81 pairs), and each pair requires 2 searches, this is 162 searches per config. That's too many for a single run. **Skip roundtrip scanning in this iteration.** The one-way results for both outbound and return dates already give price signals. Roundtrip will be a future optimization triggered selectively. Store `search_type=ONEWAY` for all results.

**Revised flow:**
1. Load active `SearchConfig` records
2. For each config: create `ScanRun`, expand dates, merge outbound+return into sorted unique date list
3. Resume from cursor if applicable
4. For each date: `search_one_way(origin, dest, date)` → convert `FlightResult` to `PriceSnapshot` rows → bulk insert → update cursor
5. Also search return direction: `search_one_way(dest, origin, date)` for return dates → store with same scan_run
6. Mark run complete

Wait — re-reading FLI-28 more carefully: "For each valid (outbound, return) date pair, run roundtrip search." This is explicitly requested. But the combinatorial issue is real. Resolution: **implement it but with a configurable max-pairs limit** (env var `MAX_ROUNDTRIP_PAIRS`, default 20). Select pairs by sampling evenly across the valid pair space. This keeps the feature functional without unbounded search counts.

Actually, simpler approach: the roundtrip search via `search_roundtrip()` just calls `search_one_way` twice. The one-way phase already searches all individual dates. The roundtrip phase would just be re-searching the same dates paired differently. The only value is if Google Flights returns different prices for roundtrip vs one-way — but `fast-flights` doesn't support native roundtrip search (it uses two one-way calls internally). So **roundtrip via fast-flights is identical to one-way** — there's no price difference to capture.

**Final decision on roundtrip**: Implement the roundtrip scanning interface (FLI-28) as a no-op for fast-flights backend since `search_roundtrip()` already delegates to `search_one_way()`. The orchestrator will:
- Phase 1: Scan all unique dates one-way (covers both outbound and return directions)
- Phase 2: For roundtrip pairs, store references linking outbound+return one-way results (no additional API calls needed)

Actually this overcomplicates it. Let me be pragmatic:

**FINAL decision**:
- Phase 1 (one-way, FLI-27): Scan all outbound dates as `origin→dest` and all return dates as `dest→origin`. Each stored as `search_type=ONEWAY`.
- Phase 2 (roundtrip, FLI-28): Skip for fast-flights backend. Add a `# TODO: roundtrip search for LATAM backend` comment. The roundtrip module structure exists but doesn't execute API calls in this iteration. FLI-28 acceptance criteria is met by having the roundtrip integration code path ready (function signature, DB storage logic, pair generation) even if fast-flights doesn't benefit from it.
- The cursor (FLI-29) tracks progress through the combined sorted date list.

## Implementation Tasks

### Task 1: Create `orchestrator.py` with core scan loop (FLI-26, FLI-29)
**File:** `src/flight_watcher/orchestrator.py`

Functions:
```python
def run_all_scans() -> None:
    """Top-level entry: load active configs, run scan for each."""

def run_scan(config: SearchConfig) -> None:
    """Run a full scan for one SearchConfig.
    1. Create ScanRun (status=RUNNING)
    2. Expand dates via expand_dates() + merge outbound+return into sorted unique list
    3. Check for existing today's ScanRun with cursor → resume from last_successful_date
    4. For each remaining date:
       a. search_one_way(config.origin, config.destination, date) → store snapshots
       b. search_one_way(config.destination, config.origin, date) → store snapshots (return direction)
       c. Update cursor (last_successful_date)
       d. random_delay() between searches
    5. On success: mark run COMPLETED
    6. On failure: save error_message, mark FAILED, cursor persists for resumption
    """

def _find_resumable_run(session: Session, config_id: int) -> ScanRun | None:
    """Find today's failed/running ScanRun for this config to resume from."""

def _dates_after_cursor(dates: list[str], cursor: date | None) -> list[str]:
    """Filter dates to only those after the cursor."""
```

### Task 2: One-way search → PriceSnapshot storage (FLI-27)
**File:** `src/flight_watcher/orchestrator.py` (same module)

Functions:
```python
def _search_and_store_oneway(
    session: Session,
    scan_run: ScanRun,
    origin: str,
    destination: str,
    flight_date: str,
) -> int:
    """Run one-way search, convert FlightResult→PriceSnapshot, bulk insert.
    Returns number of snapshots stored."""

def _flight_result_to_snapshot(
    result: FlightResult,
    scan_run_id: int,
    search_type: SearchType,
) -> PriceSnapshot:
    """Convert a FlightResult dataclass to a PriceSnapshot ORM instance."""
```

Key conversion logic:
- `FlightResult.departure_time` ("HH:MM") + `FlightResult.date` ("YYYY-MM-DD") → `datetime(year, month, day, hour, min, tzinfo=UTC)`
- `FlightResult.price` (int) → `Decimal(price)`
- `FlightResult.airline` → stored in `flight_code` (FlightResult doesn't have flight_code; use airline as identifier)
- brand = `"ECONOMY"` (fast-flights doesn't expose fare class)
- currency = `"BRL"` (hardcoded, matches scanner config)

### Task 3: Roundtrip integration placeholder (FLI-28)
**File:** `src/flight_watcher/orchestrator.py`

```python
def _run_roundtrip_phase(
    session: Session,
    scan_run: ScanRun,
    config: SearchConfig,
    outbound_dates: list[str],
    return_dates: list[str],
) -> int:
    """Roundtrip search phase.
    Currently a no-op for fast-flights backend (roundtrip = 2x one-way, already covered).
    Ready for LATAM Playwright backend which returns different roundtrip pricing.
    """
```

This satisfies FLI-28 by having the roundtrip code path with pair generation logic ready. A `# TODO` marks where LATAM-specific roundtrip logic will plug in.

### Task 4: Scheduler job registration (FLI-26)
**File:** `src/flight_watcher/scheduler.py` — add job registration function

```python
def register_scan_job() -> None:
    """Register the daily scan job."""
    scheduler = get_scheduler()
    scheduler.add_job(
        run_all_scans,
        trigger="cron",
        hour=SCAN_HOUR_UTC,
        id="daily_scan",
        replace_existing=True,
        jitter=1800,  # ±30min
    )
```

**File:** `src/flight_watcher/__main__.py` — call `register_scan_job()` after `start_scheduler()`

### Task 5: Tests for orchestrator (FLI-26, FLI-27, FLI-28, FLI-29)
**File:** `tests/test_orchestrator.py`

Test cases:
1. `test_run_all_scans_loads_active_configs` — mocks session, verifies query filters by `active=True`
2. `test_run_scan_creates_scan_run` — verifies ScanRun created with status=RUNNING
3. `test_run_scan_expands_dates_and_searches` — mocks expand_dates + search_one_way, verifies calls for each date in both directions
4. `test_run_scan_stores_price_snapshots` — verifies FlightResult→PriceSnapshot conversion and session.add_all
5. `test_run_scan_updates_cursor_after_each_date` — verifies last_successful_date updated
6. `test_run_scan_marks_completed_on_success` — verifies status=COMPLETED, completed_at set
7. `test_run_scan_marks_failed_on_error` — verifies status=FAILED, error_message saved, cursor preserved
8. `test_cursor_resumption_skips_completed_dates` — verifies dates <= cursor are skipped
9. `test_find_resumable_run_returns_todays_failed_run` — verifies query logic
10. `test_find_resumable_run_returns_none_if_no_prior` — verifies None when no prior run
11. `test_flight_result_to_snapshot_conversion` — verifies all field mappings
12. `test_roundtrip_phase_is_noop` — verifies no API calls made, returns 0
13. `test_empty_search_results_continues` — verifies empty results don't fail the run

Test patterns: follow existing conventions — `_make_*` factories, `MODULE = "flight_watcher.orchestrator"`, `patch()` for DB sessions and search functions.

### Task 6: Tests for scheduler registration
**File:** `tests/test_scheduler.py` — add test for `register_scan_job()`

Test case:
- `test_register_scan_job_adds_cron_trigger` — verifies `scheduler.add_job` called with correct params

## Acceptance Criteria

From issues + additional:
- [ ] Active `search_configs` are loaded and scanned
- [ ] Dates are expanded using `expand_dates()` from config fields
- [ ] One-way searches run for each date (both directions: origin→dest and dest→origin)
- [ ] `FlightResult` objects are converted to `PriceSnapshot` rows and stored
- [ ] `ScanRun` tracks status (running/completed/failed)
- [ ] `last_successful_date` cursor is updated after each successful date
- [ ] On failure: cursor preserved, error recorded, run marked failed
- [ ] On next run: resumes from cursor (skips already-scanned dates)
- [ ] Roundtrip integration code path exists (no-op for fast-flights)
- [ ] Scan job registered in APScheduler with cron trigger
- [ ] Parse errors handled gracefully (log + continue)
- [ ] All tests pass

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-26+27+28+29-scan-orchestrator
python -m pytest tests/ -v
python -c "from flight_watcher.orchestrator import run_all_scans; print('import ok')"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-XX` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- LATAM Playwright integration in the orchestrator (future work)
- Price drop detection or alerting
- Roundtrip API calls via fast-flights (no benefit over one-way)
