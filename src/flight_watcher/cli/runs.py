"""Runs subcommands: list."""

from typing import Optional

import typer
from sqlalchemy import select

from flight_watcher.db import get_session
from flight_watcher.models import ScanRun

app = typer.Typer(help="View scan run history.", no_args_is_help=True)


@app.command("list")
def runs_list(
    config_id: Optional[int] = typer.Option(None, "--config-id", help="Filter by config ID."),
    last: int = typer.Option(10, "--last", help="Number of recent runs to show."),
) -> None:
    """List recent scan runs."""
    with get_session() as session:
        stmt = select(ScanRun).order_by(ScanRun.id.desc()).limit(last)
        if config_id is not None:
            stmt = stmt.where(ScanRun.search_config_id == config_id)
        runs = session.execute(stmt).scalars().all()

    if not runs:
        typer.echo("No scan runs found.")
        typer.echo("[OK]")
        return

    header = f"{'ID':>6}  {'Config':>6}  {'Status':<12}  {'Started At':<24}  {'Completed At':<24}  {'Error'}"
    typer.echo(header)
    typer.echo("-" * 90)
    for run in runs:
        completed = str(run.completed_at) if run.completed_at else "-"
        error = (run.error_message or "")[:40]
        typer.echo(
            f"{run.id:>6}  {run.search_config_id:>6}  {run.status.value:<12}  "
            f"{str(run.started_at):<24}  {completed:<24}  {error}"
        )
    typer.echo("[OK]")
