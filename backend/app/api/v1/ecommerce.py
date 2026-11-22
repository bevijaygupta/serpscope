"""E-commerce SEO and Merchant Center diagnostics endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import Product
from app.services.jobs import enqueue

router = APIRouter(prefix="/ecommerce", tags=["ecommerce"])

COLUMNS = ["id", "url", "product_id", "title", "category", "price", "availability", "identifier", "canonical", "schema_types", "diagnostics", "status", "priority", "data_kind"]


@router.post("/products/bulk", status_code=201)
def bulk_products(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    rows = payload.get("products") or []
    if not isinstance(rows, list) or len(rows) > 50000:
        raise HTTPException(400, "Provide up to 50,000 products")
    records = [{
        "project_id": project.id,
        "url": str(r.get("url") or ""),
        "product_id": str(r.get("product_id") or ""),
        "title": str(r.get("title") or ""),
        "description": str(r.get("description") or ""),
        "category": str(r.get("category") or ""),
        "price": str(r.get("price") or ""),
        "availability": str(r.get("availability") or ""),
        "identifier": str(r.get("identifier") or ""),
        "canonical": str(r.get("canonical") or ""),
        "schema_types": r.get("schema_types") or [],
        "diagnostics": r.get("diagnostics") or [],
        "status": str(r.get("status") or "active"),
        "data_kind": payload.get("data_kind", "imported"),
    } for r in rows if r.get("url")]
    db.bulk_insert_mappings(Product, records)
    db.commit()
    return {"imported": len(records)}


@router.get("/products")
def products(db: DB, project: ProjectDep, issue: str | None = None, priority: str | None = None,
             category: str | None = None, q: str | None = None, offset: int = 0, limit: int = 100):
    query = select(Product).where(Product.project_id == project.id)
    if priority:
        query = query.where(Product.priority == priority)
    if category:
        query = query.where(Product.category == category)
    if q:
        query = query.where(Product.title.ilike(f"%{q}%") | Product.url.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, Product.id)
    result = [serialize(r, COLUMNS) for r in items]
    if issue:
        result = [r for r in result if issue in (r.get("diagnostics") or [])]
    return paged(result, total, offset, limit)


@router.post("/audit", status_code=202)
def audit(db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "ecommerce_audit", "E-commerce audit", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/export")
def export_products(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(Product).where(Product.project_id == project.id).limit(200000)).all()
    return download([serialize(r, COLUMNS) for r in rows], COLUMNS, f"merchant_diagnostics_project_{project.id}", format)
