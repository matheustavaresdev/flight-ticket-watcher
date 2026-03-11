import logging
import os
from typing import Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import timezone

from flight_watcher.db import get_database_url

logger = logging.getLogger(__name__)

SCAN_HOUR_UTC = int(os.environ.get("SCAN_HOUR_UTC", "3"))

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
    scheduler.add_listener(_on_job_executed, EVENT_JOB_EXECUTED)
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return scheduler


def get_scheduler() -> BackgroundScheduler:
    """Return the scheduler singleton, creating it on first call."""
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


def _on_job_executed(event) -> None:
    logger.info("Job %s executed successfully (retval=%r)", event.job_id, event.retval)


def _on_job_error(event) -> None:
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
    """Register the daily scan job with the scheduler."""
    from flight_watcher.orchestrator import run_all_scans
    scheduler = get_scheduler()
    scheduler.add_job(
        run_all_scans,
        trigger="cron",
        hour=SCAN_HOUR_UTC,
        id="daily_scan",
        replace_existing=True,
        jitter=1800,
    )
    logger.info("Registered daily_scan job at hour=%d UTC (±30min jitter)", SCAN_HOUR_UTC)
