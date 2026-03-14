import threading
import unittest

from flight_watcher.scanner_state import ScannerState, ScannerStatus, get_scanner_state


class TestScannerState(unittest.TestCase):
    def setUp(self):
        import flight_watcher.scanner_state as mod

        mod._state = None

    def tearDown(self):
        import flight_watcher.scanner_state as mod

        mod._state = None

    def test_initial_status_is_idle(self):
        state = ScannerState()
        self.assertEqual(state.status, ScannerStatus.IDLE)

    def test_status_transitions(self):
        state = ScannerState()
        state.status = ScannerStatus.SCANNING
        self.assertEqual(state.status, ScannerStatus.SCANNING)
        state.status = ScannerStatus.IDLE
        self.assertEqual(state.status, ScannerStatus.IDLE)

    def test_to_dict_serialization(self):
        state = ScannerState()
        state.status = ScannerStatus.SCANNING
        d = state.to_dict()
        self.assertEqual(d["status"], "scanning")
        self.assertIn("started_at", d)

    def test_singleton_behavior(self):
        s1 = get_scanner_state()
        s2 = get_scanner_state()
        self.assertIs(s1, s2)

    def test_thread_safety(self):
        state = ScannerState()
        errors = []

        def toggle():
            try:
                for _ in range(100):
                    state.status = ScannerStatus.SCANNING
                    state.status = ScannerStatus.IDLE
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=toggle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
