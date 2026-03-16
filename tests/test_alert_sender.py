import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

SENDER_MODULE = "flight_watcher.alert_sender"


def _make_alert(
    origin="GRU",
    destination="GIG",
    flight_date=date(2026, 6, 13),
    airline="LA3456",
    brand="LIGHT",
    new_price=Decimal("400.00"),
    previous_low_price=Decimal("500.00"),
    price_drop_abs=Decimal("100.00"),
    alert_type=None,
    sent_to=None,
    sent_at=None,
):
    from flight_watcher.models import AlertType

    m = MagicMock()
    m.origin = origin
    m.destination = destination
    m.flight_date = flight_date
    m.airline = airline
    m.brand = brand
    m.new_price = new_price
    m.previous_low_price = previous_low_price
    m.price_drop_abs = price_drop_abs
    m.alert_type = alert_type or AlertType.NEW_LOW
    m.sent_to = sent_to
    m.sent_at = sent_at
    return m


class TestSendAlerts(unittest.TestCase):
    def setUp(self):
        self.session = MagicMock()

    @patch(f"{SENDER_MODULE}.send_price_alert_email", return_value=True)
    @patch(f"{SENDER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    def test_send_alerts_calls_mailer(self, mock_send):
        """Verifies send_price_alert_email called per alert."""
        from flight_watcher.alert_sender import send_alerts
        from flight_watcher.models import AlertType

        alert = _make_alert()
        result = send_alerts(self.session, [alert])

        self.assertEqual(result, 1)
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]
        self.assertEqual(call_args["origin"], "GRU")
        self.assertEqual(call_args["destination"], "GIG")
        self.assertEqual(call_args["new_price"], Decimal("400.00"))
        self.assertEqual(call_args["alert_type"], AlertType.NEW_LOW.value)

    @patch(f"{SENDER_MODULE}.send_price_alert_email", return_value=True)
    @patch(f"{SENDER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    def test_send_alerts_updates_sent_fields(self, mock_send):
        """sent_to and sent_at populated on success."""
        from flight_watcher.alert_sender import send_alerts

        alert = _make_alert()
        send_alerts(self.session, [alert])

        self.assertEqual(alert.sent_to, "me@example.com")
        self.assertIsNotNone(alert.sent_at)

    @patch(f"{SENDER_MODULE}.send_price_alert_email", return_value=False)
    def test_send_alerts_handles_mailer_failure(self, mock_send):
        """Mailer returns False → sent fields stay None, continues to next."""
        from flight_watcher.alert_sender import send_alerts

        alert1 = _make_alert(new_price=Decimal("400.00"))
        alert2 = _make_alert(new_price=Decimal("350.00"))
        result = send_alerts(self.session, [alert1, alert2])

        self.assertEqual(result, 0)
        self.assertIsNone(alert1.sent_to)
        self.assertIsNone(alert1.sent_at)
        self.assertIsNone(alert2.sent_to)
        # Still commits even on failure
        self.session.commit.assert_called()

    @patch(f"{SENDER_MODULE}.send_price_alert_email")
    def test_send_alerts_empty_list(self, mock_send):
        """No alerts → returns 0, no mailer calls."""
        from flight_watcher.alert_sender import send_alerts

        result = send_alerts(self.session, [])

        self.assertEqual(result, 0)
        mock_send.assert_not_called()
        self.session.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
