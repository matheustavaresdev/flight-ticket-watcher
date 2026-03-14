"""Report subcommand: print flight price report for a search config."""

from typing import Optional

import typer

from flight_watcher.db import get_session
from flight_watcher.models import SearchConfig
from flight_watcher.queries import (
    best_combinations,
    get_latest_snapshots,
    roundtrip_vs_oneway,
)

app = typer.Typer(help="Flight price reports.", no_args_is_help=True)


def _fmt_price(price, currency: str = "BRL") -> str:
    symbol = "R$" if currency == "BRL" else currency
    return f"{symbol} {float(price):,.2f}"


def _fmt_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h{m:02d}"


@app.command("show")
def show(
    config_id: int = typer.Argument(..., help="Search config ID to report on."),
    brand: Optional[str] = typer.Option(None, "--brand", help="Filter by brand (e.g. LIGHT, STANDARD, FULL). Default: all brands."),
    top: int = typer.Option(10, "--top", help="Number of top flights to show."),
) -> None:
    """Print a flight price report for a search config."""
    with get_session() as session:
        config = session.get(SearchConfig, config_id)
        if config is None:
            typer.echo(f"Error: Config {config_id} not found", err=True)
            raise typer.Exit(1)

        origin = config.origin
        destination = config.destination

        # Section 1: Top Flights
        brands_to_show = [brand] if brand else ["ECONOMY", "LIGHT", "STANDARD", "FULL"]
        all_snapshots = []
        for b in brands_to_show:
            snaps = get_latest_snapshots(session, config_id, brand=b)
            all_snapshots.extend(snaps)

        all_snapshots.sort(key=lambda s: s.price)

        typer.echo(f"\n=== Flight Report: {origin} → {destination} (config #{config_id}) ===\n")

        typer.echo("── Top Flights " + "─" * 45)
        header = f"  {'#':>3}  {'Date':<12}  {'Flight':<8}  {'Depart':<7}  {'Arrive':<7}  {'Dur':<7}  {'Stops':>5}  {'Brand':<12}  {'Price':>12}"
        typer.echo(header)
        typer.echo("  " + "-" * (len(header) - 2))

        shown = all_snapshots[:top]
        for i, s in enumerate(shown, 1):
            dep = s.departure_time.strftime("%H:%M")
            arr = s.arrival_time.strftime("%H:%M")
            dur = _fmt_duration(s.duration_min)
            price_str = _fmt_price(s.price, s.currency)
            typer.echo(f"  {i:>3}  {str(s.flight_date):<12}  {s.flight_code:<8}  {dep:<7}  {arr:<7}  {dur:<7}  {s.stops:>5}  {s.brand:<12}  {price_str:>12}")

        total = len(all_snapshots)
        typer.echo(f"Showing top {min(top, total)} of {total} results.\n")

        # Section 2: Best by Stay Length
        typer.echo("── Best by Stay Length " + "─" * 37)
        b_arg = brand if brand else "ECONOMY"
        combos = best_combinations(session, config_id, brand=b_arg)

        header2 = f"  {'':2}  {'Days':>4}  {'Outbound':<12}  {'Return':<12}  {'Out Price':>12}  {'Ret Price':>12}  {'Total':>12}"
        typer.echo(header2)
        typer.echo("  " + "-" * (len(header2) - 2))

        if combos:
            min_total = min(c["total_price"] for c in combos)
            for combo in combos:
                marker = "*" if combo["total_price"] == min_total else " "
                out_p = _fmt_price(combo["outbound_price"], combo["currency"])
                ret_p = _fmt_price(combo["return_price"], combo["currency"])
                tot_p = _fmt_price(combo["total_price"], combo["currency"])
                typer.echo(
                    f"  {marker}  {combo['trip_days']:>4}  {str(combo['outbound_date']):<12}  {str(combo['return_date']):<12}  {out_p:>12}  {ret_p:>12}  {tot_p:>12}"
                )
        else:
            typer.echo("  No combinations found.")
        typer.echo("")

        # Section 3: Roundtrip vs One-Way
        typer.echo("── Roundtrip vs One-Way " + "─" * 36)
        rt_rows = roundtrip_vs_oneway(session, config_id, brand=b_arg)

        header3 = f"  {'Outbound':<12}  {'Return':<12}  {'RT Total':>12}  {'OW Total':>12}  {'RT diff':>8}  {'Rec'}"
        typer.echo(header3)
        typer.echo("  " + "-" * (len(header3) - 2))

        if rt_rows:
            for row in rt_rows:
                sig = " **" if row["significant"] else ""
                if row["recommendation"] == "2x one-way":
                    savings_str = f"+{row['savings_pct']:.1f}%"
                else:
                    savings_str = f"-{row['savings_pct']:.1f}%"
                rt_p = _fmt_price(row["roundtrip_total"], "BRL")
                ow_p = _fmt_price(row["oneway_total"], "BRL")
                typer.echo(
                    f"  {str(row['outbound_date']):<12}  {str(row['return_date']):<12}  {rt_p:>12}  {ow_p:>12}  {savings_str:>8}  {row['recommendation']}{sig}"
                )
            typer.echo("** = significant (>5% savings)")
            typer.echo("RT diff: negative = roundtrip cheaper; positive = one-way cheaper")
        else:
            typer.echo("  No roundtrip vs one-way data found.")
        typer.echo("")

        typer.echo("[OK]")
