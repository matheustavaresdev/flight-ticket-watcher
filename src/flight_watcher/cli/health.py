"""Health check command."""

import typer


def health_check() -> None:
    """Check DB connection, circuit breaker state, and scheduler status."""
    from sqlalchemy import text

    from flight_watcher.circuit_breaker import get_breaker
    from flight_watcher.db import get_session

    issues = []
    db_failed = False

    # DB check
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        db_status = "OK"
    except Exception as exc:
        db_status = f"FAIL ({exc})"
        issues.append("db")
        db_failed = True

    # Circuit breaker
    breaker_info = get_breaker().status_info()
    cb_state = breaker_info["state"]
    cb_failures = breaker_info["consecutive_failures"]
    cb_remaining = breaker_info.get("backoff_remaining_sec")

    if cb_state in ("open", "half_open"):
        issues.append("circuit_breaker")

    # Scheduler
    from flight_watcher.scheduler import _scheduler as _sched

    if _sched is not None and _sched.running:
        sched_status = "Running"
    else:
        sched_status = "Not running (daemon mode only)"

    typer.echo(f"DB connection:    {db_status}")
    typer.echo(f"Circuit breaker:  {cb_state} (failures={cb_failures})")
    if cb_remaining is not None:
        typer.echo(f"  backoff remaining: {cb_remaining:.0f}s")
    typer.echo(f"Scheduler:        {sched_status}")

    if db_failed:
        typer.echo(f"[FAIL] {len(issues)} issue(s) detected")
    elif issues:
        typer.echo(f"[WARN] {len(issues)} issue(s) detected")
    else:
        typer.echo("[OK]")
