# Implementation Plan: CLI Reporting Script (FLI-41)

## Issues
- FLI-41: CLI reporting script

## Research Context

### Existing Query Functions (ready to use)
All reporting logic already exists in `src/flight_watcher/queries.py`:
- `get_latest_snapshots(session, search_config_id, search_type=None, brand="LIGHT")` — deduped latest price per unique flight/brand/type combo
- `best_combinations(session, search_config_id, brand="LIGHT", limit=20)` — cheapest (outbound, return) pairs ranked by total price, grouped by `trip_days`
- `roundtrip_vs_oneway(session, search_config_id, brand="LIGHT")` — RT vs 2×OW comparison with savings_pct, recommendation, significant flag
- `price_trend_summary(session, search_config_id, brand="LIGHT", search_type=ONEWAY)` — per-date trend direction (↑/↓/→)

### CLI Conventions
- Typer-based modular CLI; each command group in `cli/<module>.py` exporting `app = typer.Typer()`
- Registered in `cli/__init__.py` via `app.add_typer(module.app, name="report")`
- Output via `typer.echo()`, status line at end (`[OK]`/`[FAIL]`)
- Fixed-width table headers, dashes separator, data rows
- Session via `with get_session() as session:`
- Errors: `typer.echo(..., err=True)` + `raise typer.Exit(1)`

### Test Conventions
- `typer.testing.CliRunner` with `runner.invoke(app, [...])`
- `make_session_mock()` helper returns `(get_session_mock, session_mock)` tuple
- Factory helpers: `_make_config()`, `_make_snapshot()` with sensible defaults
- Patch at module import path: `flight_watcher.cli.report.get_session`
- Class-based grouping: `TestReportCommand`

### Reference Implementations
- `scripts/best_combinations.py` — standalone argparse script calling `best_combinations()`
- `scripts/roundtrip_vs_oneway.py` — standalone argparse script calling `roundtrip_vs_oneway()`
These will be superseded by the CLI command.

## Decisions Made

1. **Single `report` command, not subcommands** — The issue specifies `python -m flight_watcher report <config_id>`. One command that prints all three sections (ranked flights, cheapest per stay, RT vs OW) in a single report. Rationale: a unified report is more useful than running 3 separate subcommands; the query functions are fast.

2. **Output format: three sections with headers** — The report prints:
   - Section 1: "Top Flights" — ranked by price, showing price/duration/fare/stops
   - Section 2: "Best by Stay Length" — cheapest total per trip_days bucket
   - Section 3: "Roundtrip vs One-Way" — comparison table with recommendation
   Each section has a header line and separator.

3. **`--brand` defaults to all brands** — Show all brands by default (LIGHT, STANDARD, FULL). `--brand LIGHT` filters to one. This is more useful for a report overview.

4. **`--top` defaults to 10** — Limits rows in Section 1 (top flights). Sections 2 and 3 show all results (they're naturally bounded by trip_days/date combos).

5. **Cheapest highlighting** — Mark the cheapest option per stay length with `*` prefix in Section 2. Simple, terminal-friendly.

6. **Config validation** — If `config_id` doesn't exist, print error and exit 1.

## Implementation Tasks

1. **Create `src/flight_watcher/cli/report.py`** — New CLI module with:
   - `app = typer.Typer(help="Flight price reports", no_args_is_help=True)`
   - `@app.command()` function `show(config_id: int, brand: Optional[str], top: int)`:
     - Validate config exists via `session.get(SearchConfig, config_id)`
     - Call `get_latest_snapshots()` for Section 1
     - Call `best_combinations()` for Section 2
     - Call `roundtrip_vs_oneway()` for Section 3
     - Format and print each section
     - End with `[OK]`

2. **Register in `src/flight_watcher/cli/__init__.py`** — Add `from flight_watcher.cli import report as report_module` and `app.add_typer(report_module.app, name="report")`

3. **Add tests in `tests/test_cli.py`** — `TestReport` class covering:
   - `test_report_show_prints_top_flights` — mocks `get_latest_snapshots`, verifies table output
   - `test_report_show_prints_best_combinations` — mocks `best_combinations`, verifies stay-length section
   - `test_report_show_prints_rt_vs_ow` — mocks `roundtrip_vs_oneway`, verifies comparison section
   - `test_report_show_invalid_config_exits_1` — config not found → exit 1
   - `test_report_show_brand_filter` — passes `--brand LIGHT`, verifies it's forwarded to query functions
   - `test_report_show_top_limits_rows` — `--top 5` limits output

## Output Format Spec

```
=== Flight Report: GRU → FOR (config #42) ===

── Top Flights ──────────────────────────────────────────────
  #  Date        Flight   Depart  Arrive  Dur   Stops  Brand     Price
  1  2026-06-21  LA3456   08:00   11:00   3h00  0      LIGHT   R$ 450.00
  2  2026-06-21  LA3457   14:00   17:30   3h30  0      STANDARD R$ 520.00
  ...
Showing top 10 of 45 results.

── Best by Stay Length ──────────────────────────────────────
 Days  Outbound     Return       Out Price   Ret Price   Total
 *  5  2026-06-21   2026-06-26   R$ 450.00   R$ 380.00   R$ 830.00
    7  2026-06-21   2026-06-28   R$ 450.00   R$ 420.00   R$ 870.00
   10  2026-06-22   2026-07-02   R$ 480.00   R$ 390.00   R$ 870.00

── Roundtrip vs One-Way ─────────────────────────────────────
 Outbound     Return       RT Total    OW Total    Savings  Rec
 2026-06-21   2026-06-26   R$ 900.00   R$ 830.00    -7.8%  2x one-way **
 2026-06-21   2026-06-28   R$ 850.00   R$ 870.00    +2.4%  roundtrip
** = significant (>5% savings)

[OK]
```

## Acceptance Criteria
- `python -m flight_watcher report <config_id>` prints ranked flights, best-by-stay, and RT vs OW sections
- `--brand LIGHT` filters all sections to that brand
- `--top 10` limits the top flights section
- Cheapest stay length is marked with `*`
- Invalid config_id prints error and exits 1
- All tests pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-41-cli-report
python -m pytest tests/ -x -q
python -m flight_watcher report --help
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-41`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- Deleting the scripts/ reference implementations (separate cleanup task)
