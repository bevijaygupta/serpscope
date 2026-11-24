"""Anonymous, in-process presence counter for the live visitor badge.

This is deliberately not Google Analytics Realtime. It stores only a salted hash
of a random per-tab session id with an expiry, and never records an IP address,
cookie, referrer, user id or Google identifier. Counts reset on API restart.
"""
from __future__ import annotations

import hashlib
import re
import threading
import time

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/presence", tags=["presence"])

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
TTL_SECONDS = 60
_lock = threading.Lock()
_sessions: dict[str, float] = {}
NOTE = (
    "Anonymous active browser sessions only. No IP address, cookie, referrer, "
    "user identity or Google identifier is stored. Counts reset when the API restarts."
)


def _prune(now: float) -> None:
    expired = [key for key, expires_at in _sessions.items() if expires_at <= now]
    for key in expired:
        _sessions.pop(key, None)


def active_count() -> int:
    with _lock:
        _prune(time.monotonic())
        return len(_sessions)


@router.post("/ping")
def ping(payload: dict) -> dict:
    """Refresh one anonymous session and return the current active count."""
    session_id = str(payload.get("session_id") or "").strip()
    if not SESSION_ID_PATTERN.fullmatch(session_id):
        raise HTTPException(400, "Invalid anonymous session id")
    # Hash before storage so the raw browser token is never held server-side.
    key = hashlib.sha256(session_id.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _lock:
        _prune(now)
        _sessions[key] = now + TTL_SECONDS
        count = len(_sessions)
    return {
        "active": count,
        "ttl_seconds": TTL_SECONDS,
        "note": NOTE,
    }


@router.get("/count")
def count() -> dict:
    """Read the current anonymous active-session count."""
    return {"active": active_count(), "ttl_seconds": TTL_SECONDS, "note": NOTE}
