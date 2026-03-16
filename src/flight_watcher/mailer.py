import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")
ALERT_EMAIL_TO = os.environ.get("ALERT_EMAIL_TO", "")
ALERT_THRESHOLD_BRL = os.environ.get("ALERT_THRESHOLD_BRL", "")


def is_email_configured() -> bool:
    return bool(SMTP_HOST and SMTP_FROM and ALERT_EMAIL_TO)


def _build_google_flights_link(origin: str, destination: str, flight_date: str) -> str:
    date_fmt = flight_date.replace("-", "")
    return (
        f"https://www.google.com/travel/flights/search"
        f"?tfs=CBwQAhoeEgoyMDI1LTAxLTAxagcIARIDR1JVcgcIARIDU0FUMABB&hl=pt-BR"
        f"#flt={origin}.{destination}.{date_fmt};c:BRL;e:1;sd:1;t:f"
    )


def _build_alert_html(alert_data: dict) -> str:
    origin = alert_data["origin"]
    destination = alert_data["destination"]
    flight_date = str(alert_data["flight_date"])
    airline = alert_data["airline"]
    brand = alert_data["brand"]
    new_price = alert_data["new_price"]
    previous_low_price = alert_data["previous_low_price"]
    price_drop_abs = alert_data["price_drop_abs"]
    alert_type = alert_data.get("alert_type", "")

    avg_7d = alert_data.get("avg_7d")
    high_7d = alert_data.get("high_7d")
    low_7d = alert_data.get("low_7d")

    gf_link = _build_google_flights_link(origin, destination, flight_date)

    stats_html = ""
    if avg_7d is not None or high_7d is not None or low_7d is not None:
        stats_html = f"""
        <tr>
          <td colspan="2" style="padding-top:16px;">
            <strong>7-day stats</strong><br>
            Avg: R$ {avg_7d} &nbsp; High: R$ {high_7d} &nbsp; Low: R$ {low_7d}
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px;">
  <h2 style="color:#1a73e8;">✈ Price Alert: {origin} → {destination}</h2>
  <table style="width:100%;border-collapse:collapse;">
    <tr>
      <td style="padding:8px 0;"><strong>Flight date</strong></td>
      <td>{flight_date}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;"><strong>Airline / Brand</strong></td>
      <td>{airline} / {brand}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;"><strong>Alert type</strong></td>
      <td>{alert_type}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;"><strong>New price</strong></td>
      <td style="color:#0d652d;font-size:1.4em;font-weight:bold;">R$ {new_price}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;"><strong>Previous low</strong></td>
      <td>R$ {previous_low_price}</td>
    </tr>
    <tr>
      <td style="padding:8px 0;"><strong>Drop</strong></td>
      <td style="color:#c62828;">▼ R$ {price_drop_abs}</td>
    </tr>
    {stats_html}
  </table>
  <p style="margin-top:24px;">
    <a href="{gf_link}" style="background:#1a73e8;color:#fff;padding:10px 20px;
       text-decoration:none;border-radius:4px;">Search on Google Flights</a>
  </p>
</body>
</html>"""


def send_price_alert_email(alert_data: dict) -> bool:
    if not is_email_configured():
        logger.warning(
            "Email not configured (SMTP_HOST, SMTP_FROM, or ALERT_EMAIL_TO missing) — skipping alert"
        )
        return False

    try:
        msg = MIMEMultipart("alternative")
        origin = alert_data["origin"]
        destination = alert_data["destination"]
        flight_date = str(alert_data["flight_date"])
        new_price = alert_data["new_price"]
        msg["Subject"] = (
            f"[Flight Alert] {origin}→{destination} on {flight_date}: R$ {new_price}"
        )
        msg["From"] = SMTP_FROM
        msg["To"] = ALERT_EMAIL_TO

        html_body = _build_alert_html(alert_data)
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            if SMTP_USERNAME and SMTP_PASSWORD:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)

        logger.info(
            "Price alert email sent for %s→%s on %s to %s",
            origin,
            destination,
            flight_date,
            ALERT_EMAIL_TO,
        )
        return True

    except (smtplib.SMTPException, OSError) as exc:
        logger.error("Failed to send price alert email: %s", exc)
        return False
