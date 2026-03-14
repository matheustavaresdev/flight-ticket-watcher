# Implementation Plan: Deduplicate on_response & Consolidate Roundtrip Cleanup

## Issues
- FLI-76: Deduplicate `on_response` closure in `latam_scraper.py`
- FLI-78: Refactor `search_latam_roundtrip` to use a single `try/finally` for cleanup

## Research Context

### Current State (`src/flight_watcher/latam_scraper.py`, 506 lines)

**FLI-76 — Duplicate `on_response` closures:**
- `search_latam()` lines 72-80 and `search_latam_oneway()` lines 157-165 have 100% identical `on_response` closures
- Both capture to a `captured` dict: set `captured["data"]`, `captured["status"]`, pop `"error"` on success; set `captured["error"]` and `captured["status"]` on exception
- `search_latam_roundtrip()` lines 266-278 has a **different** closure: appends to a `bff_responses` list, validates response structure, and logs — keep this one separate

**FLI-78 — Scattered cleanup in roundtrip:**
- `search_latam` and `search_latam_oneway` already use a clean nested `try/except` inside `try/finally` pattern
- `search_latam_roundtrip` has `context.close()` + `browser.close()` copy-pasted in 3 separate `except` blocks (lines ~302-303, ~350-351, ~389-390), plus bare calls at end (lines 436-437)
- The 4th exception handler has no cleanup at all — relies on falling through to lines 436-437
- No `try/finally` wrapper, so an unexpected exception path could leak resources

### Callers (unaffected — no signature changes)
- `src/flight_watcher/cli/search.py` — calls `search_latam_roundtrip()` and `search_latam_oneway()`
- `src/flight_watcher/orchestrator.py` — planned future use, currently no-op

### Tests (`tests/test_latam_scraper.py`, 410 lines)
- Tests verify cleanup via mock assertions (`context.close.assert_called_once()`)
- Happy path and failure path tests exist for all three functions
- Tests should pass unchanged since behavior is preserved

## Decisions Made

1. **Extract a factory function, not a standalone callback.** Since `on_response` needs closure over `captured` dict, use `_make_bff_intercept(captured: dict)` that returns the closure. This avoids making `captured` a parameter of the callback itself (which would break `page.on("response", fn)` signature).

2. **Keep roundtrip's `on_response` separate.** It uses fundamentally different state (`bff_responses` list, structural validation, logging). Forcing it into the same helper would require awkward parameterization. Not worth it.

3. **Wrap roundtrip body in `try/finally` after browser/context creation.** Remove all inline `context.close()`/`browser.close()` from except blocks. Exception handlers just return `SearchResult.failure(...)` — the `finally` block handles cleanup. Matches the pattern already used by the other two functions.

## Implementation Tasks

1. **Add `_make_bff_intercept()` helper** — affects `src/flight_watcher/latam_scraper.py`
   - Place it as a module-level private function before `search_latam()`
   - Signature: `def _make_bff_intercept(captured: dict) -> Callable`
   - Body: the existing `on_response` closure contents
   - Returns the inner function

2. **Replace inline closures in `search_latam()` and `search_latam_oneway()`** — affects `src/flight_watcher/latam_scraper.py`
   - Replace `def on_response(response): ...` block with `on_response = _make_bff_intercept(captured)`
   - Keep `page.on("response", on_response)` unchanged

3. **Consolidate `search_latam_roundtrip()` cleanup into `try/finally`** — affects `src/flight_watcher/latam_scraper.py`
   - After `context = _create_context(browser)` and `page = context.new_page()`, wrap remaining body in `try/finally`
   - Move `context.close()` and `browser.close()` to `finally` block only
   - Remove all `context.close()` / `browser.close()` from individual `except` blocks
   - Exception handlers continue to return `SearchResult.failure(...)` — cleanup happens in `finally` after the return

## Acceptance Criteria
- `on_response` closure defined in exactly one place for the `captured`-dict pattern
- `search_latam_roundtrip` has a single `try/finally` for browser/context cleanup
- No inline `context.close()` / `browser.close()` in any `except` block of `search_latam_roundtrip`
- All existing tests pass without modification
- No signature or return type changes to any public function

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-76+78-scraper-cleanup
python -m pytest tests/test_latam_scraper.py -v
python -m pytest tests/ -v --tb=short
python -c "from flight_watcher.latam_scraper import search_latam, search_latam_oneway, search_latam_roundtrip; print('imports ok')"
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-76` and `Closes FLI-78` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring the roundtrip `on_response` closure (different logic, keep as-is)
- Refactoring `_create_context()` or other helpers
- Adding new tests beyond verifying existing ones pass
- Fixing pre-existing lint warnings in untouched code
- Any cleanup, polish, or "while I'm here" improvements
