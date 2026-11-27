"""Shared API helpers for pagination, serialisation and exports."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.auth import AuditLog
from app.services.exports import make_export


def audit(db: Session, user, action: str, target: str, details: dict | None = None,
          project_id: int | None = None, organization_id: int | None = None) -> None:
    db.add(AuditLog(
        organization_id=organization_id or (getattr(user, "organization_id", None)),
        user_id=getattr(user, "id", None), project_id=project_id, action=action,
        target=target, details=details or {},
    ))


def serialize(row: Any, columns: list[str] | None = None) -> dict:
    if isinstance(row, dict):
        return {k: row.get(k) for k in columns} if columns else dict(row)
    if columns is None:
        columns = [c.name for c in row.__table__.columns]
    return {c: getattr(row, c, None) for c in columns}


def page_query(db: Session, query, offset: int, limit: int, order_by=None) -> tuple[list[Any], int]:
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    if order_by is not None:
        query = query.order_by(order_by)
    return list(db.scalars(query.offset(offset).limit(limit)).all()), total


def paged(items: list, total: int, offset: int, limit: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": offset // max(1, limit) + 1,
        "page_size": limit,
        "has_more": offset + limit < total,
    }


def export_path(base: str, suffix: str) -> Path:
    """Return a collision-free on-disk path for a generated export."""
    settings.export_path.mkdir(parents=True, exist_ok=True)
    clean_suffix = suffix.lstrip(".").lower() or "bin"
    return settings.export_path / f"{base}_{uuid4().hex[:12]}.{clean_suffix}"


def download(rows, columns: list[str], base: str, fmt: str = "csv", pdf_sections=None) -> FileResponse:
    try:
        content, media_type, filename = make_export(fmt, rows, columns, base, pdf_sections)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    path = export_path(base, Path(filename).suffix)
    path.write_bytes(content)
    return FileResponse(str(path), media_type=media_type, filename=filename)
