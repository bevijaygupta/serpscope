"""Background job handlers for workflows and scheduled checks."""
from __future__ import annotations

from app.services import workflows
from app.services.jobs import enqueue, progress, register


@register("run_workflow")
def run_workflow_job(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        workflow_id = payload.get("workflow_id")
        progress(job_id, 20, 100, "Executing workflow steps")
        result = workflows.execute_workflow(db, workflow_id, job_id)
        db.commit()
        progress(job_id, 100, 100, "Workflow finished")
        return result
    finally:
        db.close()


@register("scheduler_tick")
def scheduler_tick(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        due = workflows.due_workflows(db)
        for workflow in due:
            enqueue(
                db, "run_workflow", f"Scheduled: {workflow.name}",
                {"workflow_id": workflow.id},
                project_id=workflow.project_id,
                organization_id=organization_id,
                created_by=payload.get("created_by"),
            )
        db.commit()
        return {"due_workflows": [w.id for w in due]}
    finally:
        db.close()
