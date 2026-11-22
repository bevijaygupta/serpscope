"""Orphan page detection, classification and export."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.analysis import OrphanRecord
from app.services.jobs import enqueue

router = APIRouter(prefix="/orphans", tags=["orphans"])

COLUMNS = [
    "id", "url", "classification", "sources", "internal_inlinks", "crawled",
    "indexable", "clicks", "impressions", "sessions", "conversions", "revenue",
    "referring_domains", "priority", "priority_score", "score_components",
    "confidence", "likely_cause", "recommended_action", "page_type",
]


@router.post("/detect", status_code=202)
def detect(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "detect_orphans", "Orphan detection", {"config": payload or {}},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("")
def list_orphans(db: DB, project: ProjectDep, classification: str | None = None, priority: str | None = None,
                 q: str | None = None, offset: int = 0, limit: int = 100):
    query = select(OrphanRecord).where(OrphanRecord.project_id == project.id)
    if classification:
        query = query.where(OrphanRecord.classification == classification)
    if priority:
        query = query.where(OrphanRecord.priority == priority)
    if q:
        query = query.where(OrphanRecord.url.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, OrphanRecord.priority_score.desc())
    return paged([serialize(r, COLUMNS) for r in items], total, offset, limit)


@router.get("/summary")
def summary(db: DB, project: ProjectDep):
    from sqlalchemy import func

    rows = db.execute(
        select(OrphanRecord.classification, func.count(), func.sum(OrphanRecord.revenue), func.sum(OrphanRecord.clicks))
        .where(OrphanRecord.project_id == project.id).group_by(OrphanRecord.classification)
    ).all()
    return {"items": [{"classification": r[0], "urls": r[1], "revenue": r[2] or 0, "clicks": r[3] or 0} for r in rows]}


@router.get("/export")
def export_orphans(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(OrphanRecord).where(OrphanRecord.project_id == project.id).limit(200000)).all()
    return download([serialize(r, COLUMNS) for r in rows], COLUMNS, f"orphans_project_{project.id}", format)
