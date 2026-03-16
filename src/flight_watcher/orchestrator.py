import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from flight_watcher.date_expansion import expand_dates
from flight_watcher.db import get_session
from flight_watcher.delays import random_delay
from flight_watcher.errors import SearchFailedError, get_retry_strategy
from flight_watcher.models import (
    FlightResult,
    PriceSnapshot,
    ScanRun,
    ScanStatus,
    SearchConfig,
    SearchResult,
    SearchType,
)
from flight_watcher.scanner import search_one_way

logger = logging.getLogger(__name__)


def run_all_scans() -> None:
    """Top-level entry: load active configs, run scan for each."""
    with get_session() as session:
        rows = session.scalars(
            select(SearchConfig).where(SearchConfig.active == True)  # noqa: E712
        ).all()
        # Extract plain scalars while session is open to avoid DetachedInstanceError
        configs = [
            {
                "id": r.id,
                "origin": r.origin,
                "destination": r.destination,
                "must_arrive_by": r.must_arrive_by,
                "must_stay_until": r.must_stay_until,
                "max_trip_days": r.max_trip_days,
                "min_trip_days": r.min_trip_days,
                "retry_count": r.retry_count,
            }
            for r in rows
        ]
    logger.info("Running scans for %d active config(s)", len(configs))
    from flight_watcher.scheduler import cancel_retry_job, register_retry_job

    for config in configs:
        try:
            run_scan(config)
            cancel_retry_job(config["id"])
            with get_session() as session:
                config_row = session.get(SearchConfig, config["id"])
                if config_row is not None:
                    if config["retry_count"] > 0:
                        logger.info(
                            "Daily scan succeeded for config %d, reset retry_count",
                            config["id"],
                        )
                    config_row.retry_count = 0
        except Exception:  # noqa: BLE001
            # Detailed error is already logged inside run_scan; catch here only to continue
            register_retry_job(config["id"])


def run_retry_scan(config_id: int) -> None:
    """Retry job callable: runs a scan for a single config, managing retry state."""
    from flight_watcher.scheduler import (
        cancel_retry_job,
        RETRY_MAX_ATTEMPTS,
        RETRY_INTERVAL_MINUTES,
    )

    with get_session() as session:
        config_row = session.get(SearchConfig, config_id)
        if config_row is None:
            logger.warning("run_retry_scan: config %d not found, skipping", config_id)
            return
        if config_row.needs_attention:
            logger.warning(
                "run_retry_scan: config %d is needs_attention, skipping", config_id
            )
            return
        config = {
            "id": config_row.id,
            "origin": config_row.origin,
            "destination": config_row.destination,
            "must_arrive_by": config_row.must_arrive_by,
            "must_stay_until": config_row.must_stay_until,
            "max_trip_days": config_row.max_trip_days,
            "min_trip_days": config_row.min_trip_days,
        }

    try:
        run_scan(config)
    except Exception:  # noqa: BLE001
        with get_session() as session:
            config_row = session.get(SearchConfig, config_id)
            if config_row is not None:
                config_row.retry_count += 1
                if config_row.retry_count >= RETRY_MAX_ATTEMPTS:
                    config_row.needs_attention = True
                    cancel_retry_job(config_id)
                    logger.warning(
                        "Config %d marked as needs_attention after %d retries",
                        config_id,
                        config_row.retry_count,
                    )
                else:
                    logger.info(
                        "Retry %d/%d failed for config %d, next retry in %dmin",
                        config_row.retry_count,
                        RETRY_MAX_ATTEMPTS,
                        config_id,
                        RETRY_INTERVAL_MINUTES,
                    )
        return

    # Success path
    with get_session() as session:
        config_row = session.get(SearchConfig, config_id)
        if config_row is not None:
            config_row.retry_count = 0
    cancel_retry_job(config_id)
    logger.info("Retry succeeded for config %d, resuming daily schedule", config_id)


def run_scan(config: dict) -> None:
    """Run a full scan for one SearchConfig.

    Args:
        config: Plain dict with keys id, origin, destination, must_arrive_by,
                must_stay_until, max_trip_days. Using a dict (not ORM object)
                prevents DetachedInstanceError after the loading session closes.
    """
    outbound_dates, return_dates = expand_dates(
        config["must_arrive_by"], config["must_stay_until"], config["max_trip_days"],
        config.get("min_trip_days"),
    )
    all_dates = sorted(set(outbound_dates + return_dates))

    with get_session() as session:
        # Check for a resumable run (last 48h)
        resumable = _find_resumable_run(session, config["id"])
        cursor: date | None = None

        if resumable is not None:
            cursor = resumable.last_successful_date
            scan_run = resumable
            scan_run.status = ScanStatus.RUNNING
            scan_run.error_message = None
            session.commit()  # persist RUNNING transition before date loop
            logger.info(
                "Resuming scan run %d for config %d from cursor %s",
                scan_run.id,
                config["id"],
                cursor,
            )
        else:
            scan_run = ScanRun(
                search_config_id=config["id"],
                status=ScanStatus.RUNNING,
            )
            session.add(scan_run)
            session.flush()
            session.commit()  # commit before date loop so rollback doesn't undo the ScanRun insert
            logger.info("Started scan run %d for config %d", scan_run.id, config["id"])

        remaining_dates = _dates_after_cursor(all_dates, cursor)
        logger.info(
            "Scanning %d date(s) for config %d (origin=%s, dest=%s)",
            len(remaining_dates),
            config["id"],
            config["origin"],
            config["destination"],
        )

        try:
            for flight_date in remaining_dates:
                # Outbound direction: origin → destination
                result_out = _search_and_store_oneway(
                    session,
                    scan_run,
                    config["origin"],
                    config["destination"],
                    flight_date,
                )
                if not result_out.ok:
                    assert result_out.error_category is not None, "failure result must carry error_category"
                    strategy = get_retry_strategy(result_out.error_category)
                    if not strategy.skip_item:
                        raise SearchFailedError(
                            f"Search failed for {config['origin']}→{config['destination']}"
                            f" on {flight_date}: [{result_out.error_category}] {result_out.error}",
                            error_category=result_out.error_category,
                        )
                    logger.warning(
                        "Skipping outbound %s→%s on %s due to %s",
                        config["origin"],
                        config["destination"],
                        flight_date,
                        result_out.error_category,
                    )
                random_delay()

                # Return direction: destination → origin
                result_ret = _search_and_store_oneway(
                    session,
                    scan_run,
                    config["destination"],
                    config["origin"],
                    flight_date,
                )
                if not result_ret.ok:
                    assert result_ret.error_category is not None, "failure result must carry error_category"
                    strategy = get_retry_strategy(result_ret.error_category)
                    if not strategy.skip_item:
                        raise SearchFailedError(
                            f"Search failed for {config['destination']}→{config['origin']}"
                            f" on {flight_date}: [{result_ret.error_category}] {result_ret.error}",
                            error_category=result_ret.error_category,
                        )
                    logger.warning(
                        "Skipping return %s→%s on %s due to %s",
                        config["destination"],
                        config["origin"],
                        flight_date,
                        result_ret.error_category,
                    )
                random_delay()

                scan_run.last_successful_date = date.fromisoformat(flight_date)
                # Commit per-date so snapshots and cursor survive a mid-scan failure.
                # On retry, _dates_after_cursor skips already-committed dates.
                session.commit()
                logger.debug(
                    "Date %s: stored %d outbound + %d return snapshots",
                    flight_date,
                    result_out.data or 0,
                    result_ret.data or 0,
                )

            scan_run.status = ScanStatus.COMPLETED
            scan_run.completed_at = datetime.now(tz=timezone.utc)
            session.commit()  # persist COMPLETED status
            logger.info("Scan run %d completed", scan_run.id)

        except Exception as exc:
            session.rollback()  # discard uncommitted in-progress date work
            scan_run.status = ScanStatus.FAILED
            scan_run.error_message = str(exc)
            logger.error("Scan run %d failed: %s", scan_run.id, exc)
            session.commit()
            raise

        # Roundtrip phase (no-op for fast-flights backend)
        _run_roundtrip_phase(session, scan_run, config, outbound_dates, return_dates)


def _find_resumable_run(session: Session, config_id: int) -> ScanRun | None:
    """Find a recent failed/running ScanRun for this config to resume from.

    Looks back 48 hours to handle cross-midnight retries where a scan started
    late the previous day and is being retried the next day.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=48)
    return session.scalars(
        select(ScanRun)
        .where(ScanRun.search_config_id == config_id)
        .where(ScanRun.status.in_([ScanStatus.FAILED, ScanStatus.RUNNING]))
        .where(ScanRun.started_at >= cutoff)
        .order_by(ScanRun.started_at.desc())
        .limit(1)
    ).first()


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
) -> SearchResult[int]:
    """Run one-way search, convert FlightResult→PriceSnapshot, bulk insert. Returns SearchResult with count stored."""
    result = search_one_way(origin, destination, flight_date)
    if not result.ok:
        logger.warning(
            "Search failed for %s→%s on %s: [%s] %s",
            origin,
            destination,
            flight_date,
            result.error_category,
            result.error,
        )
        return SearchResult(
            ok=False,
            data=0,
            error=result.error,
            error_category=result.error_category,
            hint=result.hint,
            duration_sec=result.duration_sec,
        )
    if not result.data:
        logger.debug("No results for %s→%s on %s", origin, destination, flight_date)
        return SearchResult.success(0, duration_sec=result.duration_sec)
    snapshots = [
        _flight_result_to_snapshot(r, scan_run.id, SearchType.ONEWAY)
        for r in result.data
    ]
    session.add_all(snapshots)
    return SearchResult.success(len(snapshots), duration_sec=result.duration_sec)


def _flight_result_to_snapshot(
    result: FlightResult,
    scan_run_id: int,
    search_type: SearchType,
) -> PriceSnapshot:
    """Convert a FlightResult dataclass to a PriceSnapshot ORM instance."""
    flight_date = date.fromisoformat(result.date)
    dep_hour, dep_min = map(int, result.departure_time.split(":"))
    arr_hour, arr_min = map(int, result.arrival_time.split(":"))
    departure_dt = datetime(
        flight_date.year,
        flight_date.month,
        flight_date.day,
        dep_hour,
        dep_min,
        tzinfo=timezone.utc,
    )
    arrival_dt = datetime(
        flight_date.year,
        flight_date.month,
        flight_date.day,
        arr_hour,
        arr_min,
        tzinfo=timezone.utc,
    )
    if arrival_dt < departure_dt:
        arrival_dt += timedelta(days=1)
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
        fetched_at=result.fetched_at.replace(tzinfo=timezone.utc)
        if result.fetched_at.tzinfo is None
        else result.fetched_at,
    )


def _run_roundtrip_phase(
    session: Session,
    scan_run: ScanRun,
    config: dict,
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
