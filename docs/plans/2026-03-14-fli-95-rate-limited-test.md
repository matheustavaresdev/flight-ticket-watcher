# Implementation Plan: Add direct RATE_LIMITED outbound test

## Issues
- FLI-95: Add direct RATE_LIMITED outbound test for halting behavior

## Research Context

### Existing Test Patterns
The `TestFailureAwareCursorAdvancement` class in `tests/test_orchestrator.py` already has:
- `test_blocked_halts_scan_and_does_not_advance_cursor` (lines 662-683) — outbound BLOCKED halts scan
- `test_network_error_halts_scan_and_does_not_advance_cursor` (lines 690-711) — outbound NETWORK_ERROR halts scan
- `test_outbound_succeeds_return_rate_limited_cursor_not_advanced` (lines 797-821) — return-leg RATE_LIMITED halts scan

Missing: a direct outbound RATE_LIMITED test (symmetric with BLOCKED and NETWORK_ERROR outbound tests).

### Orchestrator Logic
All three error categories (BLOCKED, NETWORK_ERROR, RATE_LIMITED) share `skip_item=False` in `RETRY_STRATEGIES`, meaning they all raise `SearchFailedError` and halt the scan. The code path at `orchestrator.py:184-199` checks `strategy.skip_item` and raises if False.

### Test Structure
All halting tests follow identical structure:
1. `@patch` decorators: `get_session`, `_find_resumable_run`, `_search_and_store_oneway`, `random_delay`, `expand_dates`
2. Set `mock_search.return_value = SearchResult.failure(error=..., error_category=ErrorCategory.XXX)`
3. Use `_setup_session_and_scan_run` helper
4. Assert `SearchFailedError` raised, status=FAILED, `last_successful_date=None`

## Decisions Made
- Place the new test between the NETWORK_ERROR outbound test and the PAGE_ERROR test (after line 711) for logical grouping with the other outbound halting tests.
- Mirror the NETWORK_ERROR test structure exactly, changing only the error category and error message string.

## Implementation Tasks
1. Add `test_rate_limited_halts_scan_and_does_not_advance_cursor` to `TestFailureAwareCursorAdvancement` in `tests/test_orchestrator.py` — insert after the NETWORK_ERROR outbound test (~line 711), mirroring its structure with `ErrorCategory.RATE_LIMITED` and error string `"429 Too Many Requests"`.

## Acceptance Criteria
- New test exists and passes
- Test mirrors BLOCKED/NETWORK_ERROR outbound test structure
- Test asserts `SearchFailedError` is raised, status=FAILED, cursor not advanced

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-95-rate-limited-test
python -m pytest tests/test_orchestrator.py::TestFailureAwareCursorAdvancement::test_rate_limited_halts_scan_and_does_not_advance_cursor -v
python -m pytest tests/test_orchestrator.py -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-95`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
