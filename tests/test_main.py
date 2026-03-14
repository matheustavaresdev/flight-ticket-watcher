import signal
import unittest
from unittest.mock import MagicMock, patch

MAIN_MODULE = "flight_watcher.__main__"


class TestMainSignalHandlers(unittest.TestCase):
    @patch(f"{MAIN_MODULE}.time")
    @patch(f"{MAIN_MODULE}.start_health_server")
    @patch(f"{MAIN_MODULE}.start_scheduler")
    @patch(f"{MAIN_MODULE}.signal")
    def test_main_registers_signal_handlers(
        self, mock_signal, mock_start, mock_health, mock_time
    ):
        mock_time.sleep.side_effect = KeyboardInterrupt
        from flight_watcher.__main__ import main

        with (
            patch(f"{MAIN_MODULE}.stop_scheduler"),
            patch(f"{MAIN_MODULE}.stop_health_server"),
            patch(f"{MAIN_MODULE}.dispose_engine"),
            patch(f"{MAIN_MODULE}.get_scanner_state"),
        ):
            main()
        calls = mock_signal.signal.call_args_list
        registered_signals = [c[0][0] for c in calls]
        self.assertIn(mock_signal.SIGTERM, registered_signals)
        self.assertIn(mock_signal.SIGINT, registered_signals)

    @patch(f"{MAIN_MODULE}.time")
    @patch(f"{MAIN_MODULE}.signal")
    @patch(f"{MAIN_MODULE}.start_health_server")
    @patch(f"{MAIN_MODULE}.start_scheduler")
    def test_main_starts_health_server_before_scheduler(
        self, mock_start, mock_health, mock_signal, mock_time
    ):
        mock_time.sleep.side_effect = KeyboardInterrupt
        from flight_watcher.__main__ import main

        call_order = []
        mock_health.side_effect = lambda: call_order.append("health")
        mock_start.side_effect = lambda: call_order.append("scheduler")
        with (
            patch(f"{MAIN_MODULE}.stop_scheduler"),
            patch(f"{MAIN_MODULE}.stop_health_server"),
            patch(f"{MAIN_MODULE}.dispose_engine"),
            patch(f"{MAIN_MODULE}.get_scanner_state"),
        ):
            main()
        self.assertEqual(call_order, ["health", "scheduler"])

    @patch(f"{MAIN_MODULE}.dispose_engine")
    @patch(f"{MAIN_MODULE}.stop_health_server")
    @patch(f"{MAIN_MODULE}.stop_scheduler")
    @patch(f"{MAIN_MODULE}.get_scanner_state")
    @patch(f"{MAIN_MODULE}.sys")
    def test_signal_handler_full_shutdown_sequence(
        self, mock_sys, mock_get_state, mock_stop_sched, mock_stop_health, mock_dispose
    ):
        mock_state = MagicMock()
        mock_get_state.return_value = mock_state
        from flight_watcher.__main__ import _handle_signal

        _handle_signal(signal.SIGTERM, None)

        mock_stop_health.assert_called_once()
        mock_stop_sched.assert_called_once()
        mock_dispose.assert_called_once()
        mock_sys.exit.assert_called_once_with(0)
