"""Integration registry. No provider API is called unless explicitly configured."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write
from app.api.v1._helpers import serialize
from app.core.crypto import encrypt
from app.models.operations import Integration

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
        query = query.where(Integration.project_id == project_id)
    rows = db.scalars(query.order_by(Integration.id).limit(500)).all()
    return {"items": [serialize(r, ["id", "project_id", "organization_id", "provider", "display_name", "status", "mode", "config", "last_sync_at", "notes"]) for r in rows]}


@router.post("", status_code=201)
def upsert_integration(payload: dict, db: DB, user: UserDep):
    check_write(user)
    provider = payload.get("provider")
    if provider not in {p["provider"] for p in PROVIDERS}:
        raise HTTPException(400, "Unknown provider")
    mode = payload.get("mode", "csv_import")
    if mode not in next(p["modes"] for p in PROVIDERS if p["provider"] == provider):
        raise HTTPException(400, "Unsupported mode for provider")
    existing = db.scalar(select(Integration).where(
        Integration.provider == provider,
        Integration.project_id == payload.get("project_id"),
        Integration.organization_id == payload.get("organization_id"),
    ))
    item = existing or Integration(
        provider=provider, project_id=payload.get("project_id"),
        organization_id=payload.get("organization_id"),
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


@router.get("/{integration_id}")
def get_integration(integration_id: int, db: DB, user: UserDep):
    item = db.get(Integration, integration_id)
    if item is None:
        raise HTTPException(404, "Integration not found")
    return serialize(item, ["id", "provider", "display_name", "status", "mode", "config", "last_sync_at", "notes"])
