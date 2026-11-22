"""Shared URL inventory with filtering, pagination, column selection and exports."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.inventory import CrawlObservation, UrlRecord

router = APIRouter(prefix="/inventory", tags=["inventory"])

COLUMNS = [
    "id", "url", "normalized_url", "data_kind", "sources", "crawled", "http_status",
    "title", "meta_description", "canonical", "indexable", "robots_allowed",
    "word_count", "response_time_ms", "internal_inlinks", "internal_outlinks",
    "image_count", "images_missing_alt", "schema_types", "crawl_depth", "page_type",
    "in_sitemap", "clicks", "impressions", "sessions", "conversions", "revenue",
    "referring_domains", "last_seen", "notes",
]


def build_query(db, project_id, q, status, page_type, indexable, orphan, data_kind, min_clicks, min_revenue, in_sitemap):
    query = select(UrlRecord).where(UrlRecord.project_id == project_id)
    if q:
        pattern = f"%{q}%"
        query = query.where(UrlRecord.url.ilike(pattern) | UrlRecord.title.ilike(pattern))
    if status is not None:
        query = query.where(UrlRecord.http_status == status)
    if page_type:
        query = query.where(UrlRecord.page_type == page_type)
    if indexable is not None:
        query = query.where(UrlRecord.indexable.is_(bool(int(indexable))))
    if orphan:
        query = query.where(UrlRecord.internal_inlinks == 0)
    if data_kind:
        query = query.where(UrlRecord.data_kind == data_kind)
    if min_clicks is not None:
        query = query.where(UrlRecord.clicks >= min_clicks)
    if min_revenue is not None:
        query = query.where(UrlRecord.revenue >= min_revenue)
    if in_sitemap is not None:
        query = query.where(UrlRecord.in_sitemap.is_(bool(int(in_sitemap))))
    return query


def selected_columns(columns: str | None) -> list[str]:
    if not columns:
        return COLUMNS
    chosen = [c.strip() for c in columns.split(",") if c.strip() in COLUMNS]
    return chosen or COLUMNS


@router.get("/urls")
def list_urls(
    db: DB,
    project: ProjectDep,
    q: str | None = None,
    status: int | None = None,
    page_type: str | None = None,
    indexable: int | None = Query(None, ge=0, le=1),
    orphan: bool = False,
    data_kind: str | None = None,
    min_clicks: float | None = None,
    min_revenue: float | None = None,
    in_sitemap: int | None = Query(None, ge=0, le=1),
    offset: int = 0,
    limit: int = Query(50, ge=1, le=500),
    columns: str | None = None,
):
    query = build_query(db, project.id, q, status, page_type, indexable, orphan,
                        data_kind, min_clicks, min_revenue, in_sitemap)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = db.scalars(query.order_by(UrlRecord.id).offset(offset).limit(limit)).all()
    cols = selected_columns(columns)
    return paged([serialize(r, cols) for r in rows], total, offset, limit)


@router.get("/urls/{url_id}")
def get_url(url_id: int, db: DB, project: ProjectDep):
    record = db.get(UrlRecord, url_id)
    if record is None or record.project_id != project.id:
        raise HTTPException(404, "URL not found")
    data = serialize(record, COLUMNS + ["id", "content_type", "content_size", "h1", "h2", "meta_robots", "x_robots_tag", "redirect_chain", "redirected_to", "hreflang", "og", "pagination", "importance", "template"])
    observations = db.scalars(select(CrawlObservation).where(
        CrawlObservation.project_id == project.id,
        CrawlObservation.requested_url == record.url,
    ).order_by(CrawlObservation.id.desc()).limit(5)).all()
    data["raw_observations"] = [serialize(o, ["id", "crawl_id", "status_code", "headers", "redirect_chain", "error", "observed_at"]) for o in observations]
    return data


@router.patch("/urls/{url_id}")
def update_url(url_id: int, payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    record = db.get(UrlRecord, url_id)
    if record is None or record.project_id != project.id:
        raise HTTPException(404, "URL not found")
    for key in ("page_type", "template", "importance", "notes", "clicks", "impressions", "sessions", "conversions", "revenue", "referring_domains"):
        if key in payload:
            setattr(record, key, payload[key])
    db.commit()
    return {"success": True}


@router.get("/export")
def export_urls(
    db: DB,
    project: ProjectDep,
    format: str = "csv",
    columns: str | None = None,
    q: str | None = None,
    status: int | None = None,
    page_type: str | None = None,
    data_kind: str | None = None,
):
    query = build_query(db, project.id, q, status, page_type, None, False, data_kind, None, None, None)
    rows = db.scalars(query.order_by(UrlRecord.id).limit(200000)).all()
    cols = selected_columns(columns)
    return download([serialize(r, cols) for r in rows], cols, f"url_inventory_project_{project.id}", format)


@router.get("/summary")
def inventory_summary(db: DB, project: ProjectDep):
    rows = db.execute(
        select(UrlRecord.http_status, func.count()).where(UrlRecord.project_id == project.id).group_by(UrlRecord.http_status)
    ).all()
    types = db.execute(
        select(UrlRecord.page_type, func.count()).where(UrlRecord.project_id == project.id).group_by(UrlRecord.page_type)
    ).all()
    kinds = db.execute(
        select(UrlRecord.data_kind, func.count()).where(UrlRecord.project_id == project.id).group_by(UrlRecord.data_kind)
    ).all()
    return {
        "total": db.scalar(select(func.count()).where(UrlRecord.project_id == project.id)),
        "by_status": {str(k): v for k, v in rows},
        "by_page_type": {str(k): v for k, v in types},
        "by_data_kind": {str(k): v for k, v in kinds},
    }
