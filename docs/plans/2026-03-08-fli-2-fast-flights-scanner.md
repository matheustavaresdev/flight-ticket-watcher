# Implementation Plan: Option A — Basic fast-flights Scanner (FLI-2)

## Issues
- FLI-2: Option A: Basic fast-flights scanner

## Research Context

### Codebase State
- Minimal scaffold: `src/flight_watcher/__init__.py` (empty), `pyproject.toml` with `fast-flights` + `patchright`
- Python 3.12, hatchling build, src-layout
- No tests, no data models, no config patterns exist yet

### fast-flights Library (v2.2, AWeirdDev/flights)
- **Import**: `from fast_flights import FlightQuery, Passengers, create_query, get_flights`
- **API**: `create_query(flights=[FlightQuery(...)], trip="one-way", passengers=Passengers(adults=1), language="pt-BR", currency="BRL")` → `Query`
- **Results**: `get_flights(query)` → `MetaList[Flights]` where each `Flights` has: `.price` (int), `.airlines` (list[str]), `.flights` (list[SingleFlight])
- **SingleFlight**: `.from_airport.code`, `.to_airport.code`, `.departure.date` (tuple y,m,d), `.departure.time` (tuple h,m), `.arrival.time`, `.duration` (minutes), `.plane_type`

### Known Gotchas
1. **Round-trip broken** (issue #60) — return flight data missing. Workaround: two one-way queries.
2. **Parser instability** (issue #98) — ~25% chance of missing fields due to CSS class name changes. Need retry logic.
3. **No error handling in library** — `AttributeError`, `KeyError`, `IndexError` propagate unhandled. Must wrap with try/except.
4. **Rate limiting** — Google Flights undocumented limits. Space requests 2-3s apart, plan for 30-60 searches/hour max.

### Test Patterns
- No tests exist yet. Will set up pytest with `tests/` dir, `conftest.py`, `unittest.mock` for mocking `get_flights`.
- Add `pytest` to optional test deps in pyproject.toml.

## Decisions Made

1. **Data model**: Use `dataclass` (not Pydantic) — matches issue spec, no validation needed beyond what we build, zero extra deps.
2. **Module structure**: `src/flight_watcher/scanner.py` (single module, not a subpackage) — issue explicitly names this file, and complexity doesn't warrant a package yet.
3. **Roundtrip handling**: Two one-way queries with 2s delay between them — workaround for issue #60.
4. **Error handling strategy**: Catch broad exceptions from `get_flights()`, log with `logging` module, return empty list on failure (don't crash). Retry up to 2 times with exponential backoff for transient errors.
5. **Console output**: Simple tabular print using f-strings — no need for `rich` or `tabulate` dependency for now.
6. **Entry point**: `__main__.py` with hardcoded example route (FOR→GRU) for manual testing. No CLI framework yet.
7. **Test framework**: Add `pytest` as optional dep. Mock `get_flights` to avoid hitting Google Flights in tests.

## Implementation Tasks

### Task 1: Data model — `src/flight_watcher/models.py`
Create `FlightResult` dataclass matching the issue spec:
```python
@dataclass
class FlightResult:
    origin: str           # IATA code
    destination: str      # IATA code
    date: str             # YYYY-MM-DD
    price: int            # in BRL
    airline: str
    duration_min: int
    stops: int
    departure_time: str   # HH:MM
    arrival_time: str     # HH:MM
    fetched_at: datetime
```

### Task 2: Scanner module — `src/flight_watcher/scanner.py`
Functions:
- `search_one_way(origin, destination, date, passengers=1) -> list[FlightResult]` — builds query, calls `get_flights`, maps results to `FlightResult` list, handles errors with retry.
- `search_roundtrip(origin, destination, departure_date, return_date, passengers=1) -> tuple[list[FlightResult], list[FlightResult]]` — calls `search_one_way` twice with 2s delay between.
- Internal `_map_flight_to_results(flights_obj, origin, destination, date) -> list[FlightResult]` — converts library `Flights` object to our model. Calculates stops as `len(flights_obj.flights) - 1`. Extracts airline as comma-joined `flights_obj.airlines`.

Error handling:
- Wrap `get_flights()` in try/except catching `Exception` (library has no typed errors)
- Retry up to 2 times with `time.sleep(2 ** attempt)` backoff
- On final failure: log error, return empty list
- Use `logging` module (logger = `logging.getLogger(__name__)`)

### Task 3: Console output — `src/flight_watcher/display.py`
- `print_results(results: list[FlightResult], header: str = "") -> None` — prints results in readable format to stdout.
- Format: table-like with columns: Price, Airline, Departure, Arrival, Duration, Stops.
- Handle empty results: print "No flights found."

### Task 4: Entry point — `src/flight_watcher/__main__.py`
- Hardcoded demo: search FOR→GRU on a date ~30 days from now
- Also search return GRU→FOR
- Print both legs using `print_results`
- Runnable via `python -m flight_watcher`

### Task 5: Tests — `tests/test_scanner.py`
Add to pyproject.toml:
```toml
[project.optional-dependencies]
test = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Tests (mock `get_flights` throughout):
- `test_search_one_way_returns_flight_results` — mock returns valid data, verify FlightResult fields
- `test_search_one_way_empty_results` — mock returns empty list, verify empty list returned
- `test_search_one_way_handles_exception` — mock raises Exception, verify empty list returned (no crash)
- `test_search_roundtrip_calls_twice` — verify two calls to search with correct params
- `test_map_flight_calculates_stops` — 2 segments → 1 stop, 1 segment → 0 stops

### Task 6: Verify end-to-end
- Run `pytest` — all tests pass
- Run `python -m flight_watcher` — verify console output (manual, expect possible rate limit)

## Acceptance Criteria
- Can search FOR→GRU on a given date and get price results
- Can search roundtrip (two one-way) FOR→GRU + GRU→FOR
- Results printed to console with price, airline, duration, stops
- Handles errors gracefully (log + skip, don't crash)

## Verification
```bash
# Install in editable mode with test deps
pip install -e ".[test]"

# Run tests
pytest -v

# Run the scanner manually (may hit rate limits — that's OK, tests cover logic)
python -m flight_watcher
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes (`pip install -e .`)
- [ ] Tests pass (`pytest -v`)
- [ ] PR created with `Closes FLI-2`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Database storage, scheduling, or alerting (future issues)
- Proxy/BrightData integration
- CLI framework (argparse, click, etc.)
