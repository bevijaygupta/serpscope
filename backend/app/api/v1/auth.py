"""Authentication endpoints."""
from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import select

from app.api.deps import DB, UserDep, bearer, current_user
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.models.auth import Membership, User
from app.services.rate_limiting import (
    LOGIN_ACCOUNT_LIMIT,
    WINDOW_SECONDS,
    account_login_key,
    consume as consume_rate_limit,
)
from app.services.token_revocation import revoke_token
from app.schemas.common import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DB):
    email = payload.email.strip().lower()
    # The demo account is intentionally public and must remain available from
    # a shared edge egress; a per-account limit here would block every visitor.
    if settings.rate_limit_enabled and email != settings.demo_email:
        count, retry_after = consume_rate_limit(
            db, account_login_key(email), time.time(), WINDOW_SECONDS
        )
        if count > LOGIN_ACCOUNT_LIMIT:
            raise HTTPException(
                429, "Too many requests", headers={"Retry-After": str(retry_after)}
            )
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    if not user.is_active:
        raise HTTPException(403, "User is inactive")
    return TokenResponse(access_token=create_access_token(
        str(user.id), {"role": user.global_role, "ver": user.token_version}
    ))


@router.get("/me", response_model=UserResponse)
def me(user: UserDep):
    return UserResponse(id=user.id, email=user.email, full_name=user.full_name, global_role=user.global_role)


@router.post("/logout")
def logout(
    db: DB,
    user: UserDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
):
    """Revoke the presented bearer token until its original expiry."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(401, "Authentication required")
    revoke_token(db, credentials.credentials)
    return {"detail": "Token revoked", "token_type": "bearer"}


@router.post("/logout-all")
def logout_all(db: DB, user: UserDep):
    """Invalidate every previously issued token for the current account."""
    user.token_version += 1
    db.commit()
    return {"detail": "All sessions signed out", "token_type": "bearer"}


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, db: DB):
    """Optional local-development account creation. Disabled by default in production."""
    if not settings.self_registration_enabled:
        raise HTTPException(403, "Self-registration is disabled")
    email = payload.email
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
