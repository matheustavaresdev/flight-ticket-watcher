import logging
import os
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from flight_watcher.models import AlertType, PriceAlert, PriceSnapshot, ScanRun, ScanStatus

logger = logging.getLogger(__name__)


def _get_historical_min(
    session: Session,
    origin: str,
    dest: str,
    flight_date: date,
    brand: str,
    exclude_scan_run_id: int,
    search_config_id: int,
) -> Decimal | None:
    """MIN(price) across all completed scans for this config except the given one."""
    result = session.execute(
        select(func.min(PriceSnapshot.price))
        .join(ScanRun, PriceSnapshot.scan_run_id == ScanRun.id)
        .where(ScanRun.status == ScanStatus.COMPLETED)
        .where(ScanRun.id != exclude_scan_run_id)
        .where(ScanRun.search_config_id == search_config_id)
        .where(PriceSnapshot.origin == origin)
        .where(PriceSnapshot.destination == dest)
        .where(PriceSnapshot.flight_date == flight_date)
        .where(PriceSnapshot.brand == brand)
    ).scalar()
    return result


def _get_last_alert(
    session: Session,
    origin: str,
    dest: str,
    flight_date: date,
    brand: str,
    alert_type: AlertType,
    search_config_id: int,
) -> PriceAlert | None:
    """Most recent PriceAlert for route+date+brand+type scoped to this config."""
    return session.scalars(
        select(PriceAlert)
        .where(PriceAlert.origin == origin)
        .where(PriceAlert.destination == dest)
        .where(PriceAlert.flight_date == flight_date)
        .where(PriceAlert.brand == brand)
        .where(PriceAlert.alert_type == alert_type)
        .where(PriceAlert.search_config_id == search_config_id)
        .order_by(PriceAlert.created_at.desc())
        .limit(1)
    ).first()


def _get_threshold_brl() -> Decimal | None:
    """Parse ALERT_THRESHOLD_BRL env var. Returns None if not set or invalid."""
    raw = os.environ.get("ALERT_THRESHOLD_BRL", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        logger.warning("ALERT_THRESHOLD_BRL=%r is not a valid decimal — ignoring", raw)
        return None


def detect_price_drops(
    session: Session, scan_run_id: int, search_config_id: int
) -> list[PriceAlert]:
    """Main entry point. Compares current scan's snapshots against history.
    Returns list of PriceAlert records created."""
    # 1. Get all snapshots for this scan run
    snapshots = session.scalars(
        select(PriceSnapshot).where(PriceSnapshot.scan_run_id == scan_run_id)
    ).all()

    if not snapshots:
        return []

    # 2. Group by (origin, destination, flight_date, brand), keep cheapest per group
    groups: dict[tuple, tuple[Decimal, str]] = {}  # key -> (min_price, flight_code)
    for snap in snapshots:
        key = (snap.origin, snap.destination, snap.flight_date, snap.brand)
        if key not in groups or snap.price < groups[key][0]:
            groups[key] = (snap.price, snap.flight_code)

    threshold = _get_threshold_brl()
    created: list[PriceAlert] = []

    for (origin, dest, flight_date, brand), (cheapest_price, flight_code) in groups.items():
        # 3a. Query historical min (exclude current scan)
        historical_min = _get_historical_min(
            session, origin, dest, flight_date, brand, scan_run_id, search_config_id
        )

        # 3b-c. NEW_LOW alert
        if historical_min is not None and cheapest_price < historical_min:
            last_new_low = _get_last_alert(
                session, origin, dest, flight_date, brand, AlertType.NEW_LOW, search_config_id
            )
            if last_new_low is None or cheapest_price < last_new_low.new_price:
                prev_price = (
                    last_new_low.new_price if last_new_low else historical_min
                )
                alert = PriceAlert(
                    search_config_id=search_config_id,
                    origin=origin,
                    destination=dest,
                    flight_date=flight_date,
                    airline=flight_code,
                    brand=brand,
                    previous_low_price=prev_price,
                    new_price=cheapest_price,
                    price_drop_abs=prev_price - cheapest_price,
                    alert_type=AlertType.NEW_LOW,
                )
                session.add(alert)
                created.append(alert)

        # 3d. THRESHOLD alert
        if threshold is not None and cheapest_price < threshold:
            last_threshold = _get_last_alert(
                session, origin, dest, flight_date, brand, AlertType.THRESHOLD, search_config_id
            )
            if last_threshold is None or cheapest_price < last_threshold.new_price:
                prev_price = (
                    last_threshold.new_price
                    if last_threshold
                    else threshold
                )
                alert = PriceAlert(
                    search_config_id=search_config_id,
                    origin=origin,
                    destination=dest,
                    flight_date=flight_date,
                    airline=flight_code,
                    brand=brand,
                    previous_low_price=prev_price,
                    new_price=cheapest_price,
                    price_drop_abs=abs(cheapest_price - threshold),
                    alert_type=AlertType.THRESHOLD,
                )
                session.add(alert)
                created.append(alert)

    if created:
        session.flush()

    return created
