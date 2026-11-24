"""File upload and URL inventory import endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write, get_project
from app.api.v1._helpers import audit, serialize
from app.core.config import settings
from app.core.timeutil import iso, utcnow
from app.models.projects import DataSource
from app.services.imports import upsert_urls
from app.services.jobs import enqueue

router = APIRouter(prefix="/imports", tags=["imports"])

ALLOWED_EXTENSIONS = {".csv", ".tsv", ".txt", ".xml", ".json", ".xlsx"}
MAX_BYTES = settings.max_upload_mb * 1024 * 1024
SOURCE_TYPES = {
    "csv_urls", "sitemap", "sitemap_index", "gsc", "ga4", "cms", "screaming_frog",
    "sitebulb", "backlinks", "keyword_csv", "competitor_csv", "analytics",
    "rank_tracking", "authority", "lighthouse", "crux", "serp_features",
    "paid_ads", "gbp", "historical_audit",
}


@router.post("/upload", status_code=202)
async def upload_file(
    db: DB,
    user: UserDep,
    file: UploadFile = File(...),
    project_id: int = Form(...),
    source_type: str = Form("csv_urls"),
    data_kind: str = Form("imported"),
):
    check_write(user)
    project = get_project(db, project_id, user)
    if source_type not in SOURCE_TYPES:
        raise HTTPException(400, f"Unsupported source_type. Allowed: {sorted(SOURCE_TYPES)}")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file extension. Allowed: {sorted(ALLOWED_EXTENSIONS)}")
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB limit")
    if not content:
        raise HTTPException(400, "Empty file")
    destination_dir = settings.upload_path / str(project_id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in (file.filename or "upload") if c.isalnum() or c in "._-")[:120]
    destination = destination_dir / f"{int(utcnow().timestamp() * 1000)}_{safe_name}"
    destination.write_bytes(content)
    job = enqueue(
        db, "import_file", f"Import {safe_name}",
        {"file_path": str(destination), "source_type": source_type,
         "name": safe_name, "data_kind": data_kind},
        project_id=project.id, organization_id=project.organization_id, created_by=user.id,
    )
    audit(db, user, "import.upload", safe_name, project_id=project.id,
          details={"source_type": source_type, "bytes": len(content)})
    db.commit()
    return {"job_id": job.id, "status": "queued", "file": safe_name, "bytes": len(content)}


@router.post("/url-list", status_code=201)
def import_url_list(payload: dict, db: DB, user: UserDep):
    """Small inline URL lists. Large files should use /upload."""
    check_write(user)
    project = get_project(db, payload.get("project_id"), user)
    urls = payload.get("urls") or []
    if not isinstance(urls, list) or len(urls) > 10000:
        raise HTTPException(400, "Provide a list of up to 10,000 URLs; use /upload for larger files")
    accepted, rejected, errors = upsert_urls(
        db, project.id, urls, payload.get("source", "manual_list"),
        payload.get("data_kind", "imported"), payload.get("normalization_rules"),
    )
    source = DataSource(
        project_id=project.id, source_type=payload.get("source", "manual_list"),
        name=payload.get("name", "Inline URL list"), row_count=accepted,
        rejected_count=rejected, data_kind=payload.get("data_kind", "imported"),
        meta_info={"errors": errors},
    )
    db.add(source)
    audit(db, user, "import.url_list", source.name, project_id=project.id)
    db.commit()
    return {"data_source_id": source.id, "accepted": accepted, "rejected": rejected, "errors": errors}


@router.get("/sources")
def list_sources(db: DB, user: UserDep, project_id: int, limit: int = 200):
    get_project(db, project_id, user)
    rows = db.scalars(select(DataSource).where(DataSource.project_id == project_id)
                      .order_by(DataSource.id.desc()).limit(limit)).all()
    return {"items": [serialize(r, ["id", "source_type", "name", "file_name", "row_count", "rejected_count", "status", "data_kind", "meta_info", "created_at"]) for r in rows]}


@router.get("/sources/{source_id}")
def get_source(source_id: int, db: DB, user: UserDep):
    source = db.get(DataSource, source_id)
    if source is None:
        raise HTTPException(404, "Source not found")
    get_project(db, source.project_id, user)
    return serialize(source, ["id", "project_id", "source_type", "name", "row_count", "rejected_count", "meta_info", "data_kind"])
