# Implementation Plan: Price Drop Detection Engine (FLI-106)

## Issues
- FLI-106: Price drop detection engine

## Research Context

### Existing Infrastructure
All building blocks are already in place:
- **PriceAlert model** (`models.py:210-244`): Has `alert_type` (NEW_LOW | THRESHOLD), `previous_low_price`, `new_price`, `price_drop_abs`, `sent_to`, `sent_at`, dedup index on `(origin, destination, flight_date, brand)`.
- **PriceSnapshot model** (`models.py:159-207`): Stores per-flight prices with `origin`, `destination`, `flight_date`, `brand`, `price`, `flight_code` (airline). Indexed on route+date and route+date+brand.
- **price_history()** (`queries.py:240-284`): Returns `PriceHistoryResult` with `min_price`, `min_price_seen_at` for a given route+date+brand. Already filters by `ScanStatus.COMPLETED`.
- **send_price_alert_email()** (`mailer.py:97-136`): Accepts `alert_data` dict with keys: `origin`, `destination`, `flight_date`, `airline`, `brand`, `new_price`, `previous_low_price`, `price_drop_abs`, `alert_type`, optional `avg_7d`/`high_7d`/`low_7d`. Gracefully no-ops if SMTP not configured.
- **ALERT_THRESHOLD_BRL** (`mailer.py:15`): Already read from env at module level.
- **Orchestrator** (`orchestrator.py:127-252`): `run_scan()` stores snapshots per-date, marks scan COMPLETED, then returns. The detection hook goes after scan completion.

### Codebase Patterns
- Module-level `logger = logging.getLogger(__name__)`
- SQLAlchemy 2.0 Mapped[] style, `Decimal` for all prices
- Session via `get_session()` context manager
- Tests: `_make_*()` factory helpers, `MagicMock` sessions, `patch.dict(os.environ, ...)`, no conftest.py

## Decisions Made

1. **New module `src/flight_watcher/alerts.py`** for the detection engine. Keeps orchestrator focused on scanning, alerts module focused on detection + notification. Clean separation.

2. **Detection runs after scan completion** — called from `run_scan()` after `scan_run.status = ScanStatus.COMPLETED` is committed, before the roundtrip phase. This ensures all snapshots for the scan are persisted and the scan is marked complete before alerting.

3. **Grouping key for detection: `(origin, destination, flight_date, brand)`** — matches the PriceAlert dedup index. The `airline` field in PriceAlert will store the `flight_code` from the cheapest snapshot (the one triggering the alert), but is NOT part of the dedup key. This avoids duplicate alerts when the same route has multiple airlines.

4. **Historical min query**: For each unique `(origin, dest, flight_date, brand)` in the current scan's snapshots, query `MIN(price)` from `price_snapshots` where `scan_run.status = COMPLETED` and `scan_run_id != current_scan_run_id` (exclude current run to compare against *previous* history). If no prior history exists, skip (first scan for this route — nothing to compare against).

5. **Dedup logic**: For each candidate alert, query the most recent `PriceAlert` for that `(origin, dest, flight_date, brand)`. Only create alert if `new_price < last_alert.new_price` (or no prior alert exists for that route+date).

6. **Two alert types fired independently**:
   - **NEW_LOW**: current cheapest price for route+date+brand < historical min price across all previous scans
   - **THRESHOLD**: current cheapest price < `ALERT_THRESHOLD_BRL` (env var). Only fires if threshold is configured AND new price is below it AND dedup passes.
   - A single snapshot can trigger both alert types (creates two PriceAlert rows + two emails).

7. **Error handling**: Alert detection failures are logged but don't fail the scan. The scan already completed successfully — alerting is best-effort.

## Implementation Tasks

### Task 1: Create `src/flight_watcher/alerts.py` — detection engine

New module with these functions:

```python
def detect_price_drops(session: Session, scan_run_id: int, search_config_id: int) -> list[PriceAlert]:
    """Main entry point. Compares current scan's snapshots against history.
    Returns list of PriceAlert records created."""
```

Internal flow:
1. Get all snapshots for `scan_run_id` from the DB
2. Group by `(origin, destination, flight_date, brand)`, keep cheapest price per group
3. For each group:
   a. Query historical min price (all completed scans EXCEPT current)
   b. Query last alert for dedup
   c. Determine if NEW_LOW alert qualifies (cheapest < historical_min AND (no prior alert OR cheapest < last_alert.new_price))
   d. Determine if THRESHOLD alert qualifies (ALERT_THRESHOLD_BRL set AND cheapest < threshold AND (no prior alert of type THRESHOLD OR cheapest < last_threshold_alert.new_price))
   e. Create PriceAlert records, add to session
4. Flush to get IDs, return created alerts

Helper functions:
```python
def _get_historical_min(session, origin, dest, flight_date, brand, exclude_scan_run_id) -> Decimal | None:
    """MIN(price) across all completed scans except the given one."""

def _get_last_alert(session, origin, dest, flight_date, brand, alert_type) -> PriceAlert | None:
    """Most recent PriceAlert for route+date+brand+type."""

def _get_threshold_brl() -> Decimal | None:
    """Parse ALERT_THRESHOLD_BRL env var. Returns None if not set or invalid."""
```

Affects: `src/flight_watcher/alerts.py` (new file)

### Task 2: Create `src/flight_watcher/alert_sender.py` — notification dispatch

Thin wrapper that takes PriceAlert records and sends emails:

```python
def send_alerts(session: Session, alerts: list[PriceAlert]) -> int:
    """Send email for each alert. Updates sent_to/sent_at on success. Returns count sent."""
```

For each alert:
1. Build `alert_data` dict matching mailer's expected shape
2. Call `send_price_alert_email(alert_data)`
3. On success, update `alert.sent_to = ALERT_EMAIL_TO`, `alert.sent_at = now()`
4. Commit after all alerts processed

Affects: `src/flight_watcher/alert_sender.py` (new file)

### Task 3: Integrate into orchestrator

In `orchestrator.py`, after the scan is marked COMPLETED and committed (line ~243), call the detection engine:

```python
# After scan_run.status = ScanStatus.COMPLETED commit
try:
    from flight_watcher.alerts import detect_price_drops
    from flight_watcher.alert_sender import send_alerts
    alerts = detect_price_drops(session, scan_run.id, config["id"])
    if alerts:
        session.commit()  # persist PriceAlert records
        sent = send_alerts(session, alerts)
        logger.info("Scan %d: %d alert(s) created, %d sent", scan_run.id, len(alerts), sent)
except Exception:
    logger.exception("Alert detection failed for scan %d (non-fatal)", scan_run.id)
```

Affects: `src/flight_watcher/orchestrator.py`

### Task 4: Create `tests/test_alerts.py`

Tests for the detection engine:

1. **test_no_history_no_alerts** — first scan for a route, no prior snapshots → no alerts
2. **test_new_low_triggered** — price lower than historical min → NEW_LOW alert created
3. **test_new_low_not_triggered_price_higher** — price higher than historical min → no alert
4. **test_threshold_triggered** — price below ALERT_THRESHOLD_BRL → THRESHOLD alert created
5. **test_threshold_not_set_no_alert** — ALERT_THRESHOLD_BRL not in env → no THRESHOLD alerts
6. **test_dedup_skips_when_already_alerted** — last alert's new_price <= current price → skip
7. **test_dedup_allows_lower_price** — last alert's new_price > current price → new alert
8. **test_both_alert_types_fire** — price triggers both NEW_LOW and THRESHOLD → 2 alerts
9. **test_multiple_routes_in_scan** — scan with multiple route+date groups → correct per-group detection
10. **test_get_threshold_brl_parsing** — valid/invalid/missing env var scenarios

Affects: `tests/test_alerts.py` (new file)

### Task 5: Create `tests/test_alert_sender.py`

Tests for notification dispatch:

1. **test_send_alerts_calls_mailer** — verifies send_price_alert_email called per alert
2. **test_send_alerts_updates_sent_fields** — sent_to and sent_at populated on success
3. **test_send_alerts_handles_mailer_failure** — mailer returns False → sent fields stay None, continues to next
4. **test_send_alerts_empty_list** — no alerts → returns 0, no mailer calls

Affects: `tests/test_alert_sender.py` (new file)

### Task 6: Add orchestrator integration test

In `tests/test_orchestrator.py`, add test:

1. **test_run_scan_calls_detect_price_drops_on_completion** — mock detect_price_drops and send_alerts, verify called after COMPLETED
2. **test_run_scan_alert_failure_does_not_fail_scan** — detect_price_drops raises → scan still succeeds

Affects: `tests/test_orchestrator.py`

## Acceptance Criteria
- After each completed scan, prices from new snapshots are compared against historical minimums per (origin, dest, flight_date, brand)
- Alert triggered when: (A) price < all-time historical min (NEW_LOW), or (B) price < ALERT_THRESHOLD_BRL (THRESHOLD)
- Dedup: only alert if new price < last alerted price for that route+date+brand+alert_type
- PriceAlert records persisted with correct fields
- Email sent via existing mailer (graceful skip if not configured)
- Alert failures don't crash the scan
- All tests pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-106-price-drop-engine
pytest tests/test_alerts.py tests/test_alert_sender.py tests/test_orchestrator.py -v
pytest --tb=short
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-106` line
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
- CLI commands for alerts (separate ticket)
- Web UI for alerts (separate ticket)
