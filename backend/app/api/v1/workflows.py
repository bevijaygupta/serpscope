"""Automation workflow builder endpoints."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import paged, serialize
from app.models.operations import Workflow, WorkflowRun
from app.services.jobs import enqueue

router = APIRouter(prefix="/workflows", tags=["workflows"])

WORKFLOW_COLUMNS = ["id", "name", "description", "trigger", "schedule", "steps", "enabled", "last_run_at", "notification_email"]
RUN_COLUMNS = ["id", "workflow_id", "status", "step_results", "error", "started_at", "finished_at", "job_id"]

STEP_LIBRARY = [
    {"type": "public_audit", "label": "Queue public audit (public evidence)", "safe": True},
    {"type": "crawl", "label": "Schedule crawl", "safe": True},
    {"type": "detect_issues", "label": "Detect new issues", "safe": True},
    {"type": "detect_orphans", "label": "Identify orphans", "safe": True},
    {"type": "cluster_keywords", "label": "Cluster keywords", "safe": True},
    {"type": "map_keywords", "label": "Map keywords to pages", "safe": True},
    {"type": "content_analysis", "label": "Analyse content", "safe": True},
    {"type": "link_suggestions", "label": "Generate link suggestions", "safe": True},
    {"type": "generate_report", "label": "Generate report", "safe": True},
    {"type": "migration_validate", "label": "Validate migration", "safe": True},
    {"type": "ai_readiness", "label": "AI readiness audit", "safe": True},
    {"type": "notify", "label": "Notification (requires configured provider)", "safe": True},
]


@router.get("/step-library")
def step_library():
    return {
        "items": STEP_LIBRARY,
        "note": "No destructive step is available. 'Queue public audit' appends a new source-tracked public audit from crawl evidence; no vendor API is called.",
    }


@router.get("")
def list_workflows(db: DB, project: ProjectDep):
    rows = db.scalars(select(Workflow).where(Workflow.project_id == project.id).order_by(Workflow.id)).all()
    return {"items": [serialize(r, WORKFLOW_COLUMNS) for r in rows]}


@router.post("", status_code=201)
def create_workflow(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    steps = payload.get("steps") or []
    allowed = {s["type"] for s in STEP_LIBRARY}
    for step in steps:
        step_type = step.get("type") if isinstance(step, dict) else step
        if step_type not in allowed:
            raise HTTPException(400, f"Unsupported step: {step_type}")
    wf = Workflow(
        project_id=project.id, name=payload.get("name", "Workflow"),
        description=payload.get("description", ""),
        trigger=payload.get("trigger", "manual"), schedule=payload.get("schedule", ""),
        steps=steps, enabled=bool(payload.get("enabled", True)),
        notification_email=payload.get("notification_email", ""),
    )
    db.add(wf)
    db.commit()
    return {"id": wf.id}


@router.patch("/{workflow_id}")
def update_workflow(workflow_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    wf = db.get(Workflow, workflow_id)
    if wf is None:
        raise HTTPException(404, "Workflow not found")
    for key in ("name", "description", "trigger", "schedule", "steps", "enabled", "notification_email"):
        if key in payload:
            setattr(wf, key, payload[key])
    db.commit()
    return {"success": True}


@router.post("/{workflow_id}/run", status_code=202)
def run_workflow(workflow_id: int, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    wf = db.get(Workflow, workflow_id)
    if wf is None or wf.project_id != project.id:
        raise HTTPException(404, "Workflow not found")
    job = enqueue(db, "run_workflow", f"Run workflow: {wf.name}", {"workflow_id": workflow_id},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/runs")
def runs(db: DB, project: ProjectDep, workflow_id: int | None = None, offset: int = 0, limit: int = 100):
    query = select(WorkflowRun).where(WorkflowRun.project_id == project.id)
    if workflow_id:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, WorkflowRun.id.desc())
    return paged([serialize(r, RUN_COLUMNS) for r in items], total, offset, limit)


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: DB, project: ProjectDep):
    run = db.get(WorkflowRun, run_id)
    if run is None or run.project_id != project.id:
        raise HTTPException(404, "Run not found")
    return serialize(run, RUN_COLUMNS)
