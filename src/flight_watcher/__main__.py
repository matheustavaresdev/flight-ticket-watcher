import logging
import signal
import sys
import time

from flight_watcher.cli import cli
from flight_watcher.db import dispose_engine
from flight_watcher.health_server import start_health_server, stop_health_server
from flight_watcher.scanner_state import ScannerStatus, get_scanner_state
from flight_watcher.scheduler import register_scan_job, start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def _handle_signal(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    get_scanner_state().status = ScannerStatus.SHUTTING_DOWN
    stop_health_server()
    stop_scheduler()
    dispose_engine()
    logger.info("Shutdown complete")
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    start_health_server()
    start_scheduler()
    register_scan_job()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        get_scanner_state().status = ScannerStatus.SHUTTING_DOWN
        stop_health_server()
        stop_scheduler()
        dispose_engine()


@cli.command("scheduler")
def scheduler():
    """Run the flight price scheduler."""
    main()


if __name__ == "__main__":
    if not sys.argv[1:]:
        main()
    else:
        cli()
