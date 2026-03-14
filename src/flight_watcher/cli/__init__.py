"""CLI entry point for flight-watcher."""

import logging

import typer

app = typer.Typer(help="Flight ticket price monitoring CLI", no_args_is_help=True)


def _configure_logging(verbose: bool, quiet: bool) -> None:
    level = logging.WARNING if quiet else (logging.DEBUG if verbose else logging.INFO)
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable debug logging."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Only show warnings and errors."),
) -> None:
    _configure_logging(verbose, quiet)


from flight_watcher.cli import config as config_module  # noqa: E402
from flight_watcher.cli import runs as runs_module  # noqa: E402
from flight_watcher.cli import scheduler as scheduler_module  # noqa: E402
from flight_watcher.cli import search as search_module  # noqa: E402
from flight_watcher.cli import health as health_module  # noqa: E402

app.add_typer(config_module.app, name="config")
app.add_typer(search_module.app, name="search")
app.add_typer(runs_module.app, name="runs")
app.add_typer(scheduler_module.app, name="scheduler")
app.command("health")(health_module.health_check)
