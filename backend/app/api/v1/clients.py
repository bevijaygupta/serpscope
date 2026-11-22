"""Client organisations, team membership and project permissions."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DB, UserDep, check_write
from app.api.v1._helpers import audit, serialize
from app.core.security import hash_password
from app.models.auth import Membership, Organization, User
from app.models.projects import Project, ProjectMember

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("/organizations")
def organizations(db: DB, user: UserDep):
    query = select(Organization)
    if user.global_role not in {"owner", "admin"}:
        orgs = db.scalars(select(Membership.organization_id).where(Membership.user_id == user.id)).all()
        query = query.where(Organization.id.in_(orgs or [-1]))
    rows = db.scalars(query.order_by(Organization.id)).all()
    return {"items": [serialize(o, ["id", "name", "slug", "plan", "is_demo", "retention_days"]) for o in rows]}


@router.post("/organizations", status_code=201)
def create_organization(payload: dict, db: DB, user: UserDep):
    check_write(user)
    slug = str(payload.get("slug") or payload.get("name", "org")).lower().replace(" ", "-")[:90]
    if db.scalar(select(Organization).where(Organization.slug == slug)):
        raise HTTPException(409, "Slug already exists")
    org = Organization(name=payload.get("name", "Organisation"), slug=slug,
                       plan=payload.get("plan", "client"), retention_days=int(payload.get("retention_days", 365)))
    db.add(org)
    db.flush()
    db.add(Membership(user_id=user.id, organization_id=org.id, role="owner"))
    audit(db, user, "organization.create", org.name, organization_id=org.id)
    db.commit()
    return serialize(org, ["id", "name", "slug", "plan"])


@router.get("/organizations/{org_id}/projects")
def org_projects(org_id: int, db: DB, user: UserDep):
    rows = db.scalars(select(Project).where(Project.organization_id == org_id).order_by(Project.id)).all()
    return {"items": [serialize(p, ["id", "name", "domain", "status", "is_demo"]) for p in rows]}


@router.get("/organizations/{org_id}/members")
def members(org_id: int, db: DB, user: UserDep):
    rows = db.execute(
        select(User, Membership).join(Membership, Membership.user_id == User.id).where(Membership.organization_id == org_id)
    ).all()
    return {"items": [{"user_id": u.id, "email": u.email, "full_name": u.full_name, "role": m.role} for u, m in rows]}


@router.post("/organizations/{org_id}/members", status_code=201)
def add_member(org_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    email = str(payload.get("email", "")).strip().lower()
    target = db.scalar(select(User).where(User.email == email))
    if target is None:
        target = User(email=email, full_name=payload.get("full_name", ""),
                      hashed_password=hash_password(str(payload.get("password", "changeme123"))),
                      global_role=payload.get("global_role", "viewer"))
        db.add(target)
        db.flush()
    role = payload.get("role", "viewer")
    if role not in {"owner", "admin", "editor", "viewer"}:
        raise HTTPException(400, "Invalid role")
    db.add(Membership(user_id=target.id, organization_id=org_id, role=role))
    audit(db, user, "member.add", email, organization_id=org_id, details={"role": role})
    db.commit()
    return {"user_id": target.id, "role": role}


@router.get("/projects/{project_id}/permissions")
def project_permissions(project_id: int, db: DB, user: UserDep):
    rows = db.execute(
        select(User, ProjectMember).join(ProjectMember, ProjectMember.user_id == User.id)
        .where(ProjectMember.project_id == project_id)
    ).all()
    return {"items": [{"user_id": u.id, "email": u.email, "role": m.role} for u, m in rows]}


@router.post("/projects/{project_id}/permissions", status_code=201)
def set_permission(project_id: int, payload: dict, db: DB, user: UserDep):
    check_write(user)
    uid = int(payload.get("user_id"))
    role = payload.get("role", "editor")
    if role not in {"owner", "admin", "editor", "viewer"}:
        raise HTTPException(400, "Invalid role")
    existing = db.scalar(select(ProjectMember).where(
        ProjectMember.project_id == project_id, ProjectMember.user_id == uid
    ))
    if existing:
        existing.role = role
    else:
        db.add(ProjectMember(project_id=project_id, user_id=uid, role=role))
    audit(db, user, "permission.update", str(uid), project_id=project_id, details={"role": role})
    db.commit()
    return {"success": True}
