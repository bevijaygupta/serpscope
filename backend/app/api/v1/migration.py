"""Migration planning and validation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import MigrationMapping, MigrationProject
from app.services.jobs import enqueue

router = APIRouter(prefix="/migration", tags=["migration"])

COLUMNS = ["id", "old_url", "new_url", "redirect_status", "redirect_chain", "http_status", "old_canonical", "new_canonical", "old_indexable", "new_indexable", "in_old_sitemap", "in_new_sitemap", "clicks", "revenue", "risk", "findings", "recommendation"]


@router.get("/projects")
def migration_projects(db: DB, project: ProjectDep):
    rows = db.scalars(select(MigrationProject).where(MigrationProject.project_id == project.id)).all()
    return {"items": [serialize(r, ["id", "name", "migration_type", "old_domain", "new_domain", "phase", "checklist", "summary"]) for r in rows]}


@router.post("/projects", status_code=201)
def create_migration_project(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    item = MigrationProject(
        project_id=project.id, name=payload.get("name", "Migration"),
        migration_type=payload.get("migration_type", "domain"),
        old_domain=payload.get("old_domain", ""), new_domain=payload.get("new_domain", ""),
        phase=payload.get("phase", "planning"),
    )
    db.add(item)
    db.commit()
    return {"id": item.id}


@router.post("/mappings/bulk", status_code=201)
def bulk_mappings(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    rows = payload.get("mappings") or []
    if not isinstance(rows, list) or len(rows) > 100000:
        raise HTTPException(400, "Provide up to 100,000 mappings")
    records = [{
        "project_id": project.id,
        "old_url": str(r.get("old_url") or ""),
        "new_url": str(r.get("new_url") or ""),
        "in_old_sitemap": bool(r.get("in_old_sitemap")),
        "clicks": float(r.get("clicks") or 0),
        "revenue": float(r.get("revenue") or 0),
        "old_canonical": str(r.get("old_canonical") or ""),
    } for r in rows if r.get("old_url")]
    db.bulk_insert_mappings(MigrationMapping, records)
    db.commit()
    return {"imported": len(records)}


@router.get("/mappings")
def mappings(db: DB, project: ProjectDep, risk: str | None = None, q: str | None = None,
             offset: int = 0, limit: int = 100):
    query = select(MigrationMapping).where(MigrationMapping.project_id == project.id)
    if risk:
        query = query.where(MigrationMapping.risk == risk)
    if q:
        query = query.where(MigrationMapping.old_url.ilike(f"%{q}%") | MigrationMapping.new_url.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, MigrationMapping.id)
    return paged([serialize(r, COLUMNS) for r in items], total, offset, limit)


@router.post("/validate", status_code=202)
def validate(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "migration_validate", "Migration validation", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/export")
def export_mappings(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(MigrationMapping).where(MigrationMapping.project_id == project.id).limit(200000)).all()
    return download([serialize(r, COLUMNS) for r in rows], COLUMNS, f"migration_redirect_map_project_{project.id}", format)
