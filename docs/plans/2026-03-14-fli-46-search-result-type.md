# Implementation Plan: Add Structured SearchResult Return Type (FLI-46)

## Issues
- FLI-46: Add structured SearchResult return type

## Research Context

### Current State
Functions return `[]`, `None`, or `(None, None)` on failure. Callers cannot distinguish "no flights found" from "search crashed."

**Return patterns today:**
| Function | Success | Failure |
|----------|---------|---------|
| `scanner.search_one_way()` | `list[FlightResult]` | `[]` |
| `scanner.search_roundtrip()` | `tuple[list, list]` | tuple of empty lists |
| `latam_scraper.search_latam()` | `dict` | `None` |
| `latam_scraper.search_latam_oneway()` | `dict \| None` | `None` |
| `latam_scraper.search_latam_roundtrip()` | `tuple[dict, dict]` | `(None, None)` or `(data, None)` |

### Existing Infrastructure
- `ErrorCategory` enum already exists in `errors.py`: `RATE_LIMITED`, `NETWORK_ERROR`, `PAGE_ERROR`, `BLOCKED`
- `classify_error()` already classifies exceptions into categories
- `FlightResult` dataclass in `models.py` (lines 24-35) — plain `@dataclass`
- Circuit breaker records failures with category in both scanner and scraper

### Callers That Need Updating
1. **`orchestrator.py:259`** — `_search_and_store_oneway()` calls `search_one_way()`, checks `if not results:`
2. **`cli/search.py:80-87`** — `search_fast()` calls `search_one_way()` / `search_roundtrip()`, passes to `print_results()`
3. **`cli/search.py:33-48`** — `search_latam()` calls `search_latam_roundtrip()` / `search_latam_oneway()`, passes to `parse_offers()`
4. **`display.py:6`** — `print_results()` accepts `list[FlightResult]`

### Test Patterns
- Factory functions: `_make_flight()`, `_make_bff_response()`, `_make_flight_result()`
- Mock with `patch(f"{MODULE}.function_name")`
- Context manager style: `with (patch(...), patch(...)):`
- Assertions: `assert isinstance(r, FlightResult)`, field-by-field checks

## Decisions Made

1. **`SearchResult` is a generic wrapper, not a replacement for `FlightResult`.**
   `SearchResult.data` holds the payload (`list[FlightResult]`, `dict`, etc.). `FlightResult` stays as-is.
   Rationale: Different search backends return different data shapes. The wrapper adds metadata (ok/error/duration) without forcing a common payload type.

2. **Use `Generic[T]` for `SearchResult[T]` to preserve type safety.**
   `SearchResult[list[FlightResult]]` for scanner, `SearchResult[dict]` for LATAM scraper.
   Rationale: Callers already know what type they expect — generics keep that explicit.

3. **Add class methods `SearchResult.success()` and `SearchResult.failure()` for ergonomic construction.**
   Rationale: Reduces boilerplate at every return site. Makes intent clear.

4. **Both scanner AND latam_scraper get refactored in this PR.**
   The issue explicitly lists both files. Doing only one would leave the silent-failure antipattern active.

5. **`duration_sec` is measured inside each search function using `time.monotonic()`.**
   Rationale: The caller shouldn't need to wrap timing logic. Each function owns its own duration.

## Implementation Tasks

### Task 1: Add `SearchResult` dataclass to `models.py`

Add after `FlightResult` (line 35):

```python
from typing import Generic, TypeVar

T = TypeVar("T")

@dataclass
class SearchResult(Generic[T]):
    ok: bool
    data: T | None = None
    error: str | None = None
    error_category: ErrorCategory | None = None
    hint: str | None = None
    duration_sec: float = 0.0

    @classmethod
    def success(cls, data: T, duration_sec: float = 0.0) -> "SearchResult[T]":
        return cls(ok=True, data=data, duration_sec=duration_sec)

    @classmethod
    def failure(
        cls,
        error: str,
        error_category: ErrorCategory | None = None,
        hint: str | None = None,
        duration_sec: float = 0.0,
    ) -> "SearchResult[T]":
        return cls(
            ok=False,
            error=error,
            error_category=error_category,
            hint=hint,
            duration_sec=duration_sec,
        )
```

Import `ErrorCategory` from `errors.py`. Affects: `models.py`

### Task 2: Refactor `scanner.py` to return `SearchResult`

Change `search_one_way()` return type from `list[FlightResult]` to `SearchResult[list[FlightResult]]`.

At each return point:
- **Line 29** (`return []`, circuit breaker open): → `SearchResult.failure("circuit breaker open", ErrorCategory.BLOCKED, hint="wait for breaker reset")`
- **Line 43** (`return results`, success): → `SearchResult.success(results)`
- **Line 60** (`return []`, page error skip): → `SearchResult.failure(str(exc), category, hint="skipping route")`
- **Line 85** (`return []`, retries exhausted): → `SearchResult.failure(str(exc), category, hint="retries exhausted")`

Add `time.monotonic()` at function start, pass `duration_sec` to every return.

Change `search_roundtrip()` to return `tuple[SearchResult[list[FlightResult]], SearchResult[list[FlightResult]]]` — it already delegates to `search_one_way()` twice, so this is automatic.

Affects: `scanner.py`

### Task 3: Refactor `latam_scraper.py` to return `SearchResult`

**`search_latam()`** — return `SearchResult[dict]`:
- Line 116 (`return None`, error): → `SearchResult.failure(...)`
- Line 118 (`return captured.get("data")`, success): → `SearchResult.success(data)` or `.failure()` if data is None

**`search_latam_oneway()`** — return `SearchResult[dict]`:
- Line 177 (`return None`, error): → `SearchResult.failure(...)`
- Line 179 (`return captured.get("data")`): → same as above

**`search_latam_roundtrip()`** — return `tuple[SearchResult[dict], SearchResult[dict]]`:
- Line 202 (`return None, None`, breaker open): → `(SearchResult.failure(...), SearchResult.failure(...))`
- Line 250 (`return None, None`, outbound failed): → `(SearchResult.failure(...), SearchResult.failure(...))`
- Line 285 (`return outbound_data, None`): → `(SearchResult.success(outbound_data), SearchResult.failure(...))`
- Line 306 (`return outbound_data, None`): → same pattern
- Line 336 (`return outbound_data, return_data`): → `(SearchResult.success(outbound_data), SearchResult.success(return_data))` or appropriate failure for None data

Add `time.monotonic()` timing in each function.

Affects: `latam_scraper.py`

### Task 4: Update `orchestrator.py` callers

`_search_and_store_oneway()` (line 259):
- Currently: `results = search_one_way(...)`, `if not results: return 0`
- Change to: `result = search_one_way(...)`, `if not result.ok: return 0`, use `result.data` for snapshots

Affects: `orchestrator.py`

### Task 5: Update `cli/search.py` callers

**`search_fast()`:**
- `search_one_way()` now returns `SearchResult` — use `.data` for results, `.ok` for status
- `search_roundtrip()` now returns tuple of `SearchResult` — unpack `.data`
- Pass `result.data or []` to `print_results()` and `len()`
- On failure: print error info from `result.error`

**`search_latam()`:**
- `search_latam_roundtrip()` / `search_latam_oneway()` now return `SearchResult`
- Check `.ok` instead of truthiness, use `.data` for `parse_offers()`
- On failure: print error info

Affects: `cli/search.py`

### Task 6: Update `display.py` (minor)

`print_results()` signature stays `list[FlightResult]` — callers pass `result.data`. No structural change needed, but verify type hints.

Affects: `display.py` (type hints only, if any)

### Task 7: Update tests

**`test_scanner.py`:**
- All assertions change from `results[0].field` to `result.ok`, `result.data[0].field`
- Empty-list tests become `assert not result.ok` or `assert result.ok and result.data == []`
- Add tests for `SearchResult.failure()` on circuit breaker / retry exhaustion

**`test_latam_scraper.py`:**
- `None` checks become `.ok` checks
- Tuple unpacking: `outbound, ret = ...` stays, but check `.ok` and `.data`

**`test_orchestrator.py`:**
- Mock `search_one_way()` to return `SearchResult.success(results)` instead of `results`
- Mock failure case: `SearchResult.failure("error")`

**`test_cli.py`:**
- Mock search functions to return `SearchResult` objects
- Assert error output on failure results

Affects: `test_scanner.py`, `test_latam_scraper.py`, `test_orchestrator.py`, `test_cli.py`

### Task 8: Add `SearchResult` unit tests to `test_models.py`

- Test `SearchResult.success()` sets `ok=True`, `data=payload`, `error=None`
- Test `SearchResult.failure()` sets `ok=False`, `data=None`, `error=msg`, `error_category`
- Test `duration_sec` propagation

Affects: `test_models.py`

## Acceptance Criteria
- No function returns bare `None` or `[]` on failure
- Every failure carries error message, category, and hint
- Every success carries `duration_sec`
- Tests updated and passing

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-46-search-result-type
python -m pytest tests/ -v
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-46`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Changes to `parse_offers()` or `save_response()` — they process data, not search
