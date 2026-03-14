# Implementation Plan: Test Coverage Improvements

## Issues
- FLI-65: Add search fast strict-date rejection tests to mirror search latam
- FLI-73: _make_snapshot helper uses fixed 08:00/11:00 departure/arrival times
- FLI-74: Add SearchResult.success(None) edge case test to test_models.py
- FLI-81: test(health): add combo test for DB unreachable + CB open priority
- FLI-84: Tighten weak assertion in test_get_error_hint_missing_context_returns_template
- FLI-85: Add test for search fast error path in test_cli.py

## Research Context

### Test File Structure
- `tests/test_cli.py` — CLI command tests using `CliRunner` from Typer. Classes: `TestSearchCommands` (line 506+), `TestHealthCommand` (line 299+), `TestReport` (line 739+)
- `tests/test_models.py` — Model/schema tests. `TestSearchResult` class (line 109+)
- `tests/test_errors.py` — Error module tests, standalone functions (line 80+)

### Key Patterns
- **Date rejection tests** (test_cli.py:559-638): Each test invokes CLI via `CliRunner`, passes invalid date, asserts `exit_code != 0` and error message contains expected text. `search latam` uses `--out`, `search fast` uses `--date`.
- **`_make_snapshot` helper** (test_cli.py:747-770): Returns a `MagicMock` with flight snapshot attributes. Currently hardcodes `departure_time` to 08:00 and `arrival_time` to 11:00 using `datetime(fd.year, fd.month, fd.day, 8, 0)`.
- **SearchResult tests** (test_models.py:110-143): Direct calls to `SearchResult.success()` / `.failure()`, assert fields.
- **Health daemon tests** (test_cli.py:423-468): Mock health JSON response, invoke `health daemon`, check exit code and output text. `db_reachable=False` → exit 1, `cb_state="open"` → exit 2.
- **Error hint tests** (test_errors.py:80-86): Call `get_error_hint(ErrorCategory.NETWORK_ERROR)` with no context, assert placeholders remain.
- **Error display tests** (test_cli.py:670-736): Mock `search_latam_roundtrip` to return `SearchResult.failure(...)`, invoke CLI, check stderr for category/hint text.

### Implementation Code References
- `src/flight_watcher/cli/search.py:16-27` — `_print_search_error()` function used by both `search latam` and `search fast`
- `src/flight_watcher/cli/search.py:95-137` — `search fast` command, calls `scanner.search_one_way`
- `src/flight_watcher/cli/health.py:66-73` — Health check priority: DB unreachable (exit 1) checked before CB open (exit 2)
- `src/flight_watcher/cli/validators.py:8` — `_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")`
- `src/flight_watcher/errors.py:45-48` — NETWORK_ERROR hint template with `<ORIGIN>`, `<DEST>`, `<DATE>` placeholders
- `src/flight_watcher/errors.py:61-69` — `get_error_hint()` returns raw template on missing keys

## Decisions Made
- **FLI-65:** Add 3 new tests (not 4) — `test_search_fast_rejects_invalid_date` already exists (line 595). Add: `test_search_fast_rejects_single_digit_date_components`, `test_search_fast_rejects_datetime_string`, `test_search_fast_rejects_extended_year`.
- **FLI-73:** Add `departure_hour`, `departure_minute`, `arrival_hour`, `arrival_minute` params with defaults 8, 0, 11, 0. Minimal change, no existing callers break.
- **FLI-74:** Single test: `test_success_with_none_data`. Assert `ok=True`, `data is None`, `error is None`.
- **FLI-81:** Single test: `test_health_daemon_db_unreachable_and_breaker_open`. Mock both conditions, assert exit code 1 (DB priority wins).
- **FLI-84:** Replace `assert "<ORIGIN>" in hint or "origin" in hint.lower()` with strict checks for all 3 angle-bracket placeholders: `"<ORIGIN>"`, `"<DEST>"`, `"<DATE>"`.
- **FLI-85:** Single test: `test_search_fast_error_displays_category_and_hint`. Mock `scanner.search_one_way` to return failure with category + hint, check stderr output.

## Implementation Tasks

1. **FLI-65: Add 3 `search fast` date rejection tests** — `tests/test_cli.py`
   - Add `test_search_fast_rejects_single_digit_date_components` — invoke `["search", "fast", "--origin", "GRU", "--dest", "FOR", "--date", "2026-4-1"]`, assert exit_code != 0
   - Add `test_search_fast_rejects_datetime_string` — date `"2026-04-01T00:00:00"`, assert exit_code != 0
   - Add `test_search_fast_rejects_extended_year` — date `"+002026-04-01"`, assert exit_code != 0
   - Place them after the existing `test_search_fast_rejects_invalid_date` test (around line 611)

2. **FLI-73: Parameterize `_make_snapshot` times** — `tests/test_cli.py`
   - Add params: `departure_hour=8`, `departure_minute=0`, `arrival_hour=11`, `arrival_minute=0`
   - Use these in the `datetime()` constructors instead of hardcoded values
   - No existing callers change (defaults match current behavior)

3. **FLI-74: Add `SearchResult.success(None)` test** — `tests/test_models.py`
   - Add `test_success_with_none_data` to `TestSearchResult`
   - `r = SearchResult.success(None)` → assert `r.ok is True`, `r.data is None`, `r.error is None`, `r.error_category is None`

4. **FLI-81: Add DB+CB combo health test** — `tests/test_cli.py`
   - Add `test_health_daemon_db_unreachable_and_breaker_open` to `TestHealthCommand`
   - Mock health response with `db_reachable: false` AND `circuit_breaker.state: "open"`
   - Assert exit code 1 (not 2), output contains "[FAIL]" and "unreachable"

5. **FLI-84: Tighten error hint assertion** — `tests/test_errors.py`
   - Replace line ~86: `assert "<ORIGIN>" in hint or "origin" in hint.lower()` with:
     ```python
     assert "<ORIGIN>" in hint
     assert "<DEST>" in hint
     assert "<DATE>" in hint
     ```

6. **FLI-85: Add `search fast` error path test** — `tests/test_cli.py`
   - Add `test_search_fast_error_displays_category_and_hint` to `TestSearchCommands`
   - Mock `flight_watcher.scanner.search_one_way` returning `SearchResult.failure(error="timeout", error_category=ErrorCategory.NETWORK_ERROR, hint="Check connection")`
   - Invoke `["search", "fast", "--origin", "GRU", "--dest", "FOR", "--date", "2026-04-12"]`
   - Assert exit_code == 0 (CLI doesn't crash on search error), stderr contains "category=network_error", "Hint:", "Check connection"

## Acceptance Criteria
- All 6 issues addressed with corresponding tests
- All new tests pass
- No existing tests broken
- `_make_snapshot` defaults unchanged (backward compatible)

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-65+73+74+81+84+85-test-coverage
python -m pytest tests/test_cli.py tests/test_models.py tests/test_errors.py -v 2>&1 | tail -40
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
