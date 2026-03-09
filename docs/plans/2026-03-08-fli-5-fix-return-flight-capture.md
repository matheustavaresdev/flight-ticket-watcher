# Implementation Plan: Fix return flight data capture in LATAM scraper

## Issues
- FLI-5: Fix return flight data capture in LATAM scraper

## Research Context

### Current Implementation
- `search_latam_roundtrip()` in `src/flight_watcher/latam_scraper.py:78-153` loads a single page with `trip=RT` URL and tries to capture two BFF responses via `page.on("response")` handler
- It waits for the first BFF response via `page.expect_response()`, then polls for 5s hoping a second response arrives
- Leg identification: compares `content[0].summary.origin.iataCode` with the search origin parameter
- `scripts/find_cheapest.py` already handles the `(outbound_data, return_data)` tuple correctly

### The Bug
The LATAM website uses a multi-step booking flow: it shows outbound flights first, and the return leg BFF request **only fires after the user selects an outbound flight**. The current code assumes both BFF requests fire on initial page load, but only the outbound leg arrives. The 5-second polling loop times out without ever seeing a second response.

### API Details
- BFF endpoint: `GET /bff/air-offers/v2/offers/search`
- Both outbound and return responses have identical structure (`content[]` with `summary.origin.iataCode`)
- Each response represents one direction only — no nested leg information
- URL builder `_build_latam_url` always constructs `trip=RT` URLs

### Test Patterns
- Tests in `tests/test_scanner.py` use `unittest.mock.patch` + `MagicMock`
- Factory helpers (`_make_flight`, `_make_segment`) for test data
- No tests exist yet for `latam_scraper.py`

## Decisions Made

**Approach: Two separate page loads with swapped origin/destination.**

Rationale:
- The alternative (page interaction — clicking an outbound flight to trigger return BFF) is fragile: depends on UI selectors that change, requires knowing which flight to click, and couples the scraper to LATAM's DOM structure.
- Two separate loads are ~2x the browser time but are much more reliable and simpler to implement.
- Each load uses `trip=OW` (one-way) to avoid ambiguity, or we can keep `trip=RT` and just capture the first response each time. Need to investigate if `trip=OW` changes pricing.
- The existing `search_latam()` function already captures a single BFF response reliably — we can reuse it directly.

**Fallback (if `trip=OW` doesn't work or changes pricing):** Keep `trip=RT` for both loads. The first BFF response on a RT page is always the outbound leg, so loading with swapped origin/destination gives us the return leg as the "outbound" of the swapped search.

## Implementation Tasks

### Task 1: Write diagnostic script to verify assumptions
Create `scripts/diagnose_roundtrip.py` — a temporary diagnostic that:
1. Loads a FOR→GRU round-trip search page
2. Captures ALL network requests matching `bff/air-offers` (not just status 200)
3. Logs: URL, status, timing, and first offer's origin IATA from each response
4. Waits 15 seconds (not 5) to ensure we're not just timing out too early
5. Prints a summary of how many BFF responses were captured

Run manually: `python scripts/diagnose_roundtrip.py`
Expected result: confirms only 1 BFF response fires on page load.

**This is a diagnostic tool. Delete it after Task 3.**

### Task 2: Refactor `search_latam_roundtrip` to use two separate page loads
**File:** `src/flight_watcher/latam_scraper.py`

Replace the current `search_latam_roundtrip` implementation:
1. Call `search_latam(origin, destination, outbound, inbound)` for the outbound leg
2. Call `search_latam(destination, origin, inbound, outbound)` for the return leg (swapped origin/destination and dates)
3. Return `(outbound_data, return_data)` as before

**Important considerations:**
- If `search_latam` uses `trip=RT` internally via `_build_latam_url`, that's fine — the first BFF response on a RT page is always for the outbound direction, which is what we want
- Add a brief `time.sleep(1)` between the two searches to avoid rate-limiting
- Print timing for both legs (already handled by `search_latam`'s internal timing)
- Preserve the function signature `(origin, destination, outbound, inbound, headless=False) -> tuple[dict | None, dict | None]`

### Task 3: Verify with live FOR→GRU search
Run the actual find_cheapest script:
```bash
python scripts/find_cheapest.py FOR GRU 2026-04-12 2026-04-17
```
Expected: both outbound (FOR→GRU) and return (GRU→FOR) sections display with flight data and round-trip summary.

### Task 4: Clean up
- Delete `scripts/diagnose_roundtrip.py`
- Remove dead code: the old multi-response capture logic (list append, polling loop, IATA matching) is no longer needed since `search_latam_roundtrip` now delegates to `search_latam`

### Task 5: Add unit tests for `search_latam_roundtrip`
**File:** `tests/test_latam_scraper.py` (new)

Tests:
1. `test_roundtrip_calls_search_latam_twice` — mock `search_latam`, verify it's called with correct args (swapped for return leg)
2. `test_roundtrip_returns_none_when_outbound_fails` — mock `search_latam` to return None for first call
3. `test_roundtrip_returns_none_return_when_return_fails` — mock `search_latam` to return None for second call
4. `test_parse_offers_extracts_brands` — unit test `parse_offers` with sample data from `research/search_response.json`

Follow existing test patterns: `_make_*` helpers, `unittest.mock.patch` at import location.

## Acceptance Criteria
- Round-trip search reliably captures both outbound and return flight data
- `find_cheapest.py FOR GRU 2026-04-12 2026-04-17` shows both legs + round-trip summary
- Unit tests pass for the refactored `search_latam_roundtrip`
- No regression in one-way search (`search_latam`)

## Verification
```bash
# Unit tests
python -m pytest tests/ -v

# Live verification (manual)
python scripts/find_cheapest.py FOR GRU 2026-04-12 2026-04-17
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-5`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Changing `search_latam` or `_build_latam_url` signatures
- Investigating page interaction approach (clicking outbound to trigger return)
