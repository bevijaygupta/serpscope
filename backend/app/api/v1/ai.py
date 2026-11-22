"""AI search / AEO / GEO / LLMO intelligence endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import AiReadinessItem, AiVisibilityRecord
from app.services.jobs import enqueue

router = APIRouter(prefix="/ai-search", tags=["ai-search"])

READINESS_COLUMNS = ["id", "url", "dimension", "status", "evidence", "recommendation", "data_kind"]
VISIBILITY_COLUMNS = ["id", "question", "answer_engine", "observed_at", "brand_mentioned", "competitor_mentioned", "cited_url", "source", "data_kind", "notes"]


@router.post("/observations", status_code=201)
def add_observation(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    record = AiVisibilityRecord(
        project_id=project.id, question=str(payload.get("question", "")),
        answer_engine=str(payload.get("answer_engine", "manual-observation")),
        observed_at=payload.get("observed_at"),
        brand_mentioned=payload.get("brand_mentioned"),
        competitor_mentioned=payload.get("competitor_mentioned") or [],
        cited_url=str(payload.get("cited_url") or ""),
        source=str(payload.get("source", "manual-observation")),
        data_kind=str(payload.get("data_kind", "observed")),
        notes=str(payload.get("notes") or ""),
    )
    db.add(record)
    db.commit()
    return {"id": record.id}


@router.get("/observations")
def observations(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(AiVisibilityRecord).where(AiVisibilityRecord.project_id == project.id), offset, limit, AiVisibilityRecord.id)
    return paged([serialize(r, VISIBILITY_COLUMNS) for r in items], total, offset, limit)


@router.post("/audit", status_code=202)
def audit(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "ai_readiness", "AI search readiness audit", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/readiness")
def readiness(db: DB, project: ProjectDep, dimension: str | None = None, status: str | None = None,
              offset: int = 0, limit: int = 100):
    query = select(AiReadinessItem).where(AiReadinessItem.project_id == project.id)
    if dimension:
        query = query.where(AiReadinessItem.dimension == dimension)
    if status:
        query = query.where(AiReadinessItem.status == status)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, AiReadinessItem.id)
    return paged([serialize(r, READINESS_COLUMNS) for r in items], total, offset, limit)


@router.get("/export")
def export_ai(db: DB, project: ProjectDep, kind: str = "readiness", format: str = "csv"):
    if kind == "observations":
        cols, model = VISIBILITY_COLUMNS, AiVisibilityRecord
    else:
        cols, model = READINESS_COLUMNS, AiReadinessItem
    rows = db.scalars(select(model).where(model.project_id == project.id).limit(200000)).all()
    return download([serialize(r, cols) for r in rows], cols, f"ai_{kind}_project_{project.id}", format)
