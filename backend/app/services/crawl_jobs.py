"""Background job handlers for crawling."""
from __future__ import annotations

from app.core.timeutil import iso, utcnow
from app.models.inventory import Crawl
from app.services.crawler import CrawlConfig, CrawlEngine
from app.services.jobs import is_cancelled, progress, register


@register("crawl")
def run_crawl_job(db_session_factory, job_id: int, payload: dict, project_id: int | None, organization_id: int | None):
    db = db_session_factory()
    try:
        db.flush()
        config = CrawlConfig.from_dict(payload.get("config") or {})
        crawl = Crawl(
            project_id=project_id, job_id=job_id,
            name=payload.get("name") or f"Crawl {config.start_url or 'inventory'}",
            config=config.as_dict(), status="running", started_at=iso(utcnow()),
            data_kind=config.mode,
        )
        db.add(crawl)
        db.commit()
        crawl_id = crawl.id
    finally:
        db.close()

    engine_db = db_session_factory()
    try:
        engine = CrawlEngine(
            db=engine_db, project_id=project_id, crawl_id=crawl_id, job_id=job_id,
            config=config,
            on_progress=lambda v, t, m: progress(job_id, v, t, m),
            cancelled=lambda: is_cancelled(job_id),
        )
        stats = engine.run()
    finally:
        engine_db.close()

    db = db_session_factory()
    try:
        crawl = db.get(Crawl, crawl_id)
        crawl.status = "cancelled" if is_cancelled(job_id) else "completed"
        crawl.discovered = stats["discovered"]
        crawl.crawled = stats["crawled"]
        crawl.failed = stats["failed"]
        crawl.excluded = stats["excluded"]
        crawl.summary = stats
        crawl.finished_at = iso(utcnow())
        db.commit()
    finally:
        db.close()
    return {"crawl_id": crawl_id, **stats}
