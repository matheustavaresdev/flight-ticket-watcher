import logging
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from flight_watcher.date_expansion import expand_dates
from flight_watcher.db import get_session
from flight_watcher.delays import random_delay
from flight_watcher.models import (
    FlightResult,
    PriceSnapshot,
    ScanRun,
    ScanStatus,
    SearchConfig,
    SearchType,
)
from flight_watcher.scanner import search_one_way

logger = logging.getLogger(__name__)


def run_all_scans() -> None:
    """Top-level entry: load active configs, run scan for each."""
    with get_session() as session:
        configs = session.scalars(select(SearchConfig).where(SearchConfig.active == True)).all()
    logger.info("Running scans for %d active config(s)", len(configs))
    for config in configs:
        try:
            run_scan(config)
        except Exception as exc:
            logger.error("Unhandled error in run_scan for config %d: %s", config.id, exc)


def run_scan(config: SearchConfig) -> None:
    """Run a full scan for one SearchConfig."""
    outbound_dates, return_dates = expand_dates(
        config.must_arrive_by, config.must_stay_until, config.max_trip_days
    )
    all_dates = sorted(set(outbound_dates + return_dates))

    with get_session() as session:
        # Check for a resumable run from today
        resumable = _find_resumable_run(session, config.id)
        cursor: date | None = None

        if resumable is not None:
            cursor = resumable.last_successful_date
            scan_run = resumable
            scan_run.status = ScanStatus.RUNNING
            scan_run.error_message = None
            logger.info(
                "Resuming scan run %d for config %d from cursor %s",
                scan_run.id, config.id, cursor,
            )
        else:
            scan_run = ScanRun(
                search_config_id=config.id,
                status=ScanStatus.RUNNING,
            )
            session.add(scan_run)
            session.flush()
            logger.info("Started scan run %d for config %d", scan_run.id, config.id)

        remaining_dates = _dates_after_cursor(all_dates, cursor)
        logger.info(
            "Scanning %d date(s) for config %d (origin=%s, dest=%s)",
            len(remaining_dates), config.id, config.origin, config.destination,
        )

        try:
            for flight_date in remaining_dates:
                # Outbound direction: origin → destination
                count_out = _search_and_store_oneway(
                    session, scan_run, config.origin, config.destination, flight_date
                )
                random_delay()

                # Return direction: destination → origin
                count_ret = _search_and_store_oneway(
                    session, scan_run, config.destination, config.origin, flight_date
                )
                random_delay()

                scan_run.last_successful_date = date.fromisoformat(flight_date)
                session.flush()
                logger.debug(
                    "Date %s: stored %d outbound + %d return snapshots",
                    flight_date, count_out, count_ret,
                )

            scan_run.status = ScanStatus.COMPLETED
            scan_run.completed_at = datetime.now(tz=timezone.utc)
            logger.info("Scan run %d completed", scan_run.id)

        except Exception as exc:
            scan_run.status = ScanStatus.FAILED
            scan_run.error_message = str(exc)
            logger.error("Scan run %d failed: %s", scan_run.id, exc)
            raise

        # Roundtrip phase (no-op for fast-flights backend)
        _run_roundtrip_phase(session, scan_run, config, outbound_dates, return_dates)


def _find_resumable_run(session: Session, config_id: int) -> ScanRun | None:
    """Find today's failed/running ScanRun for this config to resume from."""
    today = datetime.now(tz=timezone.utc).date()
    result = session.scalars(
        select(ScanRun)
        .where(ScanRun.search_config_id == config_id)
        .where(ScanRun.status.in_([ScanStatus.FAILED, ScanStatus.RUNNING]))
        .order_by(ScanRun.started_at.desc())
        .limit(1)
    ).first()
    if result is None:
        return None
    run_date = result.started_at.date() if result.started_at.tzinfo else result.started_at.date()
    if run_date == today:
        return result
    return None


def _dates_after_cursor(dates: list[str], cursor: date | None) -> list[str]:
    """Return dates strictly after the cursor date. If cursor is None, return all."""
    if cursor is None:
        return dates
    return [d for d in dates if date.fromisoformat(d) > cursor]


def _search_and_store_oneway(
    session: Session,
    scan_run: ScanRun,
    origin: str,
    destination: str,
    flight_date: str,
) -> int:
    """Run one-way search, convert FlightResult→PriceSnapshot, bulk insert. Returns count stored."""
    results = search_one_way(origin, destination, flight_date)
    if not results:
        logger.debug("No results for %s→%s on %s", origin, destination, flight_date)
        return 0
    snapshots = [
        _flight_result_to_snapshot(r, scan_run.id, SearchType.ONEWAY)
        for r in results
    ]
    session.add_all(snapshots)
    return len(snapshots)


def _flight_result_to_snapshot(
    result: FlightResult,
    scan_run_id: int,
    search_type: SearchType,
) -> PriceSnapshot:
    """Convert a FlightResult dataclass to a PriceSnapshot ORM instance."""
    flight_date = date.fromisoformat(result.date)
    dep_hour, dep_min = map(int, result.departure_time.split(":"))
    arr_hour, arr_min = map(int, result.arrival_time.split(":"))
    departure_dt = datetime(flight_date.year, flight_date.month, flight_date.day, dep_hour, dep_min, tzinfo=timezone.utc)
    arrival_dt = datetime(flight_date.year, flight_date.month, flight_date.day, arr_hour, arr_min, tzinfo=timezone.utc)
    return PriceSnapshot(
        scan_run_id=scan_run_id,
        origin=result.origin,
        destination=result.destination,
        flight_date=flight_date,
        flight_code=result.airline,
        departure_time=departure_dt,
        arrival_time=arrival_dt,
        duration_min=result.duration_min,
        stops=result.stops,
        brand="ECONOMY",
        price=Decimal(result.price),
        currency="BRL",
        search_type=search_type,
        fetched_at=result.fetched_at.replace(tzinfo=timezone.utc) if result.fetched_at.tzinfo is None else result.fetched_at,
    )


def _run_roundtrip_phase(
    session: Session,
    scan_run: ScanRun,
    config: SearchConfig,
    outbound_dates: list[str],
    return_dates: list[str],
) -> int:
    """Roundtrip search phase.

    Currently a no-op for fast-flights backend (roundtrip = 2x one-way, already covered
    by the one-way phase which searches all dates in both directions).
    Ready for LATAM Playwright backend which returns different roundtrip pricing.

    TODO: implement LATAM-specific roundtrip search using generate_pairs() +
    search_latam_roundtrip() when Option C backend is added.
    """
    return 0
