"""SERPScope API entry point."""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
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
        if db.query(User).count() == 0:
            # A database can already contain the demo organisation (for example a
            # seeded dataset) while having no users. Reuse it instead of inserting
            # a duplicate slug.
            org = db.query(Organization).filter(
                Organization.slug == "demo-organisation"
            ).first()
            if org is None:
                org = Organization(name="Demo Organisation", slug="demo-organisation", is_demo=True)
                db.add(org)
                db.flush()
            admin = User(
                email="demo@serpscope.local", full_name="Demo SEO Lead",
                hashed_password=hash_password("demo1234"), global_role="owner", is_demo=True,
            )
            db.add(admin)
            db.flush()
            db.add(Membership(user_id=admin.id, organization_id=org.id, role="owner"))
            db.commit()
            logger.info("Created demo owner account demo@serpscope.local")
    finally:
        db.close()
    if settings.run_jobs_in_api:
        import threading

        threading.Thread(target=_inline_worker, daemon=True, name="inline-job-worker").start()
        logger.info("Inline job worker enabled (set RUN_JOBS_IN_API=false to use a separate worker)")
