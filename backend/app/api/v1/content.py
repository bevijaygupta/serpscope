"""Content intelligence, analysis and briefs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write, get_project
from app.api.v1._helpers import download, paged, serialize
from app.models.analysis import ContentAnalysis, ContentBrief
from app.services.jobs import enqueue

router = APIRouter(prefix="/content", tags=["content"])

ANALYSIS_COLUMNS = ["id", "url", "title", "title_length", "meta_length", "h1_count", "h2_count", "word_count", "intent_alignment", "topic_gaps", "entity_gaps", "image_alt_issues", "schema_recommendations", "score", "findings", "data_kind"]
BRIEF_COLUMNS = ["id", "url", "primary_keyword", "secondary_keywords", "intent", "suggested_title", "suggested_h1", "suggested_headings", "questions", "entities", "internal_links", "conversion_objective", "recommended_schema", "sources", "approval_status"]


@router.post("/analyse", status_code=202)
def analyse(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "content_analysis", "Content analysis", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.post("/briefs/generate", status_code=202)
def generate_briefs(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "generate_briefs", "Content brief generation", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/analyses")
def analyses(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(ContentAnalysis).where(ContentAnalysis.project_id == project.id), offset, limit, ContentAnalysis.id)
    return paged([serialize(r, ANALYSIS_COLUMNS) for r in items], total, offset, limit)


@router.get("/briefs")
def briefs(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(ContentBrief).where(ContentBrief.project_id == project.id), offset, limit, ContentBrief.id)
    return paged([serialize(r, BRIEF_COLUMNS) for r in items], total, offset, limit)


@router.patch("/briefs/{brief_id}")
def update_brief(brief_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    brief = db.get(ContentBrief, brief_id)
    if brief is None:
        raise HTTPException(404, "Brief not found")
    get_project(db, brief.project_id, user)
    for key in ("approval_status", "suggested_title", "suggested_h1", "suggested_headings", "questions", "entities"):
        if key in payload:
            setattr(brief, key, payload[key])
    db.commit()
    return {"success": True, "approval_status": brief.approval_status}


@router.get("/export")
def export_content(db: DB, project: ProjectDep, kind: str = "analyses", format: str = "csv"):
    if kind == "briefs":
        cols, model = BRIEF_COLUMNS, ContentBrief
    else:
        cols, model = ANALYSIS_COLUMNS, ContentAnalysis
    rows = db.scalars(select(model).where(model.project_id == project.id).limit(200000)).all()
    return download([serialize(r, cols) for r in rows], cols, f"content_{kind}_project_{project.id}", format)
