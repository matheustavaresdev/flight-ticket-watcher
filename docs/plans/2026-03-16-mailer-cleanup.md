# Implementation Plan: Mailer Cleanup (FLI-129, FLI-131, FLI-132, FLI-133)

## Issues
- FLI-129: test: add unauthenticated SMTP path test to test_mailer.py
- FLI-131: chore: remove unused ALERT_THRESHOLD_BRL env var from mailer.py
- FLI-132: docs: document is_email_configured() auth assumptions in mailer.py
- FLI-133: fix: handle partial 7-day stats in _build_alert_html (None rendered as string)

## Research Context

**Codebase:** All changes are in `src/flight_watcher/mailer.py`, `tests/test_mailer.py`, `.env.example`, and `docker-compose.yml`. The mailer module is self-contained (stdlib only). Tests use `unittest.TestCase` with `@patch` decorators and `MagicMock` for SMTP.

**Key patterns:**
- Module-level constant `MAILER_MODULE = "flight_watcher.mailer"` for patch targets
- `_SAMPLE_ALERT` and `_SMTP_ENV` dicts as test fixtures
- SMTP mocked via `@patch(f"{MAILER_MODULE}.smtplib.SMTP")` with `__enter__`/`__exit__` MagicMocks
- Existing tests at `test_send_price_alert_email_smtp_error` already patch empty credentials (`SMTP_USERNAME=""`, `SMTP_PASSWORD=""`) but don't assert on login

**ALERT_THRESHOLD_BRL references (4 files):**
- `src/flight_watcher/mailer.py:15` — loaded but never used
- `.env.example:29` — documented but unused
- `docker-compose.yml:38` — passed to container but unused
- `docs/plans/2026-03-15-alert-foundation.md` — mentioned in plan (leave as-is, historical doc)

**None rendering bug:** `_build_alert_html` lines 49-56 — the `any(... is not None)` guard triggers on 1+ non-None values, but the f-string renders remaining None values as literal "None" in the HTML.

## Decisions Made

- **FLI-129:** New test method `test_send_price_alert_email_no_auth` in `TestSendPriceAlertEmail` class. Follows the exact same decorator pattern as existing tests with empty SMTP_USERNAME/SMTP_PASSWORD. Asserts `mock_server.login.assert_not_called()`.
- **FLI-131:** Remove `ALERT_THRESHOLD_BRL` from mailer.py, .env.example, and docker-compose.yml. Leave plan doc references as-is (historical).
- **FLI-132:** Add inline comment above `is_email_configured()` explaining that auth credentials are intentionally not checked — the function validates transport config only, and unauthenticated SMTP relays are supported by skipping login when credentials are empty.
- **FLI-133:** Use `"N/A"` fallback for None values in the 7-day stats f-string. Format: `f"{avg_7d if avg_7d is not None else 'N/A'}"` for each stat.

## Implementation Tasks

1. **FLI-133: Fix None rendering in _build_alert_html** — `src/flight_watcher/mailer.py:51-54`
   - Replace direct f-string interpolation of `avg_7d`, `high_7d`, `low_7d` with conditional expressions that substitute `"N/A"` for None values
   - Add test `test_build_alert_html_partial_7d_stats` to `TestBuildAlertHtml` class in `tests/test_mailer.py` — pass alert_data with only `avg_7d` set, assert "N/A" appears for missing stats and no literal "None" in output
   - Add test `test_build_alert_html_all_7d_stats` — pass all three stats, assert all values appear

2. **FLI-131: Remove ALERT_THRESHOLD_BRL** — 3 files
   - Delete line `ALERT_THRESHOLD_BRL = os.environ.get("ALERT_THRESHOLD_BRL", "")` from `src/flight_watcher/mailer.py:15`
   - Delete line `ALERT_THRESHOLD_BRL=` from `.env.example:29`
   - Delete line `ALERT_THRESHOLD_BRL: ${ALERT_THRESHOLD_BRL:-}` from `docker-compose.yml:38`

3. **FLI-132: Document is_email_configured() auth assumptions** — `src/flight_watcher/mailer.py:18-19`
   - Add inline comment above the function explaining: checks transport config only (host, from, to); auth credentials are intentionally excluded because unauthenticated SMTP relays are supported — login is skipped when SMTP_USERNAME and SMTP_PASSWORD are both empty

4. **FLI-129: Add unauthenticated SMTP test** — `tests/test_mailer.py`
   - Add `test_send_price_alert_email_no_auth` method to `TestSendPriceAlertEmail` class
   - Use same decorator pattern as existing tests, with `SMTP_USERNAME=""` and `SMTP_PASSWORD=""`
   - Assert: `result is True`, `mock_server.starttls.assert_called_once()`, `mock_server.login.assert_not_called()`, `mock_server.send_message.assert_called_once()`

## Acceptance Criteria
- Unauthenticated SMTP path has a dedicated passing test (FLI-129)
- ALERT_THRESHOLD_BRL removed from mailer.py, .env.example, docker-compose.yml (FLI-131)
- is_email_configured() has clear inline comment about auth design choice (FLI-132)
- Partial 7-day stats render "N/A" instead of "None" in alert HTML (FLI-133)
- All existing tests continue to pass

## Verification
```bash
cd /Users/matheus/TavApps/Personal/flight-ticket-watcher/.worktrees/FLI-129+131+132+133-mailer-cleanup
python -m pytest tests/test_mailer.py -v
python -m pytest tests/ -v
grep -r "ALERT_THRESHOLD_BRL" src/ .env.example docker-compose.yml  # should return nothing
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with all `Closes FLI-129`, `Closes FLI-131`, `Closes FLI-132`, `Closes FLI-133` lines
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
