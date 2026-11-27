"""Job monitoring, cancellation and live progress."""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write, get_project
from app.api.v1._helpers import paged, serialize
from app.core.security import decode_access_token
from app.services.token_revocation import is_token_revoked
from app.models.auth import Membership, User
from app.models.projects import Job, Project

router = APIRouter(prefix="/jobs", tags=["jobs"])

COLUMNS = ["id", "project_id", "job_type", "name", "status", "progress", "total", "message", "error", "created_at", "started_at", "finished_at", "result"]


@router.get("")
def list_jobs(db: DB, user: UserDep, project_id: int | None = None, status_filter: str | None = None,
              offset: int = 0, limit: int = 100):
    query = select(Job)
    if project_id:
        get_project(db, project_id, user)
        query = query.where(Job.project_id == project_id)
    elif user.global_role not in {"owner", "admin"}:
        allowed = db.scalars(select(Project.id).join(
            Membership, Membership.organization_id == Project.organization_id
        ).where(Membership.user_id == user.id)).all()
        query = query.where(Job.project_id.in_(allowed or [-1]))
    if status_filter:
        query = query.where(Job.status == status_filter)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, Job.id.desc())
    return paged([serialize(j, COLUMNS) for j in items], total, offset, limit)


def _authorize_job(db, user, job: Job) -> None:
    if job.project_id is None:
        if user.global_role not in {"owner", "admin"}:
            raise HTTPException(404, "Job not found")
        return
    get_project(db, job.project_id, user)


@router.get("/{job_id}")
def get_job(job_id: int, db: DB, user: UserDep):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    _authorize_job(db, user, job)
    return serialize(job, COLUMNS + ["payload", "cancel_requested"])


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, db: DB, user: UserDep):
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    _authorize_job(db, user, job)
    check_write(user)
    if job.status in {"succeeded", "failed", "cancelled"}:
        return {"success": False, "detail": f"Job already {job.status}"}
    job.cancel_requested = True
    job.message = "Cancellation requested"
    db.commit()
    return {"success": True, "detail": "Cancellation requested; the worker checks between batches"}


@router.websocket("/ws/{job_id}")
async def job_progress(websocket: WebSocket, job_id: int):
    """Polling-based WebSocket progress (works with database-backed queues).

    Authentication is required. Clients may supply `Authorization: Bearer ...`
    or a `token` query parameter for browser clients that cannot set headers.
    """
    from app.db.session import SessionLocal

    header = websocket.headers.get("authorization", "")
    token = header[7:].strip() if header.lower().startswith("bearer ") else websocket.query_params.get("token", "")
    payload = decode_access_token(token) if token else None
    if not payload or not payload.get("sub"):
        await websocket.close(code=4401)
        return

    auth_db = SessionLocal()
    try:
        if is_token_revoked(auth_db, token):
            await websocket.close(code=4401)
            return
        user = auth_db.get(User, int(payload["sub"]))
        if user is None or not user.is_active:
            await websocket.close(code=4401)
            return
        job = auth_db.get(Job, job_id)
        if job is None:
            await websocket.close(code=4404)
            return
        try:
            if job.project_id is None:
                if user.global_role not in {"owner", "admin"}:
                    await websocket.close(code=4403)
                    return
            else:
                get_project(auth_db, job.project_id, user)
        except HTTPException:
            await websocket.close(code=4403)
            return
    finally:
        auth_db.close()

    await websocket.accept()
    try:
        for _ in range(7200):
            db = SessionLocal()
            try:
                job = db.get(Job, job_id)
                if job is None:
                    await websocket.send_json({"error": "Job not found"})
                    break
                await websocket.send_json({
                    "id": job.id, "status": job.status, "progress": job.progress,
                    "total": job.total, "message": job.message, "error": job.error,
                    "result": job.result,
                })
                if job.status in {"succeeded", "failed", "cancelled"}:
                    break
            finally:
                db.close()
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        return
