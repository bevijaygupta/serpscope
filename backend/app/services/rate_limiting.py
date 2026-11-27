"""Shared fixed-window abuse counters backed by the application database.

The previous in-process dictionary worked only for one API worker. Storing the
counters in the shared database keeps the same budget across workers and
restarts. Only an HMAC digest of (UTC day, route bucket, socket peer) is used as
the key; no IP address or request content is written to the table.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets

from sqlalchemy import case, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import RateLimitWindow

WINDOW_SECONDS = 600
LOGIN_ACCOUNT_LIMIT = 10
_PRUNE_EVERY = 64


def account_login_key(email: str) -> str:
    """Digest-only login bucket key; the email itself is never persisted.

    Login is keyed by account rather than socket peer because the hosted UI is
    served through one edge rewrite, where all visitors can share a peer.
    """
    material = b"login-account|" + email.strip().lower().encode("utf-8")
    digest = hmac.new(settings.secret_key.encode(), material, hashlib.sha256).hexdigest()[:32]
    return f"acct-{digest}"


def _retry_after(now: float, start: float, window_seconds: int) -> int:
    elapsed = max(0.0, now - start)
    return max(1, min(window_seconds, math.ceil(window_seconds - elapsed)))


def consume(db: Session, key: str, now: float, window_seconds: int) -> tuple[int, int]:
    """Atomically consume one slot and return ``(count, retry_after)``.

    The conditional UPDATE resets an expired window in the same statement that
    increments it. A rare concurrent insert is resolved by retrying the UPDATE
    after a rollback, so two API workers cannot each get a fresh window.
    """
    if secrets.randbelow(_PRUNE_EVERY) == 0:
        db.execute(
            delete(RateLimitWindow).where(
                RateLimitWindow.window_start < now - (window_seconds * 2)
            )
        )
        db.commit()

    expired = RateLimitWindow.window_start <= now - window_seconds
    statement = (
        update(RateLimitWindow)
        .where(RateLimitWindow.window_key == key)
        .values(
            window_start=case((expired, now), else_=RateLimitWindow.window_start),
            count=case((expired, 1), else_=RateLimitWindow.count + 1),
        )
    )
    result = db.execute(statement)
    if result.rowcount == 0:
        try:
            db.add(RateLimitWindow(window_key=key, window_start=now, count=1))
            db.commit()
            return 1, window_seconds
        except IntegrityError:
            db.rollback()
            db.execute(statement)
    db.commit()

    row = db.execute(
        select(RateLimitWindow.window_start, RateLimitWindow.count).where(
            RateLimitWindow.window_key == key
        )
    ).one()
    return int(row.count), _retry_after(now, float(row.window_start), window_seconds)
