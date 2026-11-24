"""Authentication endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from app.api.deps import DB, UserDep, current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth import Membership, User
from app.schemas.common import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DB):
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    return TokenResponse(access_token=create_access_token(str(user.id), {"role": user.global_role}))


@router.get("/me", response_model=UserResponse)
def me(user: UserDep):
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, global_role=user.global_role)


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: LoginRequest, db: DB):
    """Local-development account creation. Production deployments should use SSO/admin provisioning."""
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, hashed_password=hash_password(payload.password), global_role="viewer")
    db.add(user)
    db.commit()
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, global_role=user.global_role)


@router.get("/users", response_model=list[UserResponse])
def list_users(db: DB, user: UserDep):
    query = select(User)
    if user.global_role not in {"owner", "admin"}:
        orgs = db.scalars(select(Membership.organization_id).where(Membership.user_id == user.id)).all()
        query = query.join(Membership, Membership.user_id == User.id).where(
            Membership.organization_id.in_(orgs or [-1])
        ).distinct()
    rows = db.scalars(query.order_by(User.id).limit(1000)).all()
    return [UserResponse(id=r.id, email=r.email, full_name=r.full_name, global_role=r.global_role) for r in rows]
