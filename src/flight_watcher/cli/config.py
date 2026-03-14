"""Config subcommands: list, add, toggle."""

import typer
from sqlalchemy import select

from flight_watcher.cli.validators import parse_date, parse_iata
from flight_watcher.date_expansion import expand_dates, generate_pairs
from flight_watcher.db import get_session
from flight_watcher.models import SearchConfig

app = typer.Typer(help="Manage search configurations.", no_args_is_help=True)


@app.command("add")
def config_add(
    origin: str = typer.Argument(..., help="Origin IATA airport code (e.g. FOR)"),
    destination: str = typer.Argument(..., help="Destination IATA airport code (e.g. GRU)"),
    must_arrive_by: str = typer.Argument(..., help="Must arrive by date (YYYY-MM-DD)"),
    must_stay_until: str = typer.Argument(..., help="Must stay until date (YYYY-MM-DD)"),
    max_days: int = typer.Option(..., "--max-days", help="Maximum trip duration in days."),
) -> None:
    """Add a new search configuration."""
    origin = parse_iata(origin)
    destination = parse_iata(destination)
    arrive_by = parse_date(must_arrive_by)
    stay_until = parse_date(must_stay_until)

    try:
        outbound_dates, return_dates = expand_dates(arrive_by, stay_until, max_days)
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(1)

    pair_count = len(generate_pairs(outbound_dates, return_dates, max_days))

    search_config = SearchConfig(
        origin=origin,
        destination=destination,
        must_arrive_by=arrive_by,
        must_stay_until=stay_until,
        max_trip_days=max_days,
        active=True,
    )

    with get_session() as session:
        session.add(search_config)
        session.flush()
        config_id = search_config.id

    typer.echo(
        f"Added config #{config_id}: {origin} \u2192 {destination} "
        f"(arrive by {arrive_by}, stay until {stay_until}, max {max_days} days). "
        f"{pair_count} date pairs generated."
    )
    typer.echo("[OK]")


@app.command("list")
def config_list(
    include_all: bool = typer.Option(False, "--all", help="Include inactive configs."),
) -> None:
    """List search configurations."""
    with get_session() as session:
        stmt = select(SearchConfig).order_by(SearchConfig.id)
        if not include_all:
            stmt = stmt.where(SearchConfig.active.is_(True))
        configs = session.execute(stmt).scalars().all()

    header = f"{'ID':>4}  {'Origin':<8}  {'Dest':<6}  {'Arrive By':<12}  {'Stay Until':<12}  {'Max Days':>8}  {'Active':<6}"
    typer.echo(header)
    typer.echo("-" * len(header))
    for cfg in configs:
        typer.echo(
            f"{cfg.id:>4}  {cfg.origin:<8}  {cfg.destination:<6}  "
            f"{str(cfg.must_arrive_by):<12}  {str(cfg.must_stay_until):<12}  "
            f"{cfg.max_trip_days:>8}  {'Yes' if cfg.active else 'No':<6}"
        )
    typer.echo("[OK]")


@app.command("toggle")
def config_toggle(
    config_id: int = typer.Argument(..., help="Config ID to toggle."),
) -> None:
    """Toggle a search configuration active/inactive."""
    with get_session() as session:
        cfg = session.get(SearchConfig, config_id)
        if cfg is None:
            typer.echo(f"Error: Config {config_id} not found", err=True)
            raise typer.Exit(1)
        cfg.active = not cfg.active
        new_state = "active" if cfg.active else "inactive"

    typer.echo(f"Config #{config_id} is now {new_state}.")
    typer.echo("[OK]")
