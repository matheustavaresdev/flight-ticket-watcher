"""CLI entry point for flight-watcher management commands."""

from datetime import date

import click
from sqlalchemy import select

from flight_watcher.date_expansion import expand_dates, generate_pairs
from flight_watcher.db import get_session
from flight_watcher.models import SearchConfig


def _parse_iata(value: str) -> str:
    """Validate and uppercase an IATA airport code."""
    code = value.upper()
    if len(code) != 3 or not code.isalpha():
        raise click.ClickException(
            f"Invalid IATA code '{value}': must be exactly 3 alphabetic characters."
        )
    return code


def _parse_date(value: str) -> date:
    """Parse a YYYY-MM-DD date string, raising ClickException on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise click.ClickException(
            f"Invalid date '{value}': expected format YYYY-MM-DD."
        )


@click.group()
def cli():
    """Flight Watcher CLI."""


@cli.group()
def config():
    """Manage search configurations."""


@config.command("add")
@click.argument("origin")
@click.argument("destination")
@click.argument("must_arrive_by")
@click.argument("must_stay_until")
@click.option(
    "--max-days", required=True, type=int, help="Maximum trip duration in days."
)
def config_add(origin, destination, must_arrive_by, must_stay_until, max_days):
    """Add a new search configuration.

    Example: python -m flight_watcher config add FOR MIA 2026-06-21 2026-06-28 --max-days 15
    """
    origin = _parse_iata(origin)
    destination = _parse_iata(destination)
    arrive_by = _parse_date(must_arrive_by)
    stay_until = _parse_date(must_stay_until)

    try:
        outbound_dates, return_dates = expand_dates(arrive_by, stay_until, max_days)
    except ValueError as exc:
        raise click.ClickException(str(exc))

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

    click.echo(
        f"Added config #{config_id}: {origin} → {destination} "
        f"(arrive by {arrive_by}, stay until {stay_until}, max {max_days} days). "
        f"{pair_count} date pairs generated."
    )


@config.command("list")
@click.option(
    "--all",
    "include_all",
    is_flag=True,
    default=False,
    help="Include inactive configs.",
)
def config_list(include_all):
    """List search configurations."""
    with get_session() as session:
        stmt = select(SearchConfig).order_by(SearchConfig.id)
        if not include_all:
            stmt = stmt.where(SearchConfig.active.is_(True))
        configs = session.execute(stmt).scalars().all()

    header = f"{'ID':>4}  {'Origin':<8}  {'Dest':<6}  {'Arrive By':<12}  {'Stay Until':<12}  {'Max Days':>8}  {'Active':<6}"
    click.echo(header)
    click.echo("-" * len(header))
    for cfg in configs:
        click.echo(
            f"{cfg.id:>4}  {cfg.origin:<8}  {cfg.destination:<6}  "
            f"{str(cfg.must_arrive_by):<12}  {str(cfg.must_stay_until):<12}  "
            f"{cfg.max_trip_days:>8}  {'Yes' if cfg.active else 'No':<6}"
        )


@config.command("deactivate")
@click.argument("config_id", type=int)
def config_deactivate(config_id):
    """Deactivate a search configuration by ID."""
    with get_session() as session:
        cfg = session.get(SearchConfig, config_id)
        if cfg is None:
            raise click.ClickException(f"Config {config_id} not found")
        cfg.active = False

    click.echo(f"Config #{config_id} deactivated.")
