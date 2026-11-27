"""Crawler configuration, execution and results."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.core.url_utils import validate_target_url
from app.models.inventory import Crawl, CrawlObservation
from app.services.crawler import DEFAULT_CONFIG
from app.services.jobs import enqueue

router = APIRouter(prefix="/crawler", tags=["crawler"])


@router.get("/config-defaults")
def config_defaults():
    clean = dict(DEFAULT_CONFIG)
    clean.pop("auth_headers", None)
    return clean


@router.post("/start", status_code=202)
def start_crawl(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    requested = payload.get("config") or {}
    config = {key: value for key, value in requested.items()
              if key not in {"allow_private", "auth_headers"}}
    config["allow_private"] = False
    config["auth_headers"] = {}
    start_url = config.get("start_url") or ""
    seeds = config.get("seed_urls") or []
    if not start_url and not seeds:
        raise HTTPException(400, "Provide start_url or seed_urls")
    for url in ([start_url] if start_url else []) + list(seeds)[:50]:
        try:
            validate_target_url(url, allow_private=False)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
    job = enqueue(
        db, "crawl", payload.get("name") or "Site crawl",
        {"config": config, "name": payload.get("name")},
        project_id=project.id, organization_id=project.organization_id, created_by=user.id,
    )
    db.commit()
    return {"job_id": job.id, "status": "queued", "note": "Crawler respects robots.txt by default and can be cancelled from the Jobs screen."}


@router.get("/runs")
def list_crawls(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(Crawl).where(Crawl.project_id == project.id), offset, limit, Crawl.id.desc())
    cols = ["id", "name", "status", "discovered", "crawled", "failed", "excluded", "started_at", "finished_at", "summary", "data_kind"]
    return paged([serialize(i, cols) for i in items], total, offset, limit)


@router.get("/runs/{crawl_id}")
def get_crawl(crawl_id: int, db: DB, project: ProjectDep):
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project.id:
        raise HTTPException(404, "Crawl not found")
    return serialize(crawl, ["id", "name", "config", "status", "discovered", "crawled", "failed", "excluded", "summary", "started_at", "finished_at", "data_kind"])


@router.get("/runs/{crawl_id}/observations")
def observations(crawl_id: int, db: DB, project: ProjectDep, offset: int = 0, limit: int = 100, status: int | None = None):
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project.id:
        raise HTTPException(404, "Crawl not found")
    query = select(CrawlObservation).where(CrawlObservation.crawl_id == crawl_id)
    if status is not None:
        query = query.where(CrawlObservation.status_code == status)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, CrawlObservation.id)
    cols = ["id", "requested_url", "final_url", "status_code", "redirect_chain", "response_time_ms", "content_size", "error", "observed_at", "extracted"]
    return paged([serialize(i, cols) for i in items], total, offset, limit)


@router.get("/runs/{crawl_id}/export")
def export_observations(crawl_id: int, db: DB, project: ProjectDep, format: str = "csv"):
    crawl = db.get(Crawl, crawl_id)
    if crawl is None or crawl.project_id != project.id:
        raise HTTPException(404, "Crawl not found")
    rows = db.scalars(select(CrawlObservation).where(CrawlObservation.crawl_id == crawl_id).limit(200000)).all()
    cols = ["requested_url", "final_url", "status_code", "redirect_chain", "response_time_ms", "content_size", "error", "observed_at"]
    return download([serialize(r, cols) for r in rows], cols, f"crawl_observations_{crawl_id}", format)
