"""Authentication, authorisation and shared API helpers."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.auth import Membership, Organization, User
from app.models.projects import Project

bearer = HTTPBearer(auto_error=False)

DB = Annotated[Session, Depends(get_db)]


def current_user(
    db: DB,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    payload = decode_access_token(credentials.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Inactive user")
    return user


UserDep = Annotated[User, Depends(current_user)]


def require_roles(*roles: str):
    def dependency(user: UserDep) -> User:
        if user.global_role in {"owner", "admin"}:
            return user
        if roles and not any(role in roles for role in (user.global_role,)):
            raise HTTPException(status_code=403, detail="Insufficient role")
        return user

    return dependency


def get_project(db: DB, project_id: int, user: UserDep) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    if user.global_role in {"owner", "admin"}:
        return project
    membership = db.scalar(select(Membership).where(
        Membership.user_id == user.id, Membership.organization_id == project.organization_id
    ))
    if membership is None:
        raise HTTPException(403, "No access to this project")
    return project


ProjectDep = Annotated[Project, Depends(get_project)]


def paginate(page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500)) -> tuple[int, int]:
    return (page - 1) * page_size, page_size


def check_write(user: User) -> None:
    if user.global_role not in {"owner", "admin", "editor"}:
        raise HTTPException(403, "Write permission required")
