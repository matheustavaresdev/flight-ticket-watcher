# Implementation Plan: CLI Report Polish

## Issues
- FLI-59: Pass explicit limit to best_combinations() to avoid silent 20-row cap
- FLI-60: Verify CLI invocation shape: `report <id>` vs `report show <id>`
- FLI-61: Tighten brand filter assertion in test_report_show_brand_filter
- FLI-62: Add negative assertion in test_report_show_top_limits_rows
- FLI-63: Hardcoded BRL currency symbol in report formatter
- FLI-64: Fix _make_snapshot helper: departure/arrival times ignore flight_date param

## Research Context

### Codebase Findings

**report.py structure:**
- `_fmt_price(price, currency="BRL")` at line 19 — maps BRL→"R$", else uses raw currency code
- `show()` command at line 28 — registered as `@app.command("show")`, invoked as `report show <id>`
- Line 74: `combos = best_combinations(session, config_id, brand=b_arg)` — no `limit` passed
- Lines 109-110: `_fmt_price(row["roundtrip_total"], "BRL")` — hardcodes "BRL" but `row` dict has `currency` key

**queries.py signatures:**
- `best_combinations(session, search_config_id, brand="LIGHT", limit=20)` — default limit=20
- `get_latest_snapshots(session, search_config_id, search_type=None, brand="LIGHT")`
- `roundtrip_vs_oneway(session, search_config_id, brand="LIGHT")`

**test_cli.py patterns:**
- `_make_snapshot()` at line 363 — hardcodes `departure_time = datetime(2026, 6, 21, 8, 0)` and `arrival_time = datetime(2026, 6, 21, 11, 0)` regardless of `flight_date` param
- `test_report_show_brand_filter` at line 459 — loose triple-or assertion on line 476
- `test_report_show_top_limits_rows` at line 478 — only checks "Showing top 5 of" text, no negative assertion
- `make_session_mock()` returns `(get_session_mock, session_mock)` tuple

**CLI invocation (FLI-60):** Tests all use `["report", "show", "1"]` and pass. The `show` subcommand IS required. This matches Typer's behavior — `app.command("show")` creates a named subcommand. The documented `report <id>` shape would only work with `invoke_without_command=True` on the Typer instance + a callback. Current tests confirm `report show <id>` works correctly.

### PriceSnapshot model
`departure_time` and `arrival_time` are `DateTime(timezone=True)` in the model, but test mocks use naive datetimes. Since these are MagicMock objects (not real model instances), timezone awareness doesn't matter for the test assertions — the tests only check string output.

## Decisions Made

1. **FLI-59 limit:** Pass `limit=None` to `best_combinations()`. The underlying query (`queries.py`) needs to handle `None` as "no limit". Check if the SQL query supports this — if not, pass a very high number like `limit=1000`. This ensures all trip-length buckets appear regardless of config.

2. **FLI-60 resolution:** The invocation shape `report show <id>` is correct and all 198 tests confirm it. The issue asks to "verify" — resolution is to confirm it works, add a brief comment, and close the issue. No code change needed.

3. **FLI-61 assertion fix:** Replace the loose triple-or with specific `assert_called_once_with`. Also verify `best_combinations` and `roundtrip_vs_oneway` receive the brand filter by capturing their mock call args.

4. **FLI-62 negative assertion:** Assert that flight codes beyond top N are NOT in output. Test creates LA0000-LA0019 with prices 400-419 (ascending). With `--top 5`, cheapest 5 are LA0000-LA0004. Assert LA0005 through LA0019 are absent.

5. **FLI-63 currency fix:** Change lines 109-110 from hardcoded `"BRL"` to `row["currency"]`. The `_fmt_price` function itself is fine — it already handles arbitrary currency codes via the else branch.

6. **FLI-64 helper fix:** Update `_make_snapshot` to derive `departure_time` and `arrival_time` from the `flight_date` parameter. Use `datetime(fd.year, fd.month, fd.day, 8, 0)` and `datetime(fd.year, fd.month, fd.day, 11, 0)` where `fd` is the resolved flight_date.

## Implementation Tasks

### Task 1: Fix best_combinations limit (FLI-59)
- **File:** `src/flight_watcher/queries.py` — check if `limit=None` is supported in the SQL query
- **File:** `src/flight_watcher/cli/report.py:74` — pass explicit limit
- If `queries.py` uses `LIMIT :limit` in raw SQL, `None` won't work. In that case, conditionally omit the LIMIT clause or pass a high number.

### Task 2: Fix hardcoded BRL in RT vs OW section (FLI-63)
- **File:** `src/flight_watcher/cli/report.py:109-110`
- Change `_fmt_price(row["roundtrip_total"], "BRL")` → `_fmt_price(row["roundtrip_total"], row["currency"])`
- Same for `oneway_total` on line 110

### Task 3: Fix _make_snapshot helper dates (FLI-64)
- **File:** `tests/test_cli.py:363-375`
- Derive `departure_time` and `arrival_time` from the `flight_date` parameter

### Task 4: Tighten brand filter test assertion (FLI-61)
- **File:** `tests/test_cli.py:459-476`
- Replace loose triple-or with `mock_snaps.assert_called_once_with(session_mock, 1, brand="LIGHT")`
- Also assert `best_combinations` and `roundtrip_vs_oneway` mocks were called with `brand="LIGHT"`

### Task 5: Add negative assertion for top limit (FLI-62)
- **File:** `tests/test_cli.py:478-493`
- After existing assertions, add: `assert "LA0005" not in result.output` (or similar for codes that should be excluded)

### Task 6: Close FLI-60 (no code change needed)
- Verify invocation shape works via existing tests (already confirmed)
- Close issue with comment explaining the verification

## Acceptance Criteria

- FLI-59: `best_combinations()` called with explicit limit that doesn't cap at 20
- FLI-60: Verified and closed — invocation is `report show <id>` and works correctly
- FLI-61: Brand filter test uses specific assertions, covers all three query functions
- FLI-62: Negative assertion confirms excluded flights don't appear in output
- FLI-63: RT vs OW section uses `row["currency"]` instead of hardcoded "BRL"
- FLI-64: `_make_snapshot` departure/arrival times reflect the `flight_date` parameter

## Verification

```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-59+60+61+62+63+64-report-polish
python -m pytest tests/test_cli.py -x -q 2>&1 | tail -20
python -m pytest tests/ -x -q 2>&1 | tail -20
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
