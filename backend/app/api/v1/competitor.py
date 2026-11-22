"""Competitor and content gap intelligence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import Competitor, KeywordGap
from app.services.jobs import enqueue

router = APIRouter(prefix="/competitors", tags=["competitors"])

GAP_COLUMNS = ["id", "keyword", "intent", "competitor_url", "our_url", "gap_type", "priority", "evidence", "recommendation", "competitor_id"]


@router.get("")
def list_competitors(db: DB, project: ProjectDep):
    rows = db.scalars(select(Competitor).where(Competitor.project_id == project.id)).all()
    return {"items": [serialize(r, ["id", "domain", "name", "notes"]) for r in rows]}


@router.post("", status_code=201)
def add_competitor(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    domain = str(payload.get("domain", "")).strip().lower()
    if not domain:
        raise HTTPException(400, "Domain required")
    competitor = Competitor(project_id=project.id, domain=domain, name=payload.get("name", ""), notes=payload.get("notes", ""))
    db.add(competitor)
    db.commit()
    return {"id": competitor.id}


@router.post("/analyse", status_code=202)
def analyse(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "competitor_analysis", "Competitor gap analysis", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued", "note": "Uses imported competitor keyword data only"}


@router.get("/gaps")
def gaps(db: DB, project: ProjectDep, gap_type: str | None = None, offset: int = 0, limit: int = 100):
    query = select(KeywordGap).where(KeywordGap.project_id == project.id)
    if gap_type:
        query = query.where(KeywordGap.gap_type == gap_type)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, KeywordGap.id)
    return paged([serialize(r, GAP_COLUMNS) for r in items], total, offset, limit)


@router.get("/export")
def export_gaps(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(KeywordGap).where(KeywordGap.project_id == project.id).limit(200000)).all()
    return download([serialize(r, GAP_COLUMNS) for r in rows], GAP_COLUMNS, f"keyword_gaps_project_{project.id}", format)
