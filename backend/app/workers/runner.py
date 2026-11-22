"""Poll the database for queued jobs and execute registered handlers.

Run with: python -m app.workers.runner
"""
from __future__ import annotations

import logging
import time

from app.core.config import settings
from app.db.session import init_db
from app.services import jobs  # noqa: F401  registers handlers via imports below
from app.services import (  # noqa: F401
    crawl_jobs, analysis_jobs, demo_jobs, import_jobs, keyword_jobs, public_audit_jobs,
    workflow_jobs,
)
from app.services.jobs import claim_next, run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("serpscope.worker")


def main() -> None:
    init_db()
    logger.info("Worker started; waiting for jobs")
    last_schedule_check = 0.0
    while True:
        if time.time() - last_schedule_check > 60:
            from app.services.jobs import enqueue

            db = None
            try:
                from app.db.session import SessionLocal

                db = SessionLocal()
                enqueue(db, "scheduler_tick", "Scheduled workflow check", {}, created_by=None)
                db.commit()
            finally:
                if db:
                    db.close()
            last_schedule_check = time.time()
        job_id = claim_next()
        if job_id is None:
            time.sleep(settings.job_poll_seconds)
            continue
        logger.info("Running job %s", job_id)
        result = run_job(job_id)
        logger.info("Finished job %s: %s", job_id, str(result)[:300])


if __name__ == "__main__":
    main()
