import logging
import signal
import sys
import time

from flight_watcher.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def _handle_signal(signum, frame):
    logger.info("Received signal %s, shutting down...", signum)
    stop_scheduler()
    sys.exit(0)


def main():
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    start_scheduler()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_scheduler()


if __name__ == "__main__":
    main()
