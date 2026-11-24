"""Projects, dashboard overview, tasks, meeting notes and audit logs."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text

from app.api.deps import (
    DB,
    ProjectDep,
    UserDep,
    check_write,
    get_project as authorize_project,
    paginate,
    require_org,
)
from app.api.v1._helpers import audit, paged, serialize
from app.models.auth import AuditLog, Organization
from app.models.inventory import Crawl, UrlRecord
from app.models.analysis import Issue, OrphanRecord
from app.models.keywords import KeywordMapping
from app.models.projects import MeetingNote, Project, ProjectMember, Task
from app.schemas.common import ProjectCreate

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("")
def list_projects(db: DB, user: UserDep, skip: int = 0, limit: int = 100):
    query = select(Project)
    if user.global_role not in {"owner", "admin"}:
        from app.models.auth import Membership

        orgs = db.scalars(select(Membership.organization_id).where(Membership.user_id == user.id)).all()
        query = query.where(Project.organization_id.in_(orgs or [-1]))
    rows = db.scalars(query.order_by(Project.id).offset(skip).limit(limit)).all()
    return {"items": [serialize(r, ["id", "organization_id", "name", "domain", "status", "is_demo", "created_at"]) for r in rows]}


@router.post("", status_code=201)
def create_project(payload: ProjectCreate, db: DB, user: UserDep):
    check_write(user)
    org_id = payload.organization_id
    if org_id is None:
        from app.models.auth import Membership

        org_id = db.scalar(
            select(Membership.organization_id).where(Membership.user_id == user.id).order_by(Membership.id)
        )
        if org_id is None and user.global_role not in {"owner", "admin"}:
            raise HTTPException(403, "No organisation membership")
        if org_id is None:
            org = db.scalar(select(Organization).order_by(Organization.id))
            if org is None:
                org = Organization(name="Default Organisation", slug="default-organisation")
                db.add(org)
                db.flush()
            org_id = org.id
    else:
        require_org(db, user, org_id)
    project = Project(organization_id=org_id, name=payload.name, domain=payload.domain, description=payload.description)
    db.add(project)
    db.flush()
    db.add(ProjectMember(project_id=project.id, user_id=user.id, role="owner"))
    audit(db, user, "project.create", payload.name, project_id=project.id, organization_id=org_id)
    db.commit()
    return serialize(project, ["id", "organization_id", "name", "domain", "status"])


@router.get("/{project_id}")
def get_project(project: ProjectDep):
    return serialize(project, ["id", "organization_id", "name", "domain", "status", "description", "is_demo", "settings", "created_at"])


@router.patch("/{project_id}")
def update_project(project_id: int, payload: dict, db: DB, user: UserDep):
    project = authorize_project(db, project_id, user)
    check_write(user)
    for key in ("name", "domain", "status", "description", "settings"):
        if key in payload:
            setattr(project, key, payload[key])
    audit(db, user, "project.update", project.name, project_id=project_id)
    db.commit()
    return {"success": True}


@router.get("/{project_id}/overview")
def overview(project_id: int, db: DB, project: ProjectDep):
    def scalar(sql: str, params: dict | None = None):
        return db.execute(text(sql), params or {"p": project_id}).scalar() or 0

    open_p = scalar("SELECT COUNT(*) FROM issues WHERE project_id=:p AND priority='P0' AND status NOT IN ('Closed','Resolved')")
    open_p1 = scalar("SELECT COUNT(*) FROM issues WHERE project_id=:p AND priority='P1' AND status NOT IN ('Closed','Resolved')")
    crawl = db.execute(text(
        "SELECT discovered, crawled, failed, summary FROM crawls WHERE project_id=:p ORDER BY id DESC LIMIT 1"
    ), {"p": project_id}).first()
    data_kinds = db.execute(text(
        "SELECT data_kind, COUNT(*) FROM url_records WHERE project_id=:p GROUP BY data_kind"
    ), {"p": project_id}).all()
    return {
        "project": serialize(project, ["id", "name", "domain", "status", "is_demo"]),
        "cards": {
            "active_projects": scalar("SELECT COUNT(*) FROM projects WHERE status='active' AND organization_id=:p", {"p": project.organization_id}),
            "websites_monitored": scalar("SELECT COUNT(DISTINCT domain) FROM projects WHERE organization_id=:p", {"p": project.organization_id}),
            "urls_crawled": scalar("SELECT COUNT(*) FROM url_records WHERE project_id=:p AND crawled IS TRUE", {"p": project_id}),
            "critical_issues": open_p,
            "high_priority_issues": open_p1,
            "high_priority_opportunities": scalar("SELECT COUNT(*) FROM orphan_records WHERE project_id=:p AND priority IN ('P0','P1')", {"p": project_id}),
            "orphan_pages": scalar("SELECT COUNT(*) FROM orphan_records WHERE project_id=:p AND internal_inlinks=0", {"p": project_id}),
            "keyword_mappings_completed": scalar("SELECT COUNT(*) FROM keyword_mappings WHERE project_id=:p", {"p": project_id}),
            "content_opportunities": scalar("SELECT COUNT(*) FROM content_analyses WHERE project_id=:p AND score < 60", {"p": project_id}),
            "active_jobs": scalar("SELECT COUNT(*) FROM jobs WHERE status IN ('queued','claimed','running') AND organization_id=:p", {"p": project.organization_id}),
            "reports_generated": scalar("SELECT COUNT(*) FROM reports WHERE project_id=:p", {"p": project_id}),
        },
        "latest_crawl": {
            "discovered": crawl[0], "crawled": crawl[1], "failed": crawl[2], "summary": crawl[3],
        } if crawl else None,
        "data_composition": [{"data_kind": r[0], "urls": r[1]} for r in data_kinds],
        "provenance_note": "Figures are queried from the database. Demo projects contain synthetic records only.",
    }


@router.get("/{project_id}/tasks")
def list_tasks(project_id: int, db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(Task).where(Task.project_id == project_id), offset, limit, Task.id.desc())
    return paged([serialize(t, ["id", "title", "assignee_id", "status", "priority", "due_date", "issue_id", "approval_status"]) for t in items], total, offset, limit)


@router.post("/{project_id}/tasks", status_code=201)
def create_task(project_id: int, payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    task = Task(project_id=project_id, title=payload.get("title", "Untitled task"),
                description=payload.get("description", ""), assignee_id=payload.get("assignee_id"),
                status=payload.get("status", "open"), priority=payload.get("priority", "P2"),
                due_date=payload.get("due_date"), issue_id=payload.get("issue_id"),
                approval_status=payload.get("approval_status", "not_required"))
    db.add(task)
    audit(db, user, "task.create", task.title, project_id=project_id)
    db.commit()
    return serialize(task, ["id", "title", "status", "priority", "due_date"])


@router.patch("/{project_id}/tasks/{task_id}")
def update_task(project_id: int, task_id: int, payload: dict, db: DB, user: UserDep):
    authorize_project(db, project_id, user)
    task = db.get(Task, task_id)
    if task is None or task.project_id != project_id:
        raise HTTPException(404, "Task not found")
    check_write(user)
    for key in ("title", "description", "assignee_id", "status", "priority", "due_date", "approval_status"):
        if key in payload:
            setattr(task, key, payload[key])
    audit(db, user, "task.update", task.title, project_id=project_id)
    db.commit()
    return {"success": True}


@router.get("/{project_id}/meeting-notes")
def list_notes(project_id: int, db: DB, project: ProjectDep):
    rows = db.scalars(select(MeetingNote).where(MeetingNote.project_id == project_id).order_by(MeetingNote.id.desc()).limit(200)).all()
    return {"items": [serialize(r, ["id", "title", "notes", "meeting_date", "created_at"]) for r in rows]}


@router.post("/{project_id}/meeting-notes", status_code=201)
def add_note(project_id: int, payload: dict, db: DB, user: UserDep):
    authorize_project(db, project_id, user)
    check_write(user)
    note = MeetingNote(project_id=project_id, title=payload.get("title", "Meeting"), notes=payload.get("notes", ""),
                       meeting_date=payload.get("meeting_date"))
    db.add(note)
    db.commit()
    return {"id": note.id}


@router.get("/{project_id}/audit-log")
def audit_log(project_id: int, db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    query = select(AuditLog).where(AuditLog.project_id == project_id)
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, AuditLog.id.desc())
    return paged([serialize(i, ["id", "action", "target", "details", "user_id", "created_at"]) for i in items], total, offset, limit)
