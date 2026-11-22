"""Internal linking intelligence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.analysis import LinkSuggestion
from app.models.inventory import LinkEdge, UrlRecord
from app.services.jobs import enqueue
from app.services.links import analyse_graph

router = APIRouter(prefix="/internal-links", tags=["internal-links"])

SUGGESTION_COLUMNS = ["id", "source_url", "target_url", "anchor_text", "relevance", "target_importance", "current_status", "reason", "status", "source"]


@router.post("/analyse", status_code=202)
def analyse(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "link_suggestions", "Internal link analysis", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/graph-summary")
def graph_summary(db: DB, project: ProjectDep):
    from sqlalchemy import func

    edges = select(LinkEdge).where(LinkEdge.project_id == project.id)
    urls = select(UrlRecord).where(UrlRecord.project_id == project.id)
    return {
        "edges": db.scalar(select(func.count()).select_from(edges.subquery())),
        "internal_edges": db.scalar(select(func.count()).select_from(
            edges.where(LinkEdge.link_type == "internal").subquery())),
        "broken_edges": db.scalar(select(func.count()).select_from(
            edges.where(LinkEdge.is_broken.is_(True)).subquery())),
        "orphan_urls": db.scalar(select(func.count()).select_from(
            urls.where(UrlRecord.internal_inlinks == 0).subquery())),
        "urls_with_excessive_links": db.scalar(select(func.count()).select_from(
            urls.where(UrlRecord.internal_outlinks > 150).subquery())),
        "suggestions": db.scalar(select(func.count()).select_from(
            select(LinkSuggestion).where(LinkSuggestion.project_id == project.id).subquery())),
    }


@router.get("/suggestions")
def suggestions(db: DB, project: ProjectDep, status: str | None = None, offset: int = 0, limit: int = 100):
    query = select(LinkSuggestion).where(LinkSuggestion.project_id == project.id)
    if status:
        query = query.where(LinkSuggestion.status == status)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, LinkSuggestion.id)
    return paged([serialize(r, SUGGESTION_COLUMNS) for r in items], total, offset, limit)


@router.patch("/suggestions/{suggestion_id}")
def update_suggestion(suggestion_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    item = db.get(LinkSuggestion, suggestion_id)
    if item is None:
        raise HTTPException(404, "Suggestion not found")
    if payload.get("status") not in {"proposed", "approved", "rejected", "implemented"}:
        raise HTTPException(400, "Invalid status")
    item.status = payload["status"]
    db.commit()
    return {"success": True, "status": item.status}


@router.get("/export")
def export_suggestions(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(LinkSuggestion).where(LinkSuggestion.project_id == project.id).limit(200000)).all()
    return download([serialize(r, SUGGESTION_COLUMNS) for r in rows], SUGGESTION_COLUMNS, f"internal_links_project_{project.id}", format)
