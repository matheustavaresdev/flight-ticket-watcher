import os
import smtplib
import unittest
from unittest.mock import MagicMock, patch

MAILER_MODULE = "flight_watcher.mailer"

_SAMPLE_ALERT = {
    "origin": "GRU",
    "destination": "SAT",
    "flight_date": "2026-04-10",
    "airline": "LATAM",
    "brand": "LIGHT",
    "new_price": "450.00",
    "previous_low_price": "600.00",
    "price_drop_abs": "150.00",
    "alert_type": "new_low",
}

_SMTP_ENV = {
    "SMTP_HOST": "smtp.gmail.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "user@example.com",
    "SMTP_PASSWORD": "secret",
    "SMTP_FROM": "alerts@example.com",
    "ALERT_EMAIL_TO": "me@example.com",
}


class TestIsEmailConfigured(unittest.TestCase):
    def test_is_email_configured_true(self):
        with patch.dict(os.environ, _SMTP_ENV, clear=False):
            import importlib
            import flight_watcher.mailer as mailer_mod
            importlib.reload(mailer_mod)
            self.assertTrue(mailer_mod.is_email_configured())

    def test_is_email_configured_false_missing_host(self):
        env = {**_SMTP_ENV, "SMTP_HOST": ""}
        with patch.dict(os.environ, env, clear=False):
            import importlib
            import flight_watcher.mailer as mailer_mod
            importlib.reload(mailer_mod)
            self.assertFalse(mailer_mod.is_email_configured())

    def test_is_email_configured_false_missing_from(self):
        env = {**_SMTP_ENV, "SMTP_FROM": ""}
        with patch.dict(os.environ, env, clear=False):
            import importlib
            import flight_watcher.mailer as mailer_mod
            importlib.reload(mailer_mod)
            self.assertFalse(mailer_mod.is_email_configured())


class TestSendPriceAlertEmail(unittest.TestCase):
    @patch(f"{MAILER_MODULE}.is_email_configured", return_value=True)
    @patch(f"{MAILER_MODULE}.SMTP_HOST", "smtp.gmail.com")
    @patch(f"{MAILER_MODULE}.SMTP_PORT", 587)
    @patch(f"{MAILER_MODULE}.SMTP_FROM", "alerts@example.com")
    @patch(f"{MAILER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    @patch(f"{MAILER_MODULE}.SMTP_USERNAME", "user@example.com")
    @patch(f"{MAILER_MODULE}.SMTP_PASSWORD", "secret")
    @patch(f"{MAILER_MODULE}.smtplib.SMTP")
    def test_send_price_alert_email_success(self, mock_smtp_cls, *args):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.mailer import send_price_alert_email

        result = send_price_alert_email(_SAMPLE_ALERT)

        self.assertTrue(result)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user@example.com", "secret")
        mock_server.send_message.assert_called_once()

    def test_send_price_alert_email_not_configured(self):
        with patch(f"{MAILER_MODULE}.is_email_configured", return_value=False):
            from flight_watcher.mailer import send_price_alert_email

            with self.assertLogs(MAILER_MODULE, level="WARNING") as cm:
                result = send_price_alert_email(_SAMPLE_ALERT)

            self.assertFalse(result)
            self.assertTrue(any("not configured" in line for line in cm.output))

    @patch(f"{MAILER_MODULE}.is_email_configured", return_value=True)
    @patch(f"{MAILER_MODULE}.SMTP_HOST", "smtp.gmail.com")
    @patch(f"{MAILER_MODULE}.SMTP_PORT", 587)
    @patch(f"{MAILER_MODULE}.SMTP_FROM", "alerts@example.com")
    @patch(f"{MAILER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    @patch(f"{MAILER_MODULE}.SMTP_USERNAME", "")
    @patch(f"{MAILER_MODULE}.SMTP_PASSWORD", "")
    @patch(f"{MAILER_MODULE}.smtplib.SMTP")
    def test_send_price_alert_email_smtp_error(self, mock_smtp_cls, *args):
        mock_server = MagicMock()
        mock_server.starttls.side_effect = smtplib.SMTPException("connection refused")
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.mailer import send_price_alert_email

        with self.assertLogs(MAILER_MODULE, level="ERROR") as cm:
            result = send_price_alert_email(_SAMPLE_ALERT)

        self.assertFalse(result)
        self.assertTrue(any("Failed" in line for line in cm.output))

    @patch(f"{MAILER_MODULE}.is_email_configured", return_value=True)
    @patch(f"{MAILER_MODULE}.SMTP_HOST", "smtp.gmail.com")
    @patch(f"{MAILER_MODULE}.SMTP_PORT", 587)
    @patch(f"{MAILER_MODULE}.SMTP_FROM", "alerts@example.com")
    @patch(f"{MAILER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    @patch(f"{MAILER_MODULE}.SMTP_USERNAME", "")
    @patch(f"{MAILER_MODULE}.SMTP_PASSWORD", "")
    @patch(f"{MAILER_MODULE}.smtplib.SMTP")
    def test_send_price_alert_email_no_auth(self, mock_smtp_cls, *args):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = MagicMock(return_value=mock_server)
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)

        from flight_watcher.mailer import send_price_alert_email

        result = send_price_alert_email(_SAMPLE_ALERT)

        self.assertTrue(result)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_not_called()
        mock_server.send_message.assert_called_once()

    @patch(f"{MAILER_MODULE}.is_email_configured", return_value=True)
    @patch(f"{MAILER_MODULE}.SMTP_HOST", "smtp.gmail.com")
    @patch(f"{MAILER_MODULE}.SMTP_PORT", 587)
    @patch(f"{MAILER_MODULE}.SMTP_FROM", "alerts@example.com")
    @patch(f"{MAILER_MODULE}.ALERT_EMAIL_TO", "me@example.com")
    @patch(f"{MAILER_MODULE}.SMTP_USERNAME", "")
    @patch(f"{MAILER_MODULE}.SMTP_PASSWORD", "")
    @patch(f"{MAILER_MODULE}.smtplib.SMTP")
    def test_send_price_alert_email_connection_refused(self, mock_smtp_cls, *args):
        mock_smtp_cls.side_effect = ConnectionRefusedError("Connection refused")

        from flight_watcher.mailer import send_price_alert_email

        with self.assertLogs(MAILER_MODULE, level="ERROR") as cm:
            result = send_price_alert_email(_SAMPLE_ALERT)

        self.assertFalse(result)
        self.assertTrue(any("Failed" in line for line in cm.output))


class TestBuildAlertHtml(unittest.TestCase):
    def test_build_alert_html_contains_key_info(self):
        from flight_watcher.mailer import _build_alert_html

        html = _build_alert_html(_SAMPLE_ALERT)

        self.assertIn("GRU", html)
        self.assertIn("SAT", html)
        self.assertIn("2026-04-10", html)
        self.assertIn("450.00", html)
        self.assertIn("600.00", html)

    def test_build_alert_html_contains_google_flights_link(self):
        from flight_watcher.mailer import _build_alert_html

        html = _build_alert_html(_SAMPLE_ALERT)

        self.assertIn("google.com/travel/flights", html)

    def test_build_alert_html_partial_7d_stats(self):
        from flight_watcher.mailer import _build_alert_html

        alert_data = {**_SAMPLE_ALERT, "avg_7d": "500.00"}
        html = _build_alert_html(alert_data)

        self.assertIn("500.00", html)
        self.assertIn("N/A", html)
        self.assertNotIn(">None<", html)
        self.assertNotIn("R$ None", html)

    def test_build_alert_html_all_7d_stats(self):
        from flight_watcher.mailer import _build_alert_html

        alert_data = {**_SAMPLE_ALERT, "avg_7d": "500.00", "high_7d": "650.00", "low_7d": "420.00"}
        html = _build_alert_html(alert_data)

        self.assertIn("500.00", html)
        self.assertIn("650.00", html)
        self.assertIn("420.00", html)
        self.assertNotIn("N/A", html)


class TestBuildGoogleFlightsLink(unittest.TestCase):
    def test_build_google_flights_link_contains_origin_dest(self):
        from flight_watcher.mailer import _build_google_flights_link

        url = _build_google_flights_link("GRU", "SAT", "2026-04-10")

        self.assertIn("GRU", url)
        self.assertIn("SAT", url)
        self.assertIn("google.com", url)
