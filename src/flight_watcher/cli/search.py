"""Search subcommands: latam, fast."""

import time
from typing import Optional

import typer

from flight_watcher.cli.validators import parse_date, parse_iata

app = typer.Typer(help="Search for flights.", no_args_is_help=True)


@app.command("latam")
def search_latam(
    origin: str = typer.Option(..., "--origin", help="Origin IATA code."),
    dest: str = typer.Option(..., "--dest", help="Destination IATA code."),
    out: str = typer.Option(..., "--out", help="Outbound date (YYYY-MM-DD)."),
    inbound: Optional[str] = typer.Option(
        None, "--in", help="Return date (YYYY-MM-DD). Omit for one-way."
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Run browser in headless mode."
    ),
) -> None:
    """Search LATAM flights via browser interception."""
    from flight_watcher.display import print_offers
    from flight_watcher.latam_scraper import (
        parse_offers,
        search_latam_oneway,
        search_latam_roundtrip,
    )

    start = time.time()
    origin = parse_iata(origin)
    dest = parse_iata(dest)
    out = str(parse_date(out))  # validate and normalize to YYYY-MM-DD
    if inbound:
        inbound = str(parse_date(inbound))  # validate and normalize to YYYY-MM-DD

    if inbound:
        outbound_result, return_result = search_latam_roundtrip(
            origin, dest, out, inbound, headless=headless
        )
        offers_count = 0
        if outbound_result.ok and outbound_result.data:
            offers = parse_offers(outbound_result.data)
            offers_count += len(offers)
            typer.echo(f"\nOutbound {origin} \u2192 {dest}:")
            print_offers(offers)
        elif not outbound_result.ok:
            typer.echo(
                f"[WARN] Outbound search failed: {outbound_result.error}", err=True
            )
        if return_result.ok and return_result.data:
            offers = parse_offers(return_result.data)
            offers_count += len(offers)
            typer.echo(f"\nReturn {dest} \u2192 {origin}:")
            print_offers(offers)
        elif not return_result.ok:
            typer.echo(f"[WARN] Return search failed: {return_result.error}", err=True)
    else:
        result = search_latam_oneway(origin, dest, out, headless=headless)
        if result.ok and result.data:
            offers = parse_offers(result.data)
            offers_count = len(offers)
            print_offers(offers)
        else:
            offers_count = 0
            if not result.ok:
                typer.echo(f"[WARN] Search failed: {result.error}", err=True)

    elapsed = time.time() - start
    if offers_count > 0:
        typer.echo(f"[OK] {offers_count} flights found ({elapsed:.1f}s)")
    else:
        typer.echo(f"[FAIL] No flights captured ({elapsed:.1f}s)", err=True)
        raise typer.Exit(1)


@app.command("fast")
def search_fast(
    origin: str = typer.Option(..., "--origin", help="Origin IATA code."),
    dest: str = typer.Option(..., "--dest", help="Destination IATA code."),
    date: str = typer.Option(..., "--date", help="Departure date (YYYY-MM-DD)."),
    return_date: Optional[str] = typer.Option(
        None, "--return-date", help="Return date (YYYY-MM-DD). Omit for one-way."
    ),
) -> None:
    """Search flights via fast-flights (Google Flights)."""
    from flight_watcher.display import print_results
    from flight_watcher.scanner import search_one_way, search_roundtrip

    origin = parse_iata(origin)
    dest = parse_iata(dest)
    date = str(parse_date(date))  # validate and normalize to YYYY-MM-DD
    if return_date:
        return_date = str(parse_date(return_date))  # validate and normalize to YYYY-MM-DD

    if return_date:
        outbound, inbound = search_roundtrip(origin, dest, date, return_date)
        print_results(
            outbound.data or [], header=f"Outbound {origin} \u2192 {dest} on {date}"
        )
        print_results(
            inbound.data or [], header=f"Return {dest} \u2192 {origin} on {return_date}"
        )
        total = len(outbound.data or []) + len(inbound.data or [])
        if not outbound.ok:
            typer.echo(f"[WARN] Outbound search failed: {outbound.error}", err=True)
        if not inbound.ok:
            typer.echo(f"[WARN] Return search failed: {inbound.error}", err=True)
    else:
        result = search_one_way(origin, dest, date)
        print_results(result.data or [])
        total = len(result.data or [])
        if not result.ok:
            typer.echo(f"[WARN] Search failed: {result.error}", err=True)

    if total > 0:
        typer.echo(f"[OK] {total} flights found")
    else:
        typer.echo("[WARN] No flights found")
