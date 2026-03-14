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
    port = int(os.environ.get("HEALTH_PORT", "8080"))
    url = f"http://localhost:{port}/health"

    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            body = resp.read()
            data = json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read()
        data = json.loads(body)
        typer.echo(f"Daemon is {data.get('status', 'unhealthy')} [WARN]")
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
    last_scans = data.get("last_successful_scans", {})
    next_scan = data.get("next_scheduled_scan")

    typer.echo(f"Daemon status:    {status}")
    typer.echo(f"Started at:       {started_at}")
    typer.echo(f"Scanner:          {scanner}")
    typer.echo(f"Circuit breaker:  {cb_state} (failures={cb_failures})")
    if cb_backoff is not None:
        typer.echo(f"  backoff remaining: {cb_backoff:.0f}s")
    if last_scans:
        typer.echo("Last successful scans:")
        for config_id, ts in last_scans.items():
            typer.echo(f"  {config_id}: {ts}")
    if next_scan:
        typer.echo(f"Next scheduled scan: {next_scan}")

    if cb_state in ("open", "half_open"):
        typer.echo(f"[WARN] circuit breaker is {cb_state}")
        raise typer.Exit(1)
    else:
        typer.echo("[OK]")
