"""Local SEO and location management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import Location
from app.services.jobs import enqueue

router = APIRouter(prefix="/local", tags=["local"])

COLUMNS = ["id", "name", "brand", "address", "city", "state", "postal_code", "country", "phone", "website", "category", "status", "landing_page", "local_keywords", "issues", "audit", "duplicate_group", "data_kind"]


@router.post("/locations/bulk", status_code=201)
def bulk_locations(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    rows = payload.get("locations") or []
    if not isinstance(rows, list) or len(rows) > 10000:
        raise HTTPException(400, "Provide up to 10,000 location records")
    records = []
    for row in rows:
        records.append({
            "project_id": project.id,
            "name": str(row.get("name") or row.get("location") or "Unnamed location"),
            "brand": str(row.get("brand") or ""),
            "address": str(row.get("address") or ""),
            "city": str(row.get("city") or ""),
            "state": str(row.get("state") or ""),
            "postal_code": str(row.get("postal_code") or row.get("postcode") or ""),
            "country": str(row.get("country") or ""),
            "phone": str(row.get("phone") or ""),
            "website": str(row.get("website") or ""),
            "category": str(row.get("category") or ""),
            "status": str(row.get("status") or "active"),
            "landing_page": str(row.get("landing_page") or ""),
            "local_keywords": row.get("local_keywords") or [],
            "data_kind": payload.get("data_kind", "imported"),
        })
    db.bulk_insert_mappings(Location, records)
    db.commit()
    return {"imported": len(records)}


@router.get("/locations")
def locations(db: DB, project: ProjectDep, city: str | None = None, country: str | None = None,
              status: str | None = None, issue: str | None = None, q: str | None = None,
              offset: int = 0, limit: int = 100):
    query = select(Location).where(Location.project_id == project.id)
    if city:
        query = query.where(Location.city.ilike(f"%{city}%"))
    if country:
        query = query.where(Location.country.ilike(f"%{country}%"))
    if status:
        query = query.where(Location.status == status)
    if q:
        query = query.where(Location.name.ilike(f"%{q}%") | Location.address.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, Location.id)
    result = [serialize(r, COLUMNS) for r in items]
    if issue:
        result = [r for r in result if issue in (r.get("issues") or [])]
    return paged(result, total, offset, limit)


@router.post("/audit", status_code=202)
def audit_locations(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "local_audit", "Local SEO audit", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/export")
def export_locations(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(Location).where(Location.project_id == project.id).limit(200000)).all()
    return download([serialize(r, COLUMNS) for r in rows], COLUMNS, f"gbp_locations_project_{project.id}", format)
