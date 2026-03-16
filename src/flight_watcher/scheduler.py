import logging
import os
from typing import Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_SUBMITTED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import timezone

from flight_watcher.db import get_database_url
from flight_watcher.scanner_state import ScannerStatus, get_scanner_state

logger = logging.getLogger(__name__)

SCAN_INTERVAL_MINUTES = int(os.environ.get("SCAN_INTERVAL_MINUTES", "60"))
RETRY_MAX_ATTEMPTS = int(os.environ.get("RETRY_MAX_ATTEMPTS", "24"))
RETRY_INTERVAL_MINUTES = int(os.environ.get("RETRY_INTERVAL_MINUTES", "60"))

_scheduler: Optional[BackgroundScheduler] = None


def create_scheduler() -> BackgroundScheduler:
    """Create and configure a BackgroundScheduler with PostgreSQL job store."""
    jobstores = {
        "default": SQLAlchemyJobStore(
            url=get_database_url(),
            tablename="apscheduler_jobs",
        )
    }
    executors = {
        "default": ThreadPoolExecutor(max_workers=4),
    }
    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": 300,
    }
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=timezone.utc,
    )
    scheduler.add_listener(_on_job_submitted, EVENT_JOB_SUBMITTED)
    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return scheduler


def get_scheduler() -> BackgroundScheduler:
    """Return the scheduler singleton, creating it on first call."""
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


def _on_job_submitted(event) -> None:
    get_scanner_state().status = ScannerStatus.SCANNING
    logger.info("Job %s submitted, scanner scanning", event.job_id)


def _on_job_executed(event) -> None:
    get_scanner_state().status = ScannerStatus.IDLE
    logger.info("Job %s executed successfully (retval=%r)", event.job_id, event.retval)


def _on_job_error(event) -> None:
    get_scanner_state().status = ScannerStatus.IDLE
    logger.error(
        "Job %s raised an exception: %s\n%s",
        event.job_id,
        event.exception,
        event.traceback or "",
    )


def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler = get_scheduler()
    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler() -> None:
    """Shut down the scheduler and reset the singleton."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped")
        _scheduler = None


def register_scan_job() -> None:
    """Register the periodic scan job with the scheduler."""
    from apscheduler.jobstores.base import JobLookupError
    from flight_watcher.orchestrator import run_all_scans

    scheduler = get_scheduler()
    try:
        scheduler.remove_job("daily_scan")
    except JobLookupError:
        pass
    existing = scheduler.get_job("scheduled_scan")
    if existing is not None:
        existing_minutes = existing.trigger.interval.total_seconds() / 60
        if existing_minutes == SCAN_INTERVAL_MINUTES:
            logger.debug("scan job already scheduled with same interval, skipping re-registration")
            return
        # Interval changed — fall through to add_job(replace_existing=True)
    scheduler.add_job(
        run_all_scans,
        trigger="interval",
        minutes=SCAN_INTERVAL_MINUTES,
        id="scheduled_scan",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=300,
    )
    logger.info(
        "Registered scheduled_scan job (every %d min)", SCAN_INTERVAL_MINUTES
    )


def _retry_job_id(config_id: int) -> str:
    return f"retry_config_{config_id}"


def register_retry_job(config_id: int) -> None:
    """Register an hourly retry job for the given config."""
    from flight_watcher.orchestrator import run_retry_scan

    scheduler = get_scheduler()
    existing = scheduler.get_job(_retry_job_id(config_id))
    if existing is not None:
        existing_minutes = existing.trigger.interval.total_seconds() / 60
        if existing_minutes == RETRY_INTERVAL_MINUTES:
            logger.debug("retry job for config %d already scheduled with same interval, skipping re-registration", config_id)
            return
        # Interval changed — fall through to add_job(replace_existing=True)
    scheduler.add_job(
        run_retry_scan,
        trigger="interval",
        minutes=RETRY_INTERVAL_MINUTES,
        id=_retry_job_id(config_id),
        kwargs={"config_id": config_id},
        replace_existing=True,
        misfire_grace_time=300,
        max_instances=1,
    )
    logger.info(
        "Registered retry job for config %d (every %d min)",
        config_id,
        RETRY_INTERVAL_MINUTES,
    )


def cancel_retry_job(config_id: int) -> None:
    """Cancel the hourly retry job for the given config, if it exists."""
    from apscheduler.jobstores.base import JobLookupError

    try:
        get_scheduler().remove_job(_retry_job_id(config_id))
        logger.info("Cancelled retry job for config %d", config_id)
    except JobLookupError:
        pass
