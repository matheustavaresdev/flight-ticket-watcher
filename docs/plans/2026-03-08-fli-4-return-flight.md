# Implementation Plan: Show Return Flight in find_cheapest Script

## Issues
- FLI-4: Show return flight in find_cheapest script

## Research Context

### Current State
- `find_cheapest.py` searches LATAM via `search_latam()` which navigates to a round-trip URL (`trip=RT`) and intercepts the BFF API response.
- The `on_response` handler in `search_latam()` overwrites `captured["data"]` on each BFF match, meaning it only retains the **last** captured response.
- The LATAM page for a round-trip search fires **two** BFF requests: one for outbound flights and one for return flights. Currently only one is captured.
- `parse_offers()` returns a flat list of offer dicts from a single BFF response — no concept of leg direction.
- `find_cheapest_flights()` sorts by cheapest LIGHT tier and `display_flight()` shows one leg per block.

### Key Insight
The LATAM search page with `trip=RT` fires two separate BFF `/offers/search` requests — one returns outbound offers, one returns return offers. The origin/destination in each response tells you which leg it is. We need to capture both responses from the same page load and display them together.

### Codebase Patterns
- `scanner.py` has a `search_roundtrip()` that does two one-way searches — but for LATAM BFF, we should capture both from a single page load (more efficient, one browser session).
- Display convention: boxed blocks with `=` headers, `─` separators, fare class tables.
- Defensive parsing with `.get()` throughout.

## Decisions Made

1. **Capture both BFF responses from single page load** — change `search_latam()` to collect a list of responses instead of overwriting. After capturing the first response, wait briefly for the second. This avoids launching two browser sessions.

2. **New function `search_latam_roundtrip()`** — returns a tuple `(outbound_data, return_data)`. Identify which is which by comparing response origin against the search origin. Keep existing `search_latam()` unchanged for backward compatibility.

3. **Display format** — show outbound section, then return section, then a combined round-trip total at the bottom. Each section shows top N cheapest flights with fare breakdowns. The combined total shows cheapest outbound LIGHT + cheapest return LIGHT.

4. **No new dependencies** — pure changes to existing files.

## Implementation Tasks

1. **Modify `latam_scraper.py` — add `search_latam_roundtrip()`** — affects `src/flight_watcher/latam_scraper.py`
   - Change `on_response` to append to a list instead of overwriting a single dict.
   - After first BFF response is captured via `expect_response`, add a short wait (3-5s) with polling to capture the second BFF response.
   - New function `search_latam_roundtrip()` that calls the modified capture logic and returns `(outbound_data, return_data)` by matching the origin IATA code in the response content against the search origin.
   - Keep `search_latam()` working as-is (it can delegate to the new logic and return just the first response, or remain untouched).

2. **Update `find_cheapest.py` — dual-leg display** — affects `scripts/find_cheapest.py`
   - Import `search_latam_roundtrip` from latam_scraper.
   - In `main()`, call `search_latam_roundtrip()` instead of `search_latam()`.
   - Parse both responses with `parse_offers()`.
   - Add a `display_leg()` wrapper that prints a section header ("OUTBOUND" / "RETURN") and then calls `display_flight()` for each of the top N flights.
   - After both sections, print a "ROUND-TRIP SUMMARY" block showing: cheapest outbound LIGHT price + cheapest return LIGHT price = total.

3. **Handle edge cases**
   - If only one BFF response is captured (return page didn't fire), show outbound only with a warning.
   - If a response has no offers, show a message for that leg.
   - One-way searches (no inbound date) should still work — detect via args and skip return section.

## Acceptance Criteria
1. Running `python scripts/find_cheapest.py FOR GRU 2026-04-12 2026-04-17` shows both outbound (FOR→GRU) and return (GRU→FOR) flights.
2. Each leg shows the top N cheapest flights with all fare tier breakdowns.
3. A round-trip total summary is displayed at the end.
4. If only outbound is captured, script still works with a warning (no crash).
5. Existing `search_latam()` function remains backward compatible.

## Verification
```bash
# Syntax check
python -c "from src.flight_watcher.latam_scraper import search_latam_roundtrip; print('import ok')"

# Type check (if mypy is configured)
# python -m mypy scripts/find_cheapest.py src/flight_watcher/latam_scraper.py

# Manual test (requires browser + network)
python scripts/find_cheapest.py FOR GRU 2026-04-12 2026-04-17
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] `search_latam_roundtrip()` captures both BFF responses from single page load
- [ ] `find_cheapest.py` displays outbound + return + round-trip total
- [ ] Graceful degradation when only one leg is captured
- [ ] PR created with `Closes FLI-4`

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Changes to `scanner.py`, `display.py`, or `models.py`
