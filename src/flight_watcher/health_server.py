import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from sqlalchemy import func, select

from flight_watcher.circuit_breaker import get_breaker
from flight_watcher.models import ScanRun
from flight_watcher.scanner_state import ScannerStatus, get_scanner_state

logger = logging.getLogger(__name__)

_server: Optional[HTTPServer] = None
_server_thread: Optional[threading.Thread] = None


def _get_health_data() -> tuple[dict, int]:
    """Build health response data and HTTP status code."""
    state = get_scanner_state()
    breaker = get_breaker()

    scanner_status = state.status

    # Get next scheduled scan time
    next_scan = None
    try:
        import flight_watcher.scheduler as sched_mod  # deferred import to avoid circular dependency
        scheduler = sched_mod.get_scheduler()
        if scheduler is not None:
            jobs = scheduler.get_jobs()
            run_times = [j.next_run_time for j in jobs if j.next_run_time is not None]
            if run_times:
                next_scan = min(run_times).isoformat()
    except Exception as e:
        logger.warning("Failed to query next scheduled scan: %s", e)

    # Get last successful scans
    last_successful_scans: dict = {}
    try:
        from flight_watcher.db import get_session
        with get_session() as session:
            rows = session.execute(
                select(ScanRun.search_config_id, func.max(ScanRun.completed_at))
                .where(ScanRun.status == "completed")
                .group_by(ScanRun.search_config_id)
            ).all()
            last_successful_scans = {
                str(row[0]): row[1].isoformat() if row[1] else None
                for row in rows
            }
    except Exception as e:
        logger.warning("Failed to query last successful scans: %s", e)

    is_shutting_down = scanner_status == ScannerStatus.SHUTTING_DOWN
    http_status = 503 if is_shutting_down else 200

    data = {
        "status": "shutting_down" if is_shutting_down else "healthy",
        "scanner": scanner_status.value,
        "started_at": state.started_at.isoformat(),
        "circuit_breaker": breaker.status_info(),
        "last_successful_scans": last_successful_scans,
        "next_scheduled_scan": next_scan,
    }
    return data, http_status


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/health":
            self.send_response(404)
            self.end_headers()
            return
        data, status = _get_health_data()
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Suppress default access logging to avoid noise
        pass


def start_health_server() -> None:
    """Start the health HTTP server in a daemon thread."""
    global _server, _server_thread
    port = int(os.environ.get("HEALTH_PORT", "8080"))
    _server = HTTPServer(("", port), _HealthHandler)
    _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
    _server_thread.start()
    logger.info("Health server started on port %d", port)


def stop_health_server() -> None:
    """Shut down the health HTTP server."""
    global _server, _server_thread
    if _server is not None:
        _server.shutdown()
        _server = None
        _server_thread = None
        logger.info("Health server stopped")
