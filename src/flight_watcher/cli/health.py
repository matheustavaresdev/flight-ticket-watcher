"""Health check command."""

import typer


def health_check() -> None:
    """Check DB connection, circuit breaker state, and scheduler status."""
    from sqlalchemy import text

    from flight_watcher.circuit_breaker import get_breaker
    from flight_watcher.db import get_session

    issues = []

    # DB check
    try:
        with get_session() as session:
            session.execute(text("SELECT 1"))
        db_status = "OK"
    except Exception as exc:
        db_status = f"FAIL ({exc})"
        issues.append("db")

    # Circuit breaker
    breaker_info = get_breaker().status_info()
    cb_state = breaker_info["state"]
    cb_failures = breaker_info["consecutive_failures"]
    cb_remaining = breaker_info.get("backoff_remaining_sec")

    typer.echo(f"DB connection:    {db_status}")
    typer.echo(f"Circuit breaker:  {cb_state} (failures={cb_failures})")
    if cb_remaining is not None:
        typer.echo(f"  backoff remaining: {cb_remaining:.0f}s")

    if issues:
        typer.echo(f"[WARN] {len(issues)} issue(s) detected")
    else:
        typer.echo("[OK]")
