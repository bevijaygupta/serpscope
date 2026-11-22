"""Technical SEO issue management and high-value 404 workflow."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.analysis import Issue, IssueUrl
from app.schemas.common import IssueUpdate
from app.services import issues as issue_service
from app.services.jobs import enqueue

router = APIRouter(prefix="/technical", tags=["technical"])

ISSUE_COLUMNS = [
    "id", "code", "name", "category", "severity", "priority", "priority_score",
    "business_impact", "affected_count", "page_templates", "evidence",
    "priority_explanation", "recommended_fix", "owner", "status", "due_date",
    "validation_status", "detected_at", "source",
]

VALID_STATUSES = ["Detected", "Reviewed", "Approved", "Assigned", "Implemented", "Validated", "Closed", "Resolved"]


@router.post("/detect", status_code=202)
def detect(project_id: int, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "detect_issues", "Technical audit", {}, project_id=project.id,
                  organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.get("/issues")
def list_issues(db: DB, project: ProjectDep, priority: str | None = None, status: str | None = None,
                category: str | None = None, q: str | None = None, offset: int = 0, limit: int = 100):
    query = select(Issue).where(Issue.project_id == project.id)
    if priority:
        query = query.where(Issue.priority == priority)
    if status:
        query = query.where(Issue.status == status)
    if category:
        query = query.where(Issue.category == category)
    if q:
        query = query.where(Issue.name.ilike(f"%{q}%") | Issue.code.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, Issue.priority_score.desc())
    return paged([serialize(i, ISSUE_COLUMNS) for i in items], total, offset, limit)


@router.get("/issues/{issue_id}")
def get_issue(issue_id: int, db: DB, project: ProjectDep):
    issue = db.get(Issue, issue_id)
    if issue is None or issue.project_id != project.id:
        raise HTTPException(404, "Issue not found")
    data = serialize(issue, ISSUE_COLUMNS)
    urls = db.scalars(select(IssueUrl).where(IssueUrl.issue_id == issue_id).limit(1000)).all()
    data["affected_urls"] = [serialize(u, ["url", "evidence"]) for u in urls]
    return data


@router.patch("/issues/{issue_id}")
def update_issue(issue_id: int, payload: IssueUpdate, db: DB, user: UserDep):
    check_write(user)
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(404, "Issue not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("status") and data["status"] not in VALID_STATUSES:
        raise HTTPException(400, f"Invalid status. Allowed: {VALID_STATUSES}")
    for key, value in data.items():
        setattr(issue, key, value)
    db.commit()
    return {"success": True, "status": issue.status}


@router.get("/high-value-404s")
def high_value_404s(db: DB, project: ProjectDep, limit: int = 200):
    rows = issue_service.high_value_404s(db, project.id)
    return {"items": rows[:limit], "total": len(rows), "method": "supplied business metrics + rule-based replacement matching"}


@router.get("/export")
def export_issues(db: DB, project: ProjectDep, format: str = "csv"):
    rows = db.scalars(select(Issue).where(Issue.project_id == project.id).limit(20000)).all()
    return download([serialize(r, ISSUE_COLUMNS) for r in rows], ISSUE_COLUMNS, f"technical_issues_project_{project.id}", format)
