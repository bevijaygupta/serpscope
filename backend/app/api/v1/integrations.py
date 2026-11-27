"""Integration registry and dormant, explicitly gated live connectors."""
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
from app.services.vendor_connectors import ConnectorUnavailable, connector_readiness
from app.services.vendor_sync import sync_integration

router = APIRouter(prefix="/integrations", tags=["integrations"])

# Callers may label a row as ready/configured, but "connected" is earned only
# by a successful live sync. Config is an allowlist so arbitrary values (and
# especially secrets) cannot be stored in the plain-text config column.
CALLER_ALLOWED_STATUSES = {"csv_ready", "not_configured", "configured"}
CONFIG_STRING_LIMITS = {
    "site_url": 500,
    "property_id": 100,
    "start_date": 40,
    "end_date": 40,
}

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


def _sanitized_config(raw: object) -> dict:
    """Keep only short, known config values out of the plain-text column."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise HTTPException(400, "config must be an object")
    clean: dict = {}
    for key, value in raw.items():
        if key == "row_limit":
            try:
                limit = int(value)
            except (TypeError, ValueError):
                raise HTTPException(400, "Invalid config value")
            if not 1 <= limit <= 10_000:
                raise HTTPException(400, "Invalid config value")
            clean[key] = limit
            continue
        if key not in CONFIG_STRING_LIMITS or not isinstance(value, str):
            raise HTTPException(400, "Unsupported config value")
        if len(value) > CONFIG_STRING_LIMITS[key]:
            raise HTTPException(400, "Config value is too long")
        clean[key] = value.strip()
    return clean


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
    requested_status = payload.get("status")
    if requested_status is not None and requested_status not in CALLER_ALLOWED_STATUSES:
        raise HTTPException(400, "connected is earned only by a successful sync")
    item.mode = mode
    item.config = _sanitized_config(payload.get("config"))
    item.notes = payload.get("notes", "")
    if payload.get("credentials"):
        # Credentials are encrypted at rest and never returned by the API.
        item.credentials_encrypted = encrypt(str(payload["credentials"]))
        item.status = "configured"
    elif requested_status == "configured":
        if existing is None or not existing.credentials_encrypted:
            raise HTTPException(400, "configured requires stored credentials")
        item.status = "configured"
    elif requested_status is not None:
        item.status = requested_status
    elif existing is not None and existing.status == "connected" and existing.credentials_encrypted:
        item.status = "connected"
    else:
        item.status = "csv_ready" if mode == "csv_import" else "not_configured"
    if existing is None:
        db.add(item)
    db.commit()
    return {
        "id": item.id,
        "status": item.status,
        "note": (
            "Credentials stored encrypted; values are not returned. "
            "connected is set only by a successful sync."
        ),
    }


@router.get("/connectors")
def connector_status(user: UserDep):
    """Which live adapters are enabled. Never returns credential values."""
    return {
        "items": [
            {"provider": provider, "ready": ready}
            for provider, ready in connector_readiness().items()
        ],
        "note": (
            "All live connectors are off by default. A provider is ready only when "
            "LIVE_CONNECTORS_ENABLED=true and its credentials exist in the deployment "
            "environment. No credential value is returned by this endpoint."
        ),
    }


@router.post("/{integration_id}/sync")
def sync_live_integration(integration_id: int, db: DB, user: UserDep):
    """Explicitly fetch real provider rows for a project-scoped integration."""
    check_write(user)
    item = db.get(Integration, integration_id)
    if item is None:
        raise HTTPException(404, "Integration not found")
    if item.project_id is None:
        raise HTTPException(400, "Live sync requires a project-scoped integration")
    get_project(db, item.project_id, user)
    try:
        return sync_integration(db, item)
    except ConnectorUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


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
        "note": (
            "Statuses are earned by real uploaded or explicitly synced live rows. "
            "No provider API is called unless a live connector is enabled and "
            "configured; no private metric is inferred."
        ),
        "status_explanations": {
            "not_supplied": "No real export was supplied for this signal. The audit says 'Not supplied' instead of guessing.",
            "supplied": "Verbatim rows from a file you uploaded. Stored with its source and data-kind label; not a live API connection.",
            "synthetic": "Labelled demo/verification rows. Never presented as real client or vendor performance.",
            "api_live": "Verbatim rows fetched by an explicitly enabled live connector. The data-kind label names the provider; these rows are excluded from public case studies.",
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
