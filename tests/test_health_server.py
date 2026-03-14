import json
import urllib.request
import unittest
from unittest.mock import patch, MagicMock

from flight_watcher.scanner_state import ScannerStatus


HEALTH_MODULE = "flight_watcher.health_server"


class TestHealthServer(unittest.TestCase):
    def setUp(self):
        import flight_watcher.health_server as mod
        import flight_watcher.scanner_state as state_mod

        mod._server = None
        mod._server_thread = None
        state_mod._state = None

    def tearDown(self):
        import flight_watcher.health_server as mod
        import flight_watcher.scanner_state as state_mod

        if mod._server is not None:
            mod._server.shutdown()
            mod._server = None
            mod._server_thread = None
        state_mod._state = None

    def _find_free_port(self):
        import socket

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            return s.getsockname()[1]

    def test_server_starts_and_returns_200(self):
        port = self._find_free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port)}):
            with patch(f"{HEALTH_MODULE}.get_breaker") as mock_breaker:
                mock_breaker.return_value = MagicMock(
                    status_info=lambda: {
                        "state": "closed",
                        "consecutive_failures": 0,
                        "backoff_remaining_sec": None,
                    },
                )
                from flight_watcher.health_server import (
                    start_health_server,
                    stop_health_server,
                )

                start_health_server()
                try:
                    response = urllib.request.urlopen(f"http://localhost:{port}/health")
                    self.assertEqual(response.status, 200)
                    data = json.loads(response.read())
                    self.assertIn("status", data)
                    self.assertIn("scanner", data)
                    self.assertIn("circuit_breaker", data)
                finally:
                    stop_health_server()

    def test_returns_503_when_shutting_down(self):
        port = self._find_free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port)}):
            with (
                patch(f"{HEALTH_MODULE}.get_breaker") as mock_breaker,
                patch(f"{HEALTH_MODULE}.get_scanner_state") as mock_state,
            ):
                mock_state.return_value.status = ScannerStatus.SHUTTING_DOWN
                mock_state.return_value.started_at = MagicMock(
                    isoformat=lambda: "2026-01-01T00:00:00+00:00"
                )
                mock_breaker.return_value = MagicMock(
                    status_info=lambda: {
                        "state": "closed",
                        "consecutive_failures": 0,
                        "backoff_remaining_sec": None,
                    },
                )
                from flight_watcher.health_server import (
                    start_health_server,
                    stop_health_server,
                )

                start_health_server()
                try:
                    try:
                        urllib.request.urlopen(f"http://localhost:{port}/health")
                        self.fail("Expected HTTPError 503")
                    except urllib.error.HTTPError as e:
                        self.assertEqual(e.code, 503)
                finally:
                    stop_health_server()

    def test_non_health_path_returns_404(self):
        port = self._find_free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port)}):
            from flight_watcher.health_server import (
                start_health_server,
                stop_health_server,
            )

            start_health_server()
            try:
                try:
                    urllib.request.urlopen(f"http://localhost:{port}/other")
                    self.fail("Expected HTTPError 404")
                except urllib.error.HTTPError as e:
                    self.assertEqual(e.code, 404)
            finally:
                stop_health_server()

    def test_stop_health_server_shuts_down_cleanly(self):
        port = self._find_free_port()
        with patch.dict("os.environ", {"HEALTH_PORT": str(port)}):
            from flight_watcher.health_server import (
                start_health_server,
                stop_health_server,
            )
            import flight_watcher.health_server as mod

            start_health_server()
            self.assertIsNotNone(mod._server)
            stop_health_server()
            self.assertIsNone(mod._server)
