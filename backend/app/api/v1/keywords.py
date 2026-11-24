"""Keyword research, clustering, mapping and bulk workflow endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select

from app.api.deps import DB, ProjectDep, UserDep, check_write, get_project
from app.api.v1._helpers import download, paged, serialize
from app.core.config import settings
from app.core.timeutil import iso, utcnow
from app.models.keywords import Keyword, KeywordCluster, KeywordMapping
from app.models.projects import DataSource
from app.services import keywords as keyword_service
from app.services.jobs import enqueue

router = APIRouter(prefix="/keywords", tags=["keywords"])

KW_COLUMNS = ["id", "keyword", "normalized", "intent", "intent_source", "topic", "parent_topic", "country", "language", "volume", "difficulty", "cpc", "competition", "serp_features", "source", "collected_at", "confidence", "cluster_id", "evidence"]
CLUSTER_COLUMNS = ["id", "name", "parent_topic", "intent", "method", "reasoning", "primary_keyword", "review_status", "keywords"]
MAPPING_COLUMNS = ["id", "url", "primary_keyword", "secondary_keywords", "supporting_keywords", "intent", "cluster_name", "page_type", "funnel_stage", "target_location", "confidence", "reasoning", "recommended_changes", "suggested_internal_links", "status", "cannibalisation_risk", "source"]


@router.post("/import", status_code=202)
async def import_keywords(
    db: DB,
    user: UserDep,
    project: ProjectDep,
    file: UploadFile = File(...),
    source_type: str = Form("keyword_csv"),
):
    check_write(user)
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".tsv", ".txt", ".xlsx"}:
        raise HTTPException(400, "Upload a CSV, TSV or XLSX export")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "File too large")
    destination_dir = settings.upload_path / str(project.id)
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = "".join(c for c in (file.filename or "keywords.csv") if c.isalnum() or c in "._-")[:120]
    path = destination_dir / f"kw_{int(utcnow().timestamp() * 1000)}_{safe_name}"
    path.write_bytes(content)
    job = enqueue(db, "import_keywords", f"Import keywords {safe_name}",
                  {"file_path": str(path), "source_type": source_type,
                   "competitor_domain": (source_type == "competitor_csv" and project.domain) or ""},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.post("/inline", status_code=201)
def add_keywords(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    items = payload.get("keywords") or []
    if not isinstance(items, list) or len(items) > 10000:
        raise HTTPException(400, "Provide up to 10,000 keyword objects or strings")
    records = []
    for item in items:
        keyword = item if isinstance(item, str) else str(item.get("keyword", ""))
        if not keyword.strip():
            continue
        records.append({
            "project_id": project.id, "keyword": keyword.strip(),
            "normalized": keyword_service.normalize_keyword(keyword),
            "intent": (item.get("intent") if isinstance(item, dict) else "") or "unclassified",
            "topic": (item.get("topic") if isinstance(item, dict) else "") or "",
            "volume": int(item.get("volume") or 0) if isinstance(item, dict) else None,
            "difficulty": float(item.get("difficulty")) if isinstance(item, dict) and item.get("difficulty") else None,
            "source": payload.get("source", "manual"),
            "collected_at": iso(utcnow()),
            "confidence": payload.get("confidence", "imported"),
        })
    db.bulk_insert_mappings(Keyword, records)
    db.commit()
    return {"imported": len(records)}


@router.get("")
def list_keywords(db: DB, project: ProjectDep, q: str | None = None, intent: str | None = None,
                  cluster_id: int | None = None, source: str | None = None, offset: int = 0, limit: int = 100):
    query = select(Keyword).where(Keyword.project_id == project.id)
    if q:
        query = query.where(Keyword.keyword.ilike(f"%{q}%"))
    if intent:
        query = query.where(Keyword.intent == intent)
    if cluster_id:
        query = query.where(Keyword.cluster_id == cluster_id)
    if source:
        query = query.where(Keyword.source == source)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, Keyword.id)
    return paged([serialize(r, KW_COLUMNS) for r in items], total, offset, limit)


@router.get("/summary")
def keyword_summary(db: DB, project: ProjectDep):
    intents = db.execute(select(Keyword.intent, func.count()).where(Keyword.project_id == project.id).group_by(Keyword.intent)).all()
    sources = db.execute(select(Keyword.source, func.count()).where(Keyword.project_id == project.id).group_by(Keyword.source)).all()
    return {
        "total": db.scalar(select(func.count()).where(Keyword.project_id == project.id)),
        "by_intent": dict(intents), "by_source": dict(sources),
        "clusters": db.scalar(select(func.count()).where(KeywordCluster.project_id == project.id)),
    }


@router.post("/cluster", status_code=202)
def cluster(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    config = payload or {}
    job = enqueue(db, "cluster_keywords", "Keyword clustering", {"config": config},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued", "methods": ["exact", "normalized", "token", "semantic", "intent", "serp_overlap"]}


@router.get("/clusters")
def clusters(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(KeywordCluster).where(KeywordCluster.project_id == project.id), offset, limit, KeywordCluster.id)
    return paged([serialize(r, CLUSTER_COLUMNS) for r in items], total, offset, limit)


@router.patch("/clusters/{cluster_id}")
def update_cluster(cluster_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    cluster = db.get(KeywordCluster, cluster_id)
    if cluster is None:
        raise HTTPException(404, "Cluster not found")
    get_project(db, cluster.project_id, user)
    for key in ("name", "parent_topic", "intent", "review_status", "primary_keyword", "reasoning"):
        if key in payload:
            setattr(cluster, key, payload[key])
    if "split_keywords" in payload:
        removed = set(payload["split_keywords"])
        cluster.keywords = [k for k in (cluster.keywords or []) if k.get("keyword") not in removed]
        db.query(Keyword).filter(
            Keyword.project_id == cluster.project_id,
            Keyword.cluster_id == cluster_id,
            Keyword.keyword.in_(removed),
        ).update({"cluster_id": None})
    db.commit()
    return {"success": True}


@router.post("/map", status_code=202)
def map_keywords(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "map_keywords", "Keyword to URL mapping", {"config": payload or {}},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/mappings")
def mappings(db: DB, project: ProjectDep, q: str | None = None, risk: str | None = None,
             offset: int = 0, limit: int = 100):
    query = select(KeywordMapping).where(KeywordMapping.project_id == project.id)
    if q:
        query = query.where(KeywordMapping.url.ilike(f"%{q}%") | KeywordMapping.primary_keyword.ilike(f"%{q}%"))
    if risk:
        query = query.where(KeywordMapping.cannibalisation_risk == risk)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, KeywordMapping.id)
    return paged([serialize(r, MAPPING_COLUMNS) for r in items], total, offset, limit)


@router.get("/cannibalisation")
def cannibalisation(db: DB, project: ProjectDep):
    rows = keyword_service.cannibalisation_conflicts(db, project.id)
    return {"items": [{
        "primary_keyword": item["primary_keyword"],
        "url_count": len(item["urls"]),
        "urls": item["urls"],
    } for item in rows]}


@router.post("/bulk-workflow", status_code=202)
def bulk_workflow(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "bulk_keyword_workflow", "1,000-page keyword mapping workflow",
                  {"config": payload or {}}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued",
            "note": "Automated processing of imported data; fresh third-party research needs provider credentials."}


@router.get("/export")
def export_keywords(db: DB, project: ProjectDep, kind: str = "mapping", format: str = "csv"):
    if kind == "clusters":
        cols, model = CLUSTER_COLUMNS, KeywordCluster
    elif kind == "keywords":
        cols, model = KW_COLUMNS, Keyword
    else:
        cols, model = MAPPING_COLUMNS, KeywordMapping
    rows = db.scalars(select(model).where(model.project_id == project.id).limit(200000)).all()
    return download([serialize(r, cols) for r in rows], cols, f"{kind}_project_{project.id}", format)
