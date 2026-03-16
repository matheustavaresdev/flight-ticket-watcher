import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

ALERTS_MODULE = "flight_watcher.alerts"


def _make_snapshot(
    origin="GRU",
    destination="GIG",
    flight_date=date(2026, 6, 13),
    brand="LIGHT",
    price=Decimal("500.00"),
    flight_code="LA3456",
    scan_run_id=1,
):
    m = MagicMock()
    m.origin = origin
    m.destination = destination
    m.flight_date = flight_date
    m.brand = brand
    m.price = price
    m.flight_code = flight_code
    m.scan_run_id = scan_run_id
    return m


def _make_alert(
    new_price=Decimal("500.00"),
    alert_type=None,
):
    from flight_watcher.models import AlertType

    m = MagicMock()
    m.new_price = new_price
    m.alert_type = alert_type or AlertType.NEW_LOW
    return m


class TestDetectPriceDrops(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()

    def _setup_session(self, snapshots, historical_min=None, last_alert=None):
        """Configure session.scalars and session.execute for common patterns."""
        # snapshots query
        self.session.scalars.return_value.all.return_value = snapshots
        # historical min
        self.session.execute.return_value.scalar.return_value = historical_min
        # last alert
        self.session.scalars.return_value.first.return_value = last_alert

    def test_no_history_no_alerts(self):
        """First scan for a route — no prior snapshots → no alerts."""
        from flight_watcher.alerts import detect_price_drops

        snap = _make_snapshot(price=Decimal("500.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = None  # no history

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(result, [])
        self.session.add.assert_not_called()

    def test_new_low_triggered(self):
        """Price lower than historical min → NEW_LOW alert created."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap = _make_snapshot(price=Decimal("400.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = Decimal("500.00")
        # No prior alert
        self.session.scalars.return_value.first.return_value = None

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(len(result), 1)
        alert = result[0]
        self.assertEqual(alert.alert_type, AlertType.NEW_LOW)
        self.assertEqual(alert.new_price, Decimal("400.00"))
        self.assertEqual(alert.previous_low_price, Decimal("500.00"))
        self.assertEqual(alert.price_drop_abs, Decimal("100.00"))

    def test_new_low_not_triggered_price_higher(self):
        """Price higher than historical min → no alert."""
        from flight_watcher.alerts import detect_price_drops

        snap = _make_snapshot(price=Decimal("600.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = Decimal("500.00")

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(result, [])

    def test_threshold_triggered(self):
        """Price below ALERT_THRESHOLD_BRL → THRESHOLD alert created."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap = _make_snapshot(price=Decimal("290.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = None  # no prior history
        self.session.scalars.return_value.first.return_value = None

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": "300"}):
            result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].alert_type, AlertType.THRESHOLD)
        self.assertEqual(result[0].new_price, Decimal("290.00"))

    def test_threshold_not_set_no_alert(self):
        """ALERT_THRESHOLD_BRL not in env → no THRESHOLD alerts."""
        from flight_watcher.alerts import detect_price_drops

        snap = _make_snapshot(price=Decimal("200.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = None
        self.session.scalars.return_value.first.return_value = None

        env_without_threshold = {k: v for k, v in os.environ.items() if k != "ALERT_THRESHOLD_BRL"}
        with patch.dict(os.environ, env_without_threshold, clear=True):
            result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(result, [])

    def test_dedup_skips_when_already_alerted(self):
        """Last alert's new_price <= current price → skip."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap = _make_snapshot(price=Decimal("400.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = Decimal("500.00")
        # Prior alert already at same price — dedup should skip
        last_alert = _make_alert(new_price=Decimal("400.00"), alert_type=AlertType.NEW_LOW)
        self.session.scalars.return_value.first.return_value = last_alert

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(result, [])

    def test_dedup_allows_lower_price(self):
        """Last alert's new_price > current price → new alert allowed."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap = _make_snapshot(price=Decimal("350.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = Decimal("500.00")
        # Prior alert at 400 — current 350 is lower, so allow
        last_alert = _make_alert(new_price=Decimal("400.00"), alert_type=AlertType.NEW_LOW)
        self.session.scalars.return_value.first.return_value = last_alert

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].new_price, Decimal("350.00"))
        self.assertEqual(result[0].previous_low_price, Decimal("400.00"))

    def test_both_alert_types_fire(self):
        """Price triggers both NEW_LOW and THRESHOLD → 2 alerts."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap = _make_snapshot(price=Decimal("250.00"))
        self.session.scalars.return_value.all.return_value = [snap]
        self.session.execute.return_value.scalar.return_value = Decimal("400.00")
        self.session.scalars.return_value.first.return_value = None

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": "300"}):
            result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(len(result), 2)
        types = {a.alert_type for a in result}
        self.assertIn(AlertType.NEW_LOW, types)
        self.assertIn(AlertType.THRESHOLD, types)

    def test_multiple_routes_in_scan(self):
        """Scan with multiple route+date groups → correct per-group detection."""
        from flight_watcher.alerts import detect_price_drops
        from flight_watcher.models import AlertType

        snap1 = _make_snapshot(
            origin="GRU", destination="GIG", price=Decimal("400.00"), flight_date=date(2026, 6, 13)
        )
        snap2 = _make_snapshot(
            origin="GRU", destination="SSA", price=Decimal("600.00"), flight_date=date(2026, 7, 1)
        )
        self.session.scalars.return_value.all.return_value = [snap1, snap2]

        # Route 1: has history, price is lower → alert
        # Route 2: has history, price is higher → no alert
        execute_results = [Decimal("500.00"), Decimal("550.00")]
        call_idx = 0

        def scalar_side_effect():
            nonlocal call_idx
            val = execute_results[call_idx % len(execute_results)]
            call_idx += 1
            return val

        self.session.execute.return_value.scalar.side_effect = scalar_side_effect
        self.session.scalars.return_value.first.return_value = None

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        # Only snap1's route triggered (400 < 500); snap2's route did not (600 > 550)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].destination, "GIG")

    def test_empty_scan_no_alerts(self):
        """Scan with no snapshots → returns empty list immediately."""
        from flight_watcher.alerts import detect_price_drops

        self.session.scalars.return_value.all.return_value = []

        result = detect_price_drops(self.session, scan_run_id=1, search_config_id=1)

        self.assertEqual(result, [])


class TestGetThresholdBrl(unittest.TestCase):
    def test_valid_integer(self):
        from flight_watcher.alerts import _get_threshold_brl

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": "500"}):
            result = _get_threshold_brl()
        self.assertEqual(result, Decimal("500"))

    def test_valid_decimal(self):
        from flight_watcher.alerts import _get_threshold_brl

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": "499.99"}):
            result = _get_threshold_brl()
        self.assertEqual(result, Decimal("499.99"))

    def test_not_set(self):
        from flight_watcher.alerts import _get_threshold_brl

        env = {k: v for k, v in os.environ.items() if k != "ALERT_THRESHOLD_BRL"}
        with patch.dict(os.environ, env, clear=True):
            result = _get_threshold_brl()
        self.assertIsNone(result)

    def test_empty_string(self):
        from flight_watcher.alerts import _get_threshold_brl

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": ""}):
            result = _get_threshold_brl()
        self.assertIsNone(result)

    def test_invalid_value(self):
        from flight_watcher.alerts import _get_threshold_brl

        with patch.dict(os.environ, {"ALERT_THRESHOLD_BRL": "not-a-number"}):
            result = _get_threshold_brl()
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
