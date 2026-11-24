"""Non-destructive workflow execution and simple interval scheduling."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.models.operations import Workflow, WorkflowRun
from app.models.projects import Project
from app.services import content, domains, issues, keywords, links, orphans, reports
from app.services.jobs import enqueue


def _queue_public_audit(db: Session, project_id: int, config: dict | None) -> dict:
    """Queue a public-evidence audit instead of running a vendor or destructive step."""
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found for scheduled public audit")
    config = config or {}
    body = {
        "start_url": config.get("start_url") or project.domain,
        "name": config.get("name") or f"Scheduled public audit · {project.domain}",
        "config": config.get("config") or {},
    }
    job = enqueue(
        db, "public_audit", body["name"], body,
        project_id=project_id, organization_id=project.organization_id,
    )
    return {
        "status": "queued",
        "job_id": job.id,
        "note": "Public audit queued from the workflow. It uses public evidence only and is never synthetic.",
    }


STEP_HANDLERS = {
    "public_audit": lambda db, p, c: _queue_public_audit(db, p, c),
    "detect_issues": lambda db, p, c: issues.detect_issues(db, p),
    "detect_orphans": lambda db, p, c: orphans.detect_orphans(db, p, c),
    "cluster_keywords": lambda db, p, c: keywords.cluster_keywords(db, p, (c or {}).get("method", "normalized"), c),
    "map_keywords": lambda db, p, c: keywords.map_clusters_to_urls(db, p, c),
    "content_analysis": lambda db, p, c: content.analyse_content(db, p),
    "link_suggestions": lambda db, p, c: links.analyse_graph(db, p),
    "generate_report": lambda db, p, c: reports.generate_weekly_report(db, p, **(c or {})),
    "migration_validate": lambda db, p, c: domains.migration_validate(db, p, c),
    "ai_readiness": lambda db, p, c: domains.ai_readiness(db, p),
    "local_audit": lambda db, p, c: domains.local_audit(db, p),
    "ecommerce_audit": lambda db, p, c: domains.ecommerce_audit(db, p),
    "competitor_analysis": lambda db, p, c: domains.competitor_analysis(db, p, c),
    "international_plan": lambda db, p, c: domains.build_international_plan(db, p, c),
}


def execute_workflow(db: Session, workflow_id: int, job_id: int | None = None) -> dict[str, Any]:
    workflow = db.get(Workflow, workflow_id)
    if workflow is None:
        raise ValueError("Workflow not found")
    run = WorkflowRun(
        workflow_id=workflow_id, project_id=workflow.project_id,
        job_id=job_id, status="running", started_at=iso(utcnow()), step_results=[],
    )
    db.add(run)
    db.flush()
    results = []
    try:
        for index, step in enumerate(workflow.steps or []):
            step_type = step.get("type") if isinstance(step, dict) else str(step)
            config = step.get("config", {}) if isinstance(step, dict) else {}
            if step_type == "crawl":
                result = {"note": "Crawl step requires a crawl job; use the crawler screen to start it with this configuration.", "config": config}
            elif step_type in STEP_HANDLERS:
                result = STEP_HANDLERS[step_type](db, workflow.project_id, config)
            elif step_type == "notify":
                result = {"note": "Notification recorded; outbound delivery requires configured provider", "config": config}
            else:
                result = {"error": f"Unsupported or skipped step: {step_type}"}
            results.append({"index": index, "type": step_type, "result": result})
            run.step_results = results
            db.flush()
        run.status = "succeeded"
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
    run.finished_at = iso(utcnow())
    workflow.last_run_at = iso(utcnow())
    db.commit()
    return {"workflow_run_id": run.id, "status": run.status, "steps": results, "error": run.error}


def due_workflows(db: Session) -> list[Workflow]:
    now = utcnow()
    due = []
    for wf in db.scalars(select_workflows()):
        if not wf.enabled or wf.trigger != "scheduled":
            continue
        if not wf.last_run_at:
            due.append(wf)
            continue
        try:
            last = datetime.fromisoformat(wf.last_run_at.replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
        except ValueError:
            due.append(wf)
            continue
        interval = {"hourly": 1 / 24, "daily": 1, "weekly": 7, "monthly": 30}.get(wf.schedule, 1)
        if (now - last).total_seconds() >= interval * 86400:
            due.append(wf)
    return due


def select_workflows():
    return select(Workflow)
