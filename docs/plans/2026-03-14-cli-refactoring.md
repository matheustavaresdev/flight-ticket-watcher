# Implementation Plan: CLI Validator Extraction & Scraper Decoupling

## Issues
- FLI-51: search commands missing IATA and date input validation
- FLI-52: decouple latam_scraper.py from typer — move print_offers to cli layer

## Research Context

### Current State
- `cli/config.py` has `_parse_iata()` (lines 15-21) and `_parse_date()` (lines 24-28) — private helpers that validate IATA codes (3 uppercase alpha) and dates (YYYY-MM-DD ISO format). Both raise `typer.BadParameter`.
- `cli/search.py` accepts `--origin`, `--dest`, `--out`, `--in` as raw strings with no validation — just does `.upper()` on IATA codes.
- `latam_scraper.py` imports `typer` (line 9) solely for `typer.echo()` inside `print_offers()` (lines 373-389). This couples a core scraping module to the CLI framework.
- `src/flight_watcher/display.py` already exists with `print_results()` for fast-flights output — uses `typer.echo()`. This is the established display utility module.
- No `cli/validators.py` exists yet.

### Test Coverage
- `tests/test_cli.py` has `TestConfigAdd` (lines 56-103) testing IATA/date validation.
- `TestSearchCommands.test_search_latam_invokes_scraper()` (line 282) mocks `print_offers` from `latam_scraper`.

## Decisions Made

1. **Validators location:** `cli/validators.py` — keeps them in the CLI layer where `typer.BadParameter` is appropriate. Functions become public (drop `_` prefix) since they're now a shared module.

2. **`print_offers()` destination:** `src/flight_watcher/display.py` — the existing display utility module. It already uses `typer.echo()` and has `print_results()` for fast-flights. Consolidating display functions here follows the established pattern. The key goal (removing typer from `latam_scraper.py`) is achieved.

3. **Validator application style:** Call validators explicitly inside command functions (same pattern as `config.py` today), not via Typer `callback` parameter. Keeps it simple and consistent with existing code.

## Implementation Tasks

1. **Create `cli/validators.py`** — new file
   - Move `_parse_iata()` → `parse_iata()` and `_parse_date()` → `parse_date()` (public API)
   - Imports: `datetime.date`, `typer`

2. **Update `cli/config.py`** — modify
   - Remove `_parse_iata()` and `_parse_date()` function definitions
   - Add `from flight_watcher.cli.validators import parse_iata, parse_date`
   - Update call sites: `_parse_iata(...)` → `parse_iata(...)`, `_parse_date(...)` → `parse_date(...)`

3. **Update `cli/search.py`** — modify
   - Add `from flight_watcher.cli.validators import parse_iata, parse_date`
   - In `search_latam()`: validate `origin`, `dest` with `parse_iata()` and `out`/`inbound` with `parse_date()` before passing to scraper
   - In `search_fast()`: same validation for its IATA/date arguments
   - Update `print_offers` import: change from `flight_watcher.latam_scraper` to `flight_watcher.display`

4. **Move `print_offers()` to `display.py`** — modify `src/flight_watcher/display.py`
   - Copy `print_offers()` function from `latam_scraper.py`
   - Ensure `typer` import exists (it already does)

5. **Remove `print_offers()` from `latam_scraper.py`** — modify
   - Delete the `print_offers()` function
   - Remove the `import typer` line (verify no other usage remains)

6. **Update tests** — modify `tests/test_cli.py`
   - Update mock path for `print_offers`: `flight_watcher.latam_scraper.print_offers` → `flight_watcher.display.print_offers`
   - Add validation tests for `search latam` and `search fast` commands (invalid IATA, invalid date → error exit)

## Acceptance Criteria
- `_parse_iata()` and `_parse_date()` extracted to `cli/validators.py` and reused in both `config.py` and `search.py`
- `search latam --origin GRUU` fails with a clear IATA validation error
- `search latam --out 2026/04/12` fails with a clear date validation error
- Same validations work for `search fast`
- `latam_scraper.py` has zero `typer` imports
- `print_offers()` lives in `display.py` and works identically
- All existing tests pass
- New tests cover search command validation

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-51+52-cli-refactoring
python -m pytest tests/ -v
python -m flight_watcher search latam --origin GRUU --dest GRU --out 2026-04-01 2>&1 | head -5  # should show IATA error
python -m flight_watcher search latam --origin GRU --dest CGH --out 2026/04/01 2>&1 | head -5  # should show date error
grep -c "import typer" src/flight_watcher/latam_scraper.py  # should be 0
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-51` and `Closes FLI-52` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Moving `display.py` into the `cli/` package (separate concern)
