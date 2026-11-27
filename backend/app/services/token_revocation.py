"""Persistent, shared bearer-token revocation.

Only an HMAC digest of a token is stored, never the token itself. The database
is the source of truth so a logout is visible to every API worker and survives
a process restart. Expired records are removed lazily on the next revocation.
"""
from __future__ import annotations

import time

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token, token_digest
from app.models.auth import RevokedToken


def revoke_token(db: Session, token: str) -> int:
    """Revoke one valid token until its original expiry. Returns that expiry."""
    payload = decode_access_token(token)
    if not payload or "exp" not in payload:
        raise ValueError("Invalid or expired token")
    expiry = int(payload["exp"])
    digest = token_digest(token)

    now = int(time.time())
    db.execute(delete(RevokedToken).where(RevokedToken.expires_at < now))
    if db.scalar(select(RevokedToken.id).where(RevokedToken.token_digest == digest)) is None:
        db.add(RevokedToken(token_digest=digest, expires_at=expiry))
    try:
        db.commit()
    except IntegrityError:  # concurrent logout for the same token
        db.rollback()
    return expiry


def is_token_revoked(db: Session, token: str) -> bool:
    """True only for an explicitly revoked token that has not yet expired."""
    digest = token_digest(token)
    expiry = db.scalar(
        select(RevokedToken.expires_at).where(RevokedToken.token_digest == digest)
    )
    return expiry is not None and int(expiry) >= int(time.time())
