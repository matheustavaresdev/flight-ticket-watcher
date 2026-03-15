# Implementation Plan: Per-Date Commit to Preserve Scan Progress

## Issues
- FLI-96: Consider per-date commit to preserve scan progress across transient failures

## Research Context

### Current Problem
`run_scan()` wraps the entire date iteration loop in a single `with get_session() as session:` block. Each date's cursor update uses `session.flush()`, which makes changes visible in-memory but does NOT persist to disk. When `SearchFailedError` escapes the loop, `get_session()`'s except block calls `session.rollback()`, discarding ALL flushed progress — including snapshots and cursor from dates that succeeded before the failure.

**Example:** Scanning 10 dates. Dates 1-4 succeed (snapshots stored, cursor flushed to date 4). Date 5 fails with RATE_LIMITED. Rollback wipes everything. On retry, the run rescans dates 1-4 again.

### Key Code Locations
- `orchestrator.py:228-232` — cursor update + flush (the change point)
- `orchestrator.py:244-248` — exception handler sets FAILED status (needs commit before raise)
- `db.py:55-71` — `get_session()` context manager (commit on exit, rollback on exception)

### Session/Transaction Semantics
- `session.flush()` → writes to DB buffer, visible in session, NOT durable
- `session.commit()` → durable write, survives rollback
- After `session.commit()`, a subsequent `session.rollback()` only undoes uncommitted changes
- `get_session()` auto-commits on normal exit, auto-rollbacks on exception

### Approach
Replace `session.flush()` with `session.commit()` in the date loop. Add `session.commit()` in the except block so the FAILED status is also persisted (otherwise the auto-rollback in `get_session()` would discard it).

This is the minimal change. No need for savepoints, nested transactions, or restructuring `get_session()`.

## Decisions Made

1. **`session.commit()` per date, not savepoints/nested transactions** — Savepoints add complexity. The date loop already has clear commit points. A simple `flush→commit` swap achieves the goal with zero new abstractions.

2. **Commit FAILED status in the except block** — After per-date commits, the `get_session()` rollback would only undo the FAILED status marker (since snapshots/cursor are already committed). Adding `session.commit()` before `raise` ensures the failure state is also durable.

3. **No changes to `get_session()`** — The context manager's commit/rollback becomes effectively a no-op (nothing pending on normal exit; nothing pending after except-block commit on failure). This is fine — it's still a valid safety net.

## Implementation Tasks

1. **Replace `session.flush()` with `session.commit()` in the date loop** — affects `src/flight_watcher/orchestrator.py:232`
   - Change `session.flush()` to `session.commit()`
   - Update the NOTE comment (lines 229-231) to reflect the new behavior

2. **Add `session.commit()` in the except block** — affects `src/flight_watcher/orchestrator.py:244-248`
   - After setting `scan_run.status = ScanStatus.FAILED` and `scan_run.error_message`, add `session.commit()` before `raise`
   - This ensures the FAILED status survives the `get_session()` rollback

3. **Add test: partial progress preserved on mid-scan failure** — affects `tests/test_orchestrator.py`
   - New test in `TestFailureAwareCursorAdvancement`: scan with 3 dates where dates 1-2 succeed and date 3 fails (RATE_LIMITED). Verify:
     - `session.commit()` was called after each successful date (2 times for dates, 1 time for failure = 3 total)
     - `scan_run.last_successful_date` equals date 2 (the last successful)
     - `scan_run.status == ScanStatus.FAILED`
   - This is the core behavior change — previously cursor would be lost on rollback

4. **Update existing test that verifies flush behavior** — affects `tests/test_orchestrator.py`
   - `test_run_scan_updates_cursor_after_each_date` currently verifies cursor advancement. It should still pass since the cursor update logic is unchanged — only the persistence mechanism changed (commit vs flush).
   - Verify `session.commit` is called instead of/in addition to `session.flush` in relevant assertions, if any tests assert on `session.flush.call_count`.

## Acceptance Criteria
- Scan progress (snapshots + cursor) from completed dates survives a mid-scan failure
- Failed status is persisted even when exception propagates through `get_session()`
- Cursor resumption still works correctly (find today's FAILED run, resume from last_successful_date)
- All existing tests pass (no behavioral regression for success path, single-date failures, or cursor resumption)
- New test covers the partial-progress scenario

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-96-per-date-commit
python -m pytest tests/test_orchestrator.py -v
python -m pytest tests/ -v
python -m pyright src/flight_watcher/orchestrator.py
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-96`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring `get_session()` or adding savepoint support
- Adding sub-transaction abstractions
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
