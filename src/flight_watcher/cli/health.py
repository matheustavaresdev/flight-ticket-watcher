"""Health check command."""

import json
import logging
import os
import urllib.error
import urllib.request

import typer

logger = logging.getLogger(__name__)


def health_check() -> None:
    """Query the running daemon's HTTP health endpoint."""
    raw_port = os.environ.get("HEALTH_PORT", "8080")
    try:
        port = int(raw_port)
    except ValueError:
        typer.echo(f"Error: HEALTH_PORT must be numeric, got '{raw_port}'")
        raise typer.Exit(1)
    url = f"http://localhost:{port}/health"

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read()
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        try:
            data = json.loads(body)
            typer.echo(f"Daemon is {data.get('status', 'unhealthy')} [WARN]")
        except (json.JSONDecodeError, KeyError):
            typer.echo(f"Daemon returned HTTP {exc.code} [FAIL]")
        raise typer.Exit(1)
    except urllib.error.URLError as exc:
        typer.echo(f"Daemon not reachable at {url}: {exc.reason}")
        typer.echo("[FAIL] daemon is not running")
        raise typer.Exit(1)

    status = data.get("status", "unknown")
    scanner = data.get("scanner", "unknown")
    started_at = data.get("started_at", "unknown")
    cb = data.get("circuit_breaker", {})
    cb_state = cb.get("state", "unknown")
    cb_failures = cb.get("consecutive_failures", 0)
    cb_backoff = cb.get("backoff_remaining_sec")
    db_reachable = data.get("db_reachable", True)
    last_scans = data.get("last_successful_scans", {})
    next_scan = data.get("next_scheduled_scan")

    typer.echo(f"Daemon status:    {status}")
    typer.echo(f"Started at:       {started_at}")
    typer.echo(f"Scanner:          {scanner}")
    typer.echo(f"Circuit breaker:  {cb_state} (failures={cb_failures})")
    if cb_backoff is not None:
        typer.echo(f"  backoff remaining: {float(cb_backoff):.0f}s")
    typer.echo(f"Database:         {'reachable' if db_reachable else 'UNREACHABLE'}")
    if last_scans:
        typer.echo("Last successful scans:")
        for config_id, ts in last_scans.items():
            typer.echo(f"  {config_id}: {ts}")
    if next_scan:
        typer.echo(f"Next scheduled scan: {next_scan}")

    if not db_reachable:
        typer.echo("[FAIL] database is unreachable")
        raise typer.Exit(1)
    elif cb_state in ("open", "half_open"):
        typer.echo(f"[WARN] circuit breaker is {cb_state}")
        raise typer.Exit(2)
    else:
        typer.echo("[OK]")
