"""SERPScope API entry point."""
from __future__ import annotations

import hashlib
import hmac
import logging
import math
import threading
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import (
    ai,
    analytics,
    audits,
    auth,
    clients,
    competitor,
    content,
    crawler,
    demo,
    ecommerce,
    imports,
    integrations,
    international,
    inventory,
    jobs,
    keywords,
    links,
    local,
    meta,
    migration,
    orphans,
    presence,
    projects,
    technical,
    workflows,
)
from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal, init_db
from app.models.auth import Membership, Organization, User

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger("serpscope")

app = FastAPI(
    title="SERPScope API",
    version="1.0.0",
    description="Enterprise SEO intelligence and automation platform. All metrics carry source, timestamp and data-quality status.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-process, per-host abuse throttle. It never stores the client host itself:
# only a short HMAC digest of (UTC day, route bucket, socket peer host) is kept.
# The socket peer is read directly, never X-Forwarded-For, cookies, headers,
# user identity, audited domain or request contents. This is safe for the single
# Render web process declared in render.yaml; extra workers multiply the budget.
RATE_LIMIT_WINDOW_SECONDS = 600
RATE_LIMIT_BUCKET_LIMITS = {
    "login": 10,
    "presence": 60,
    "register": 5,
    "mutation": 120,
}
DEMO_EMAIL = "demo@serpscope.local"
DEMO_ORG_SLUG = "demo-organisation"
DEMO_PASSWORD = "demo1234"
_RATE_WINDOWS: dict[str, tuple[float, int]] = {}
_RATE_LOCK = threading.Lock()
_RATE_MAX_KEYS = 10_000


def _rate_limit_key(bucket: str, peer: str | None, day: int) -> str:
    material = f"{day}|{bucket}|{peer or ''}".encode("utf-8")
    return hmac.new(settings.secret_key.encode("utf-8"), material, hashlib.sha256).hexdigest()[:32]


@app.middleware("http")
async def rate_limit_mutations(request: Request, call_next):
    if not settings.rate_limit_enabled or request.method not in {"POST", "PATCH", "PUT", "DELETE"}:
        return await call_next(request)
    path = request.url.path
    if path == "/api/v1/auth/login":
        bucket = "login"
    elif path == "/api/v1/auth/register":
        bucket = "register"
    elif path == "/api/v1/presence/ping":
        bucket = "presence"
    else:
        bucket = "mutation"
    limit = RATE_LIMIT_BUCKET_LIMITS[bucket]
    day = int(time.time() // 86_400)
    key = _rate_limit_key(bucket, request.client.host if request.client else None, day)
    now = time.monotonic()
    with _RATE_LOCK:
        if len(_RATE_WINDOWS) > _RATE_MAX_KEYS:
            _RATE_WINDOWS.clear()
        start, count = _RATE_WINDOWS.get(key, (now, 0))
        if now - start >= RATE_LIMIT_WINDOW_SECONDS:
            start, count = now, 0
        count += 1
        _RATE_WINDOWS[key] = (start, count)
        retry_after = max(1, math.ceil(RATE_LIMIT_WINDOW_SECONDS - (now - start)))
    if count > limit:
        # No key, peer or path is echoed back; only a numeric retry hint.
        return JSONResponse(
            status_code=429,
            content={"detail": "Too many requests"},
            headers={"Retry-After": str(retry_after)},
        )
    return await call_next(request)


ROUTERS = [
    auth, meta, projects, clients, imports, jobs, inventory, crawler, technical,
    orphans, keywords, content, links, competitor, international, local,
    ecommerce, migration, ai, analytics, workflows, integrations, demo,
    audits, audits.public_router, presence,
]
for router in ROUTERS:
    app.include_router(router.router if hasattr(router, "router") else router, prefix="/api/v1")

settings.export_path.mkdir(parents=True, exist_ok=True)
settings.upload_path.mkdir(parents=True, exist_ok=True)
# Generated exports are returned directly by the authenticated download endpoints.
# There is deliberately no public static mount over EXPORT_DIR: a filename guess
# must never expose another tenant's generated file.


@app.get("/api/health", tags=["meta"])
def health():
    # Report only the dialect, never credentials or the connection string.
    report = {
        "status": "ok",
        "environment": settings.environment,
        "database": settings.database_url.split("://", 1)[0],
    }
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - degraded is reported without internals
        logger.exception("Health check database probe failed")
        return JSONResponse(status_code=503, content={**report, "status": "degraded", "probe": "unavailable"})
    return report


@app.exception_handler(Exception)
async def unhandled_exception(request, exc):  # pragma: no cover - safety net
    logger.exception("Unhandled error on %s", request.url.path)
    # Exception text can contain SQL, paths or supplied values. Log it, never
    # echo it back to an unauthenticated caller.
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def _inline_worker() -> None:  # pragma: no cover - background loop
    import time

    from app.services.jobs import claim_next, run_job
    from app.services import (  # noqa: F401 - register handlers in API process
        analysis_jobs, crawl_jobs, demo_jobs, import_jobs, keyword_jobs, public_audit_jobs,
        workflow_jobs,
    )

    last_schedule_check = 0.0
    while True:
        # Match the dedicated worker: scheduled workflows must tick whether the
        # API process or the standalone worker owns the queue.
        if time.time() - last_schedule_check > 60:
            db = None
            try:
                from app.services.jobs import enqueue

                db = SessionLocal()
                enqueue(db, "scheduler_tick", "Scheduled workflow check", {}, created_by=None)
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Inline worker could not enqueue scheduler tick")
            finally:
                if db is not None:
                    db.close()
            last_schedule_check = time.time()
        job_id = claim_next()
        if job_id is None:
            time.sleep(settings.job_poll_seconds)
            continue
        try:
            run_job(job_id)
        except Exception:  # noqa: BLE001
            logger.exception("Inline job %s failed", job_id)


@app.on_event("startup")
def bootstrap():
    init_db()
    db = SessionLocal()
    try:
        # Ensure the deterministic demo login exists even when other users were
        # created first (for example through the local self-registration route).
        # Existing accounts are never overwritten: an operator can replace the
        # demo user deliberately without startup silently restoring a password.
        org = db.query(Organization).filter(Organization.slug == DEMO_ORG_SLUG).first()
        if org is None:
            org = Organization(name="Demo Organisation", slug=DEMO_ORG_SLUG, is_demo=True)
            db.add(org)
            db.flush()

        admin = db.query(User).filter(User.email == DEMO_EMAIL).first()
        if admin is None:
            admin = User(
                email=DEMO_EMAIL, full_name="Demo SEO Lead",
                hashed_password=hash_password(DEMO_PASSWORD), global_role="owner", is_demo=True,
            )
            db.add(admin)
            db.flush()

        membership = db.query(Membership).filter(
            Membership.user_id == admin.id, Membership.organization_id == org.id
        ).first()
        if membership is None:
            db.add(Membership(user_id=admin.id, organization_id=org.id, role="owner"))
        db.commit()
        logger.info("Demo owner account available: %s", DEMO_EMAIL)
    finally:
        db.close()
    if settings.run_jobs_in_api:
        import threading

        threading.Thread(target=_inline_worker, daemon=True, name="inline-job-worker").start()
        logger.info("Inline job worker enabled (set RUN_JOBS_IN_API=false to use a separate worker)")
