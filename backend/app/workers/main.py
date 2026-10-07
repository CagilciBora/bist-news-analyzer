"""Worker process: runs scheduled collection (and later analysis/report) jobs.

Usage:
    uv run python -m app.workers.main            # run the scheduler (blocks)
    uv run python -m app.workers.main --once rss # run one job now and exit (rss | kap)
"""

import argparse
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers import jobs

logger = logging.getLogger(__name__)
TIMEZONE = ZoneInfo("Europe/Istanbul")

JOBS: dict[str, Callable[[], Any]] = {
    "rss": jobs.collect_rss,
    "kap": jobs.collect_kap,
}


def build_scheduler() -> BlockingScheduler:
    settings = get_settings()
    scheduler = BlockingScheduler(timezone=TIMEZONE)
    now = datetime.now(TIMEZONE)
    intervals = {"rss": settings.rss_interval_minutes, "kap": settings.kap_interval_minutes}
    for job_id, minutes in intervals.items():
        scheduler.add_job(
            JOBS[job_id],
            "interval",
            minutes=minutes,
            id=job_id,
            next_run_time=now,  # also run once at startup
            max_instances=1,
            coalesce=True,
        )
    return scheduler


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--once", choices=sorted(JOBS), help="run a single job immediately and exit")
    args = parser.parse_args()

    configure_logging(get_settings().log_level)
    if args.once:
        JOBS[args.once]()
        return

    scheduler = build_scheduler()
    logger.info("Worker started with jobs: %s", [job.id for job in scheduler.get_jobs()])
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Worker stopped")


if __name__ == "__main__":
    main()
