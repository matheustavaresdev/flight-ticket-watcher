import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from flight_watcher.mailer import ALERT_EMAIL_TO, send_price_alert_email
from flight_watcher.models import PriceAlert

logger = logging.getLogger(__name__)


def send_alerts(session: Session, alerts: list[PriceAlert]) -> int:
    """Send email for each alert. Updates sent_to/sent_at on success. Returns count sent."""
    sent_count = 0

    for alert in alerts:
        alert_data = {
            "origin": alert.origin,
            "destination": alert.destination,
            "flight_date": alert.flight_date,
            "airline": alert.airline,
            "brand": alert.brand,
            "new_price": alert.new_price,
            "previous_low_price": alert.previous_low_price,
            "price_drop_abs": alert.price_drop_abs,
            "alert_type": alert.alert_type.value,
        }

        success = send_price_alert_email(alert_data)
        if success:
            alert.sent_to = ALERT_EMAIL_TO
            alert.sent_at = datetime.now(tz=timezone.utc)
            sent_count += 1

    session.commit()
    return sent_count
