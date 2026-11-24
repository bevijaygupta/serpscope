"""AI search / AEO / GEO / LLMO intelligence endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.enterprise import AiReadinessItem, AiVisibilityRecord
from app.services.jobs import enqueue

router = APIRouter(prefix="/ai-search", tags=["ai-search"])

READINESS_COLUMNS = ["id", "url", "dimension", "status", "evidence", "recommendation", "data_kind"]
VISIBILITY_COLUMNS = [
    "id", "question", "answer_engine", "observed_at", "brand_mentioned", "competitor_mentioned",
    "cited_url", "answer_url", "locale", "source", "data_kind", "notes",
]


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
        answer_url=str(payload.get("answer_url") or ""),
        locale=str(payload.get("locale") or ""),
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


def _observation_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1", "mentioned", "present"}:
        return True
    if text in {"false", "no", "n", "0", "not mentioned", "absent"}:
        return False
    return None


def _observation_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).replace(",", ";").split(";") if part.strip()]


@router.post("/observations/import", status_code=201)
def import_observations(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    """Store user-supplied answer-engine observations verbatim.

    No answer engine is queried here. Rows keep their declared source and
    data_kind; synthetic/unverified rows are stored but excluded from claims, so
    an empty *verified* log still reports `not_sampled`.
    """
    check_write(user)
    default_source = str(payload.get("source") or "imported-observation")[:100]
    default_kind = str(payload.get("data_kind") or "imported")[:30]
    rows = payload.get("rows")
    if rows is None and payload.get("csv"):
        from app.services.imports import parse_table
        suffix = ".json" if str(payload.get("csv_format", "")).lower() == "json" else ".csv"
        _, rows = parse_table(str(payload["csv"]).encode("utf-8"), suffix)
    if not isinstance(rows, list) or not rows:
        raise HTTPException(400, "Provide a non-empty 'rows' list or 'csv' text")

    accepted = 0
    rejected = 0
    errors: list[str] = []
    sources: set[str] = set()
    kinds: set[str] = set()
    for index, raw in enumerate(rows, start=1):
        if not isinstance(raw, dict):
            rejected += 1
            errors.append(f"Row {index}: expected an object")
            continue
        question = str(raw.get("question") or "").strip()
        engine = str(raw.get("answer_engine") or "").strip()
        if not question or not engine:
            rejected += 1
            errors.append(f"Row {index}: 'question' and 'answer_engine' are required")
            continue
        source = str(raw.get("source") or default_source)[:100]
        kind = str(raw.get("data_kind") or default_kind)[:30]
        db.add(AiVisibilityRecord(
            project_id=project.id,
            question=question,
            answer_engine=engine,
            observed_at=(str(raw["observed_at"]) if raw.get("observed_at") not in (None, "") else None),
            brand_mentioned=_observation_bool(raw.get("brand_mentioned")),
            competitor_mentioned=_observation_list(raw.get("competitor_mentioned")),
            cited_url=str(raw.get("cited_url") or "")[:4096],
            answer_url=str(raw.get("answer_url") or "")[:4096],
            locale=str(raw.get("locale") or "")[:20],
            source=source,
            data_kind=kind,
            notes=str(raw.get("notes") or "")[:4096],
        ))
        accepted += 1
        sources.add(source)
        kinds.add(kind)
    db.commit()

    from app.services.public_audit import ai_visibility_context
    context = ai_visibility_context(db, project.id)
    return {
        "accepted": accepted,
        "rejected": rejected,
        "errors": errors[:20],
        "sources": sorted(sources),
        "data_kinds": sorted(kinds),
        "visibility_status": context["status"],
        "verified_observations": context["observation_count"],
        "note": (
            "Rows are stored exactly as supplied. No answer engine was queried. "
            "Only source-labelled verified data_kind values become claims; "
            "an empty verified log stays 'not_sampled', never 'not mentioned'."
        ),
    }


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
