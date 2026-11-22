"""Database-backed job queue shared by the API process and worker process."""
from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.db.session import SessionLocal
from app.models.projects import Job

HANDLERS: dict[str, Callable] = {}


def register(job_type: str):
    def decorator(fn: Callable):
        HANDLERS[job_type] = fn
        return fn
    return decorator


def enqueue(
    db: Session,
    job_type: str,
    name: str,
    payload: dict | None = None,
    project_id: int | None = None,
    organization_id: int | None = None,
    created_by: int | None = None,
) -> Job:
    job = Job(
        job_type=job_type,
        name=name,
        project_id=project_id,
        organization_id=organization_id,
        created_by=created_by,
        payload=payload or {},
        status="queued",
    )
    db.add(job)
    db.flush()
    return job


def progress(job_id: int, value: int, total: int | None = None, message: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if job:
            job.progress = max(0, int(value))
            if total is not None:
                job.total = int(total)
            if message is not None:
                job.message = message[:500]
            db.commit()
    finally:
        db.close()


def is_cancelled(job_id: int) -> bool:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        return bool(job and job.cancel_requested)
    finally:
        db.close()


def run_job(job_id: int) -> dict[str, Any]:
    db = SessionLocal()
    job = db.get(Job, job_id)
    if job is None:
        return {"error": "Job not found"}
    if job.status not in {"queued", "claimed", "running"}:
        return {"status": job.status}
    handler = HANDLERS.get(job.job_type)
    if handler is None:
        job.status = "failed"
        job.error = f"Unknown job type: {job.job_type}"
        job.finished_at = iso(utcnow())
        db.commit()
        return {"error": job.error}
    job.status = "running"
    job.started_at = iso(utcnow())
    job.message = "Starting"
    db.commit()
    payload = dict(job.payload or {})
    project_id = job.project_id
    organization_id = job.organization_id
    db.close()
    try:
        result = handler(
            db_session_factory=SessionLocal,
            job_id=job_id,
            payload=payload,
            project_id=project_id,
            organization_id=organization_id,
        )
        db = SessionLocal()
        job = db.get(Job, job_id)
        if job:
            if job.cancel_requested:
                job.status = "cancelled"
                job.message = "Cancelled by user"
            else:
                job.status = "succeeded"
                job.message = "Completed"
                job.progress = job.total or job.progress
                job.result = result or {}
            job.finished_at = iso(utcnow())
            db.commit()
        return result or {}
    except Exception as exc:  # noqa: BLE001 - job failures must be recorded, not crash the worker
        db = SessionLocal()
        job = db.get(Job, job_id)
        if job:
            job.status = "failed"
            job.error = f"{type(exc).__name__}: {exc}"
            job.message = job.error[:500]
            job.finished_at = iso(utcnow())
            db.commit()
        return {"error": f"{type(exc).__name__}: {exc}", "traceback": traceback.format_exc()[-2000:]}
    finally:
        db.close()


def claim_next() -> int | None:
    """Atomically claim one queued job (SQLite-safe via conditional UPDATE)."""
    from sqlalchemy import text

    db = SessionLocal()
    try:
        row = db.execute(text(
            "SELECT id FROM jobs WHERE status='queued' ORDER BY created_at, id LIMIT 1"
        )).first()
        if not row:
            return None
        job_id = row[0]
        result = db.execute(text(
            "UPDATE jobs SET status='claimed' WHERE id=:id AND status='queued'"
        ), {"id": job_id})
        db.commit()
        return job_id if result.rowcount else None
    finally:
        db.close()
