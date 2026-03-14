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
