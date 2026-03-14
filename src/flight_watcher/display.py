import typer

from flight_watcher.models import FlightResult


def print_results(results: list[FlightResult], header: str = "") -> None:
    """Print flight results in a readable tabular format."""
    if header:
        typer.echo(f"\n{header}")
        typer.echo("=" * len(header))
    if not results:
        typer.echo("No flights found.")
        return
    # Print header row
    typer.echo(f"{'Price':>8}  {'Airline':<30}  {'Dep':>5}  {'Arr':>5}  {'Dur (min)':>9}  {'Stops':>5}")
    typer.echo("-" * 70)
    for r in results:
        typer.echo(f"R${r.price:>7,}  {r.airline:<30}  {r.departure_time:>5}  {r.arrival_time:>5}  {r.duration_min:>9}  {r.stops:>5}")


def print_offers(offers: list[dict]) -> None:
    """Print LATAM offers in a human-readable format."""
    for i, offer in enumerate(offers, 1):
        brands_str = " | ".join(
            f"{b['name']}: {b['currency']} {b['price']:.2f}"
            for b in offer["brands"]
            if b["price"] is not None
            and b["name"] is not None
            and b["currency"] is not None
        )
        stops_str = "direct" if offer["stops"] == 0 else f"{offer['stops']} stop(s)"
        typer.echo(
            f"{i:2d}. {offer['flight_code']}  "
            f"{offer['origin']}->{offer['destination']}  "
            f"{offer['departure']} ({offer['duration_min']}min, {stops_str})  "
            f"[{brands_str}]"
        )
