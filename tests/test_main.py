import signal
import sys
import unittest
from unittest.mock import MagicMock, call, patch

MAIN_MODULE = "flight_watcher.__main__"


class TestMainSignalHandlers(unittest.TestCase):
    @patch(f"{MAIN_MODULE}.time")
    @patch(f"{MAIN_MODULE}.start_scheduler")
    @patch(f"{MAIN_MODULE}.signal")
    def test_main_registers_signal_handlers(self, mock_signal, mock_start, mock_time):
        mock_time.sleep.side_effect = KeyboardInterrupt
        from flight_watcher.__main__ import main
        with patch(f"{MAIN_MODULE}.stop_scheduler"):
            main()
        calls = mock_signal.signal.call_args_list
        registered_signals = [c[0][0] for c in calls]
        self.assertIn(mock_signal.SIGTERM, registered_signals)
        self.assertIn(mock_signal.SIGINT, registered_signals)

    @patch(f"{MAIN_MODULE}.time")
    @patch(f"{MAIN_MODULE}.signal")
    @patch(f"{MAIN_MODULE}.start_scheduler")
    def test_main_starts_scheduler(self, mock_start, mock_signal, mock_time):
        mock_time.sleep.side_effect = KeyboardInterrupt
        from flight_watcher.__main__ import main
        with patch(f"{MAIN_MODULE}.stop_scheduler"):
            main()
        mock_start.assert_called_once()

    @patch(f"{MAIN_MODULE}.stop_scheduler")
    @patch(f"{MAIN_MODULE}.sys")
    def test_signal_handler_stops_scheduler(self, mock_sys, mock_stop):
        from flight_watcher.__main__ import _handle_signal
        _handle_signal(signal.SIGTERM, None)
        mock_stop.assert_called_once()
        mock_sys.exit.assert_called_once_with(0)
