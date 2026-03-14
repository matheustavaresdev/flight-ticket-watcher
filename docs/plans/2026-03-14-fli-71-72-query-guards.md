# Implementation Plan: best_combinations() Query Guards

## Issues
- FLI-71: best_combinations() lacks currency-consistency guard
- FLI-72: best_combinations() signature default changed to None — restore limit=20

## Research Context

### Codebase Patterns
- `best_combinations()` is at `src/flight_watcher/queries.py:82-139`
- `roundtrip_vs_oneway()` at `queries.py:142-226` already has the currency guard pattern (lines 198-201):
  ```python
  currencies = {rt_out_currency, rt_ret_currency, ow_out_currency, ow_ret_currency}
  if len(currencies) > 1:
      continue
  ```
- In `best_combinations()`, the cross-join loop (lines 121-137) currently discards the return leg currency with `_`:
  ```python
  for out_date, (out_price, currency) in cheapest_out.items():
      for ret_date, (ret_price, _) in cheapest_ret.items():
  ```

### Callers of best_combinations()
1. `src/flight_watcher/cli/report.py:74` — passes `limit=None` explicitly
2. `scripts/best_combinations.py:27` — passes argparse limit (default=20)
3. `tests/test_queries.py` — multiple test calls, rely on default
4. `tests/test_cli.py:742` — asserts `limit=None` was passed

### Architecture Conventions
- Query functions don't log or raise exceptions — return empty on invalid state
- Currency is `str` (ISO 4217, 3 chars) on `PriceSnapshot.currency`
- Use `Decimal` for monetary calculations
- Guards silently skip invalid rows (continue), don't raise

## Decisions Made

1. **FLI-71 guard pattern:** Use the same set-based currency check from `roundtrip_vs_oneway()`. Capture return currency instead of discarding with `_`, compare `{out_currency, ret_currency}`, `continue` if `len > 1`.

2. **FLI-72 default restoration:** Restore signature to `limit: int = 20`. The CLI report caller (`report.py:74`) wants unlimited results, so it should pass `limit=0` or a large sentinel — but looking at the function body, `None` means "no limit" via `if limit is not None: ... [:limit]`. Keep `Optional[int] = 20` so callers can still pass `None` for unlimited. The report caller already passes `limit=None` which is correct. The fix is just the default value: `limit: int | None = 20` instead of `limit: int | None = None`.

3. **Test update:** `test_cli.py:742` asserts `limit=None` — this is correct since `report.py` explicitly passes `limit=None`. No change needed there.

## Implementation Tasks

1. **FLI-71: Add currency guard to `best_combinations()`** — `src/flight_watcher/queries.py`
   - Capture return currency: change `(ret_price, _)` to `(ret_price, ret_currency)`
   - Add guard before computing `total_price`:
     ```python
     if currency != ret_currency:
         continue
     ```
   - This is simpler than the `roundtrip_vs_oneway` pattern (only 2 currencies, not 4)

2. **FLI-72: Restore default `limit=20`** — `src/flight_watcher/queries.py`
   - Change signature from `limit: Optional[int] = None` to `limit: Optional[int] = 20`
   - No caller changes needed — `report.py` already passes `limit=None` explicitly
   - No test changes needed — `test_cli.py` asserts `limit=None` which matches report.py behavior

3. **Add test for currency mismatch** — `tests/test_queries.py`
   - Add a test case to `TestBestCombinations` that creates snapshots with different currencies for outbound vs return legs
   - Assert that mismatched-currency combinations are excluded from results

## Acceptance Criteria
- `best_combinations()` skips combinations where outbound and return currencies differ
- `best_combinations()` defaults to returning 20 results when `limit` is not specified
- Callers passing `limit=None` still get unlimited results
- Existing tests continue to pass
- New test covers currency mismatch scenario

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-71+72-query-guards
python -m pytest tests/test_queries.py -v
python -m pytest tests/test_cli.py -v
python -m pytest tests/ -v
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-71` and `Closes FLI-72` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
