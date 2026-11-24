"""Integration registry. No provider API is called unless explicitly configured."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write, get_project, require_org
from app.api.v1._helpers import serialize
from app.core.crypto import encrypt
from app.models.auth import Membership
from app.models.operations import Integration
from app.models.projects import Project
from app.services.supplied_metrics import SIGNAL_LABELS, supplied_record_rows, supplied_signals

router = APIRouter(prefix="/integrations", tags=["integrations"])

PROVIDERS = [
    {"provider": "google_search_console", "display_name": "Google Search Console", "modes": ["csv_import", "oauth_api"]},
    {"provider": "google_analytics_4", "display_name": "Google Analytics 4", "modes": ["csv_import", "oauth_api"]},
    {"provider": "google_sheets", "display_name": "Google Sheets", "modes": ["csv_import", "oauth_api"]},
    {"provider": "google_business_profile", "display_name": "Google Business Profile", "modes": ["csv_import", "oauth_api"]},
    {"provider": "google_merchant_center", "display_name": "Google Merchant Center", "modes": ["csv_import", "oauth_api"]},
    {"provider": "screaming_frog", "display_name": "Screaming Frog", "modes": ["csv_import"]},
    {"provider": "sitebulb", "display_name": "Sitebulb", "modes": ["csv_import"]},
    {"provider": "semrush", "display_name": "Semrush", "modes": ["csv_import", "api_key"]},
    {"provider": "ahrefs", "display_name": "Ahrefs", "modes": ["csv_import", "api_key"]},
    {"provider": "llm_provider", "display_name": "Optional LLM provider", "modes": ["api_key"]},
]


@router.get("/providers")
def providers():
    return {"items": PROVIDERS, "note": "CSV import works without credentials. API modes require configured credentials and permissions."}


@router.get("")
def list_integrations(db: DB, user: UserDep, project_id: int | None = None):
    query = select(Integration)
    if project_id:
        get_project(db, project_id, user)
        query = query.where(Integration.project_id == project_id)
    elif user.global_role not in {"owner", "admin"}:
        orgs = db.scalars(select(Membership.organization_id).where(Membership.user_id == user.id)).all()
        projects = db.scalars(select(Project.id).where(Project.organization_id.in_(orgs or [-1]))).all()
        query = query.where(Integration.project_id.in_(projects or [-1]))
    rows = db.scalars(query.order_by(Integration.id).limit(500)).all()
    return {"items": [serialize(r, ["id", "project_id", "organization_id", "provider", "display_name", "status", "mode", "config", "last_sync_at", "notes"]) for r in rows]}


@router.post("", status_code=201)
def upsert_integration(payload: dict, db: DB, user: UserDep):
    check_write(user)
    if payload.get("project_id") is None:
        raise HTTPException(400, "project_id is required")
    try:
        project_id = int(payload["project_id"])
    except (TypeError, ValueError):
        raise HTTPException(400, "Invalid project_id")
    project = get_project(db, project_id, user)
    organization_id = project.organization_id
    provider = payload.get("provider")
    if provider not in {p["provider"] for p in PROVIDERS}:
        raise HTTPException(400, "Unknown provider")
    mode = payload.get("mode", "csv_import")
    if mode not in next(p["modes"] for p in PROVIDERS if p["provider"] == provider):
        raise HTTPException(400, "Unsupported mode for provider")
    existing = db.scalar(select(Integration).where(
        Integration.provider == provider,
        Integration.project_id == project_id,
        Integration.organization_id == organization_id,
    ))
    item = existing or Integration(
        provider=provider, project_id=project_id,
        organization_id=organization_id,
        display_name=payload.get("display_name", provider),
    )
    item.mode = mode
    item.status = payload.get("status", "csv_ready" if mode == "csv_import" else "not_configured")
    item.config = payload.get("config") or {}
    item.notes = payload.get("notes", "")
    if payload.get("credentials"):
        # Credentials are encrypted at rest and never returned by the API.
        item.credentials_encrypted = encrypt(str(payload["credentials"]))
        item.status = "configured"
    if existing is None:
        db.add(item)
    db.commit()
    return {"id": item.id, "status": item.status, "note": "Credentials stored encrypted; values are not returned."}


@router.get("/supplied-signals")
def supplied_signal_status(db: DB, user: UserDep, project_id: int):
    """Which vendor signals have real user-supplied rows, and how many."""
    get_project(db, project_id, user)
    status = supplied_signals(db, project_id)
    return {
        "items": [
            {"signal": key, "label": SIGNAL_LABELS[key], **value}
            for key, value in status.items()
        ],
        "note": "Statuses are earned by real uploaded rows. No provider API is called and no private metric is inferred.",
        "status_explanations": {
            "not_supplied": "No real export was supplied for this signal. The audit says 'Not supplied' instead of guessing.",
            "supplied": "Verbatim rows from a file you uploaded. Stored with its source and data-kind label; not a live API connection.",
            "synthetic": "Labelled demo/verification rows. Never presented as real client or vendor performance.",
        },
    }


@router.get("/supplied-records")
def supplied_records(db: DB, user: UserDep, project_id: int, signal: str, limit: int = 100):
    get_project(db, project_id, user)
    if signal not in SIGNAL_LABELS:
        raise HTTPException(400, f"Unknown signal. Allowed: {sorted(SIGNAL_LABELS)}")
    return {"items": supplied_record_rows(db, project_id, signal, min(max(limit, 1), 500))}


@router.get("/{integration_id}")
def get_integration(integration_id: int, db: DB, user: UserDep):
    item = db.get(Integration, integration_id)
    if item is None:
        raise HTTPException(404, "Integration not found")
    if item.project_id is not None:
        get_project(db, item.project_id, user)
    elif item.organization_id is not None:
        require_org(db, user, item.organization_id)
    elif user.global_role not in {"owner", "admin"}:
        raise HTTPException(404, "Integration not found")
    return serialize(item, ["id", "provider", "display_name", "status", "mode", "config", "last_sync_at", "notes"])
