"""Yearly Rate Scheduler
---------------------
File: backend/yearly_rate_scheduler.py

Synchronizes yearly-rate records for one configured user:
- immediately when initialized (unless disabled by configuration)
- every six hours
- uses Africa/Mogadishu for scheduler and logging timestamps

Financial-year boundaries are delegated to app.routes helpers and must be
October 10 inclusive through October 10 of the next year exclusive.

IMPORTANT: This is an in-process scheduler. It works only while the Flask
process stays alive. For serverless deployments (including Vercel Functions),
use a persistent worker or an external cron/scheduled function instead.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

try:
    from apscheduler.events import (
        EVENT_JOB_ERROR,
        EVENT_JOB_EXECUTED,
        EVENT_JOB_MISSED,
    )
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError as exc:  # Keep import safe; fail clearly when enabled.
    BackgroundScheduler = None
    EVENT_JOB_ERROR = EVENT_JOB_EXECUTED = EVENT_JOB_MISSED = 0
    _APSCHEDULER_IMPORT_ERROR = exc
else:
    _APSCHEDULER_IMPORT_ERROR = None


TIMEZONE = ZoneInfo("Africa/Mogadishu")
TARGET_USER_ID = "6a3fb30b7e3a09592080f815"
SCHEDULER_JOB_ID = "yearly_rate_sync"
SYNC_INTERVAL_HOURS = 6

_yearly_rate_scheduler = None
_scheduler_lock = threading.RLock()
_sync_execution_lock = threading.Lock()


def _scheduler_logger():
    return logging.getLogger("yearly_rate_scheduler")


def _scheduler_event_listener(event):
    """Log APScheduler job outcomes without swallowing job exceptions."""
    logger = _scheduler_logger()
    job_id = getattr(event, "job_id", SCHEDULER_JOB_ID)

    if event.code == EVENT_JOB_EXECUTED:
        logger.info("Yearly-rate job executed successfully. Job ID=%s", job_id)
    elif event.code == EVENT_JOB_ERROR:
        logger.error(
            "Yearly-rate job failed. Job ID=%s Exception=%s",
            job_id,
            getattr(event, "exception", None),
        )
    elif event.code == EVENT_JOB_MISSED:
        logger.warning(
            "Yearly-rate job missed its scheduled execution. Job ID=%s", job_id
        )


def _load_yearly_rate_functions():
    """Import financial functions lazily to reduce circular-import risk."""
    from app.routes import (
        _yr_financial_start,
        _yr_next_year,
        _yr_year_label,
        diagnose_yearly_rate_transactions,
        sync_yearly_rates_for_user,
    )

    return (
        sync_yearly_rates_for_user,
        diagnose_yearly_rate_transactions,
        _yr_financial_start,
        _yr_next_year,
        _yr_year_label,
    )


def _get_current_financial_period():
    """Return [October 10, next October 10) for today's Mogadishu date."""
    (
        _sync_function,
        _diagnose_function,
        financial_start,
        next_year,
        year_label,
    ) = _load_yearly_rate_functions()

    today = datetime.now(TIMEZONE).date()
    start = financial_start(today)
    end = next_year(start)

    # Guard against an accidental helper change that reintroduces October 9.
    expected_start_day = 10
    if start.month != 10 or start.day != expected_start_day:
        raise ValueError(
            f"Financial-year start must be October 10; received {start.isoformat()}"
        )
    if end.month != 10 or end.day != expected_start_day or end <= start:
        raise ValueError(
            f"Financial-year end must be October 10 of the following year; "
            f"received {end.isoformat()}"
        )

    return {
        "today": today,
        "start": start,
        "end": end,
        "year_label": year_label(start),
    }


def run_yearly_rate_sync(app):
    """Synchronize yearly-rate records and diagnose the current financial year."""
    logger = getattr(app, "logger", _scheduler_logger())
    started_at = datetime.now(TIMEZONE)

    if not _sync_execution_lock.acquire(blocking=False):
        logger.warning(
            "Yearly-rate sync skipped because another sync is running. User=%s",
            TARGET_USER_ID,
        )
        return {
            "success": False,
            "skipped": True,
            "reason": "sync_already_running",
            "user_id": TARGET_USER_ID,
        }

    try:
        with app.app_context():
            logger.info(
                "Starting yearly-rate synchronization. User=%s Started=%s",
                TARGET_USER_ID,
                started_at.isoformat(),
            )

            (
                sync_function,
                diagnose_function,
                _financial_start,
                _next_year,
                _year_label,
            ) = _load_yearly_rate_functions()

            sync_result = sync_function(user_id=TARGET_USER_ID)
            if not isinstance(sync_result, dict):
                raise RuntimeError(
                    "sync_yearly_rates_for_user() must return a dictionary."
                )

            returned_user_id = str(sync_result.get("user_id", ""))
            if returned_user_id != TARGET_USER_ID:
                raise RuntimeError(
                    "Yearly-rate sync returned an unexpected user ID: "
                    f"{returned_user_id!r}"
                )

            logger.info(
                "Yearly-rate synchronization completed. User=%s Created=%s "
                "Updated=%s Unchanged=%s CurrentYear=%s",
                TARGET_USER_ID,
                sync_result.get("created", 0),
                sync_result.get("updated", 0),
                sync_result.get("unchanged", 0),
                sync_result.get("current_year"),
            )

            # Reuse the same authoritative helpers as the routes. The end date
            # is exclusive: Oct 10 next year is the boundary, not an extra day.
            period = _get_current_financial_period()
            diagnostic_result = diagnose_function(
                user_id=TARGET_USER_ID,
                start=period["start"],
                end=period["end"],
            )
            if not isinstance(diagnostic_result, dict):
                raise RuntimeError(
                    "diagnose_yearly_rate_transactions() must return a dictionary."
                )

            logger.info(
                "Yearly-rate diagnostics. User=%s Year=%s Start=%s EndExclusive=%s "
                "Income=%s Expenses=%s SavingsDeposits=%s SavingsWithdrawals=%s "
                "UnknownTransfers=%s Unclassified=%s",
                TARGET_USER_ID,
                period["year_label"],
                period["start"].isoformat(),
                period["end"].isoformat(),
                diagnostic_result.get("income_total", 0),
                diagnostic_result.get("expense_total", 0),
                diagnostic_result.get("savings_to_total", 0),
                diagnostic_result.get("savings_from_total", 0),
                diagnostic_result.get("unknown_transfer_total", 0),
                diagnostic_result.get("unclassified_total", 0),
            )

            completed_at = datetime.now(TIMEZONE)
            result = {
                "success": True,
                "user_id": TARGET_USER_ID,
                "started_at": started_at.isoformat(),
                "completed_at": completed_at.isoformat(),
                "current_year": period["year_label"],
                "financial_period": {
                    "start": period["start"].isoformat(),
                    "end_exclusive": period["end"].isoformat(),
                    "timezone": str(TIMEZONE),
                },
                "sync": sync_result,
                "diagnostics": diagnostic_result,
            }

            logger.info(
                "Yearly-rate scheduler task completed. User=%s DurationSeconds=%.2f",
                TARGET_USER_ID,
                (completed_at - started_at).total_seconds(),
            )
            return result

    except Exception:
        logger.exception(
            "Yearly-rate synchronization failed. User=%s Started=%s",
            TARGET_USER_ID,
            started_at.isoformat(),
        )
        raise
    finally:
        _sync_execution_lock.release()


def init_yearly_rate_scheduler(app):
    """Initialize one scheduler per process and optionally run once immediately.

    Optional Flask config:
      YEARLY_RATE_SCHEDULER_ENABLED: bool (default True)
      YEARLY_RATE_SCHEDULER_RUN_ON_START: bool (default True)
    """
    global _yearly_rate_scheduler

    logger = getattr(app, "logger", _scheduler_logger())

    if app.config.get("TESTING", False):
        logger.info("Yearly-rate scheduler disabled because TESTING=True.")
        return None

    if not app.config.get("YEARLY_RATE_SCHEDULER_ENABLED", True):
        logger.info("Yearly-rate scheduler disabled by configuration.")
        return None

    if BackgroundScheduler is None:
        raise RuntimeError(
            "APScheduler is required for the yearly-rate scheduler. "
            "Install it with: pip install APScheduler"
        ) from _APSCHEDULER_IMPORT_ERROR

    # In Flask's debug reloader, start only in the serving child process.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        logger.info("Scheduler not started in Werkzeug reloader parent process.")
        return None

    with _scheduler_lock:
        if _yearly_rate_scheduler is not None and _yearly_rate_scheduler.running:
            logger.debug("Yearly-rate scheduler is already running.")
            return _yearly_rate_scheduler

        scheduler = BackgroundScheduler(
            timezone=TIMEZONE,
            daemon=True,
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 3600,
            },
        )
        scheduler.add_job(
            func=run_yearly_rate_sync,
            trigger="interval",
            hours=SYNC_INTERVAL_HOURS,
            args=[app],
            id=SCHEDULER_JOB_ID,
            name="Sync configured user's yearly rates",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        scheduler.add_listener(
            _scheduler_event_listener,
            EVENT_JOB_EXECUTED | EVENT_JOB_ERROR | EVENT_JOB_MISSED,
        )

        try:
            scheduler.start()
        except Exception:
            logger.exception("Could not start yearly-rate scheduler.")
            try:
                scheduler.shutdown(wait=False)
            except Exception:
                logger.debug(
                    "Scheduler cleanup after startup failure also failed.",
                    exc_info=True,
                )
            raise

        _yearly_rate_scheduler = scheduler
        logger.info(
            "Yearly-rate scheduler started. Timezone=%s IntervalHours=%s TargetUser=%s",
            TIMEZONE,
            SYNC_INTERVAL_HOURS,
            TARGET_USER_ID,
        )

    # Run immediately outside the scheduler lock. The execution lock prevents
    # this call from overlapping with a scheduled execution in this process.
    if app.config.get("YEARLY_RATE_SCHEDULER_RUN_ON_START", True):
        try:
            run_yearly_rate_sync(app)
        except Exception:
            logger.exception(
                "Initial yearly-rate sync failed. The recurring job remains scheduled."
            )

    return _yearly_rate_scheduler


def shutdown_yearly_rate_scheduler(wait=False):
    """Gracefully stop the in-process scheduler."""
    global _yearly_rate_scheduler

    with _scheduler_lock:
        scheduler = _yearly_rate_scheduler
        if scheduler is None:
            return
        try:
            if scheduler.running:
                scheduler.shutdown(wait=wait)
        except Exception:
            _scheduler_logger().exception("Error shutting down yearly-rate scheduler.")
        finally:
            _yearly_rate_scheduler = None


def get_yearly_rate_scheduler_status():
    """Return scheduler state and the next scheduled execution time."""
    scheduler = _yearly_rate_scheduler
    if scheduler is None:
        return {
            "running": False,
            "timezone": str(TIMEZONE),
            "interval_hours": SYNC_INTERVAL_HOURS,
            "target_user_id": TARGET_USER_ID,
            "next_run_time": None,
            "job_id": SCHEDULER_JOB_ID,
        }

    job = scheduler.get_job(SCHEDULER_JOB_ID)
    next_run_time = (
        job.next_run_time.isoformat() if job and job.next_run_time else None
    )
    return {
        "running": scheduler.running,
        "timezone": str(TIMEZONE),
        "interval_hours": SYNC_INTERVAL_HOURS,
        "target_user_id": TARGET_USER_ID,
        "next_run_time": next_run_time,
        "job_id": SCHEDULER_JOB_ID,
    }
