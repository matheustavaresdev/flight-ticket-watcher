"""Scheduler subcommands: start."""

import signal
import sys
import time

import typer

app = typer.Typer(help="Scheduler daemon commands.", no_args_is_help=True)


@app.command("start")
def scheduler_start() -> None:
    """Start the flight price scheduler daemon."""
    import logging

    from flight_watcher.db import dispose_engine
    from flight_watcher.health_server import start_health_server, stop_health_server
    from flight_watcher.scanner_state import ScannerStatus, get_scanner_state
    from flight_watcher.scheduler import register_scan_job, start_scheduler, stop_scheduler

    logger = logging.getLogger(__name__)

    def _shutdown():
        get_scanner_state().status = ScannerStatus.SHUTTING_DOWN
        stop_health_server()
        stop_scheduler()
        dispose_engine()
        logger.info("Shutdown complete")

    def _handle_signal(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        _shutdown()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    start_health_server()
    start_scheduler()
    register_scan_job()

    typer.echo("[OK] Scheduler started")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        _shutdown()
