# Implementation Plan: Alert Foundation (Configurable Scanning + Email Alerts)

## Issues
- FLI-104: Make scan interval configurable (default hourly)
- FLI-105: Add price_alerts table + Alembic migration
- FLI-107: SMTP email sender module
- FLI-108: Add SMTP config to docker-compose and .env.example

## Research Context

### Scheduler (FLI-104)
- `src/flight_watcher/scheduler.py` uses APScheduler 3.x `BackgroundScheduler` with PostgreSQL `SQLAlchemyJobStore`
- Current main scan: `cron` trigger at `SCAN_HOUR_UTC` (daily), registered in `register_scan_job()` line 95
- Retry jobs already use `interval` trigger with `RETRY_INTERVAL_MINUTES` (default 60)
- Env vars loaded at module level: `SCAN_HOUR_UTC`, `RETRY_MAX_ATTEMPTS`, `RETRY_INTERVAL_MINUTES`
- docker-compose already passes `SCAN_SCHEDULE` (not used in code yet — `.env.example` only has `SCAN_HOUR_UTC`)

### Database (FLI-105)
- Models in `src/flight_watcher/models.py` — SQLAlchemy 2.0 `Mapped[]` + `mapped_column()` pattern
- Enums: `native_enum=False` with `values_callable=lambda x: [e.value for e in x]`
- Timestamps: `DateTime(timezone=True)` with `server_default=func.now()`
- Prices: `Numeric(10, 2)`
- Latest alembic revision: `b5c6d7e8` (retry columns)
- Migration files in `alembic/versions/`, format: `{rev}_{slug}.py`

### Email (FLI-107)
- No existing email/notification infrastructure
- Flat module structure: `src/flight_watcher/<module>.py`
- Singleton pattern: `_var = None`, `get_var()` factory (see `db.py`, `scheduler.py`)
- Logging: `logger = logging.getLogger(__name__)`
- Python stdlib `smtplib` + `email` sufficient — no external deps needed

### Docker/Env (FLI-108)
- `.env.example` has all env vars with comments, no real values
- `docker-compose.yml` scanner service passes env vars via `${VAR}` interpolation
- No existing SMTP vars

### Test Patterns
- Tests in `tests/test_<module>.py`, pytest + unittest.TestCase hybrid
- No conftest.py — inline `_make_*()` factory helpers per file
- Module path constant: `MODULE = "flight_watcher.module_name"`
- Session mocking: `MagicMock()` with `execute().scalars().all()` chain
- Context manager mocking for `get_session()`: custom `make_session_mock()` helper
- Model tests: inspect `__table__.columns`, `__table__.indexes`, FK references
- Env tests: `patch.dict(os.environ, {...}, clear=True)`
- Scheduler tests: `unittest.TestCase` with setUp/tearDown resetting `sched_mod._scheduler = None`

## Decisions Made

1. **Scan interval approach**: Replace the `cron` trigger with an `interval` trigger using new `SCAN_INTERVAL_MINUTES` env var (default 60). This is simpler than cron and matches the issue description. Remove `SCAN_HOUR_UTC` from code and `.env.example`. The `SCAN_SCHEDULE` var already in docker-compose.yml is unused — replace it with `SCAN_INTERVAL_MINUTES`.

2. **AlertType enum**: `new_low` (price dropped below any previously seen price) and `threshold` (price dropped below user-configured threshold). Matches issue description exactly.

3. **price_alerts table schema**: Follow the issue description column list exactly. FK to `search_configs`. Index on `(origin, destination, flight_date, brand)` for dedup lookups as specified.

4. **Email module**: Single file `src/flight_watcher/mailer.py` with `send_price_alert_email()` function. Uses stdlib `smtplib` + `email.mime`. No singleton needed — just a stateless function that reads config from env. HTML template built inline (no Jinja2 dependency for a single template).

5. **Graceful degradation**: If SMTP env vars are not set, log a warning and skip email sending (don't crash the scanner). This lets the scanner run without email configured.

## Implementation Tasks

### Task 1: FLI-108 — Add SMTP + scan interval config to .env.example and docker-compose
Affects: `.env.example`, `docker-compose.yml`

1a. Add to `.env.example`:
```
# Scan interval
SCAN_INTERVAL_MINUTES=60

# Email alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=
ALERT_EMAIL_TO=
ALERT_THRESHOLD_BRL=
```

1b. Replace `SCAN_HOUR_UTC=0` with `SCAN_INTERVAL_MINUTES=60` in `.env.example`.

1c. Update `docker-compose.yml` scanner environment section:
- Replace `SCAN_SCHEDULE: ${SCAN_SCHEDULE}` with `SCAN_INTERVAL_MINUTES: ${SCAN_INTERVAL_MINUTES:-60}`
- Add: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `ALERT_EMAIL_TO`, `ALERT_THRESHOLD_BRL`

### Task 2: FLI-104 — Make scan interval configurable
Affects: `src/flight_watcher/scheduler.py`, `tests/test_scheduler.py`

2a. In `scheduler.py`:
- Replace `SCAN_HOUR_UTC` with `SCAN_INTERVAL_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "60"))`
- Change `register_scan_job()` from `cron` trigger to `interval` trigger:
  ```python
  scheduler.add_job(
      run_all_scans,
      trigger="interval",
      minutes=SCAN_INTERVAL_MINUTES,
      id="scheduled_scan",
      replace_existing=True,
      max_instances=1,
      misfire_grace_time=300,
  )
  ```
- Remove jitter (interval jobs don't need it — natural drift handles this)
- Rename job id from `daily_scan` to `scheduled_scan` (it's no longer daily)
- Update log message

2b. In `tests/test_scheduler.py`:
- Update tests for `register_scan_job` to expect `interval` trigger instead of `cron`
- Test that `SCAN_INTERVAL_MINUTES` env var is respected
- Test default value (60)

### Task 3: FLI-105 — Add price_alerts table + Alembic migration
Affects: `src/flight_watcher/models.py`, `alembic/versions/`

3a. Add `AlertType` enum to `models.py`:
```python
class AlertType(enum.Enum):
    NEW_LOW = "new_low"
    THRESHOLD = "threshold"
```

3b. Add `PriceAlert` model to `models.py`:
```python
class PriceAlert(Base):
    __tablename__ = "price_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    search_config_id: Mapped[int] = mapped_column(
        ForeignKey("search_configs.id"), nullable=False
    )
    origin: Mapped[str] = mapped_column(String(3), nullable=False)
    destination: Mapped[str] = mapped_column(String(3), nullable=False)
    flight_date: Mapped[date] = mapped_column(Date, nullable=False)
    airline: Mapped[str] = mapped_column(String(30), nullable=False)
    brand: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_low_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    price_drop_abs: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    alert_type: Mapped[AlertType] = mapped_column(
        Enum(AlertType, native_enum=False,
             values_callable=lambda x: [e.value for e in x],
             validate_strings=True),
        nullable=False,
    )
    sent_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    search_config: Mapped["SearchConfig"] = relationship()

    __table_args__ = (
        Index("ix_price_alerts_route_date", "origin", "destination", "flight_date", "brand"),
    )
```

3c. Add relationship back-ref on `SearchConfig`:
```python
price_alerts: Mapped[list["PriceAlert"]] = relationship(back_populates="search_config")
```

3d. Create Alembic migration `alembic/versions/c3d4e5f6_add_price_alerts_table.py`:
- `revision = "c3d4e5f6"`, `down_revision = "b5c6d7e8"`
- `upgrade()`: `op.create_table("price_alerts", ...)` + `op.create_index(...)`
- `downgrade()`: `op.drop_index(...)` + `op.drop_table("price_alerts")`

3e. Add tests in `tests/test_models.py`:
- `TestPriceAlert`: verify tablename, columns, indexes, FK reference, AlertType enum values
- Follow existing `TestSearchConfig`/`TestPriceSnapshot` patterns exactly

### Task 4: FLI-107 — SMTP email sender module
Affects: `src/flight_watcher/mailer.py` (new), `tests/test_mailer.py` (new)

4a. Create `src/flight_watcher/mailer.py`:
- Module-level config from env:
  ```python
  SMTP_HOST = os.environ.get("SMTP_HOST", "")
  SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
  SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
  SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
  SMTP_FROM = os.environ.get("SMTP_FROM", "")
  ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
  ALERT_THRESHOLD_BRL = os.environ.get("ALERT_THRESHOLD_BRL", "")
  ```
- `def is_email_configured() -> bool`: returns True if SMTP_HOST and SMTP_FROM and ALERT_EMAIL_TO are all non-empty
- `def _build_google_flights_link(origin, destination, flight_date) -> str`: constructs a Google Flights search URL
- `def _build_alert_html(alert_data: dict) -> str`: returns HTML email body with:
  - Route (origin → destination)
  - Flight date
  - New price vs previous low (highlighted)
  - Price drop amount
  - 7-day stats if provided (avg/high/low)
  - Google Flights search link
  - Simple, inline-CSS HTML (email-client compatible)
- `def send_price_alert_email(alert_data: dict) -> bool`:
  - If not `is_email_configured()`, log warning, return False
  - Build `MIMEMultipart("alternative")` with HTML part
  - Connect via `smtplib.SMTP(SMTP_HOST, SMTP_PORT)`
  - `starttls()`, `login(SMTP_USERNAME, SMTP_PASSWORD)`, `send_message(msg)`
  - Return True on success, log + return False on exception
  - `alert_data` dict keys: `origin`, `destination`, `flight_date`, `airline`, `brand`, `new_price`, `previous_low_price`, `price_drop_abs`, `alert_type`, `avg_7d` (optional), `high_7d` (optional), `low_7d` (optional)

4b. Create `tests/test_mailer.py`:
- `MAILER_MODULE = "flight_watcher.mailer"`
- `test_is_email_configured_true`: patch env with all required vars set
- `test_is_email_configured_false_missing_host`: patch env with SMTP_HOST empty
- `test_send_price_alert_email_success`: mock `smtplib.SMTP`, verify `starttls()`, `login()`, `send_message()` called
- `test_send_price_alert_email_not_configured`: mock env with empty SMTP_HOST, verify returns False and logs warning
- `test_send_price_alert_email_smtp_error`: mock SMTP to raise `smtplib.SMTPException`, verify returns False and logs error
- `test_build_alert_html_contains_key_info`: verify HTML contains route, price, date
- `test_build_google_flights_link`: verify URL format

## Acceptance Criteria
- [ ] `SCAN_INTERVAL_MINUTES` env var controls scan frequency (default 60 minutes)
- [ ] `price_alerts` table exists with all specified columns and route+date index
- [ ] Alembic migration creates/drops the table cleanly
- [ ] `send_price_alert_email()` sends HTML email via Gmail SMTP with TLS
- [ ] Email template includes: route, date, new price vs previous low, Google Flights link
- [ ] Email sending degrades gracefully (logs warning, doesn't crash) when SMTP not configured
- [ ] All new env vars in `.env.example` and wired through `docker-compose.yml`
- [ ] All existing tests still pass
- [ ] New tests cover all new code

## Verification
```bash
# Lint
ruff check src/ tests/

# Type check (if configured)
# mypy src/

# All tests
python -m pytest tests/ -v

# Specific new/modified test files
python -m pytest tests/test_scheduler.py tests/test_models.py tests/test_mailer.py -v

# Verify migration applies
# (requires running DB — skip in CI, verify manually)
# alembic upgrade head
# alembic downgrade -1
# alembic upgrade head
```

## Done Criteria
- [ ] All implementation tasks above completed
- [ ] Build passes
- [ ] Tests pass
- [ ] PR created with `Closes FLI-104`, `Closes FLI-105`, `Closes FLI-107`, `Closes FLI-108`
- [ ] /revise spawned via tmux

## NOT in Scope (do NOT attempt)
- Price drop detection logic (future FLI-106)
- Alert triggering/orchestration logic (future issue)
- Email template refinement beyond functional HTML
- Refactoring adjacent code not mentioned in tasks
- Adding tests beyond what's specified in tasks
- Fixing pre-existing lint warnings in untouched files
- Any cleanup, polish, or "while I'm here" improvements
