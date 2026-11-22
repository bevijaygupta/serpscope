"""International SEO planning and hreflang validation endpoints."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, serialize
from app.models.enterprise import HreflangRecord, InternationalPlan
from app.services.jobs import enqueue

router = APIRouter(prefix="/international", tags=["international"])

PLAN_COLUMNS = ["id", "market", "language", "url_structure", "search_intent", "service_pages", "supporting_content", "keyword_clusters", "hreflang_recommendations", "internal_link_architecture", "roadmap", "evidence"]
HREFLANG_COLUMNS = ["id", "url", "lang", "target", "status", "evidence"]


@router.post("/plan", status_code=202)
def build_plan(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "international_plan", "International SEO plan", {"config": payload or {}},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/plans")
def plans(db: DB, project: ProjectDep):
    rows = db.scalars(select(InternationalPlan).where(InternationalPlan.project_id == project.id).order_by(InternationalPlan.id.desc()).limit(50)).all()
    return {"items": [serialize(r, PLAN_COLUMNS) for r in rows]}


@router.get("/hreflang")
def hreflang(db: DB, project: ProjectDep, status: str | None = None):
    query = select(HreflangRecord).where(HreflangRecord.project_id == project.id)
    if status:
        query = query.where(HreflangRecord.status == status)
    rows = db.scalars(query.limit(5000)).all()
    return {"items": [serialize(r, HREFLANG_COLUMNS) for r in rows]}


@router.get("/export")
def export_plan(db: DB, project: ProjectDep, kind: str = "plan", format: str = "csv"):
    if kind == "hreflang":
        cols, model = HREFLANG_COLUMNS, HreflangRecord
    else:
        cols, model = PLAN_COLUMNS, InternationalPlan
    rows = db.scalars(select(model).where(model.project_id == project.id).limit(20000)).all()
    return download([serialize(r, cols) for r in rows], cols, f"international_{kind}_project_{project.id}", format)
