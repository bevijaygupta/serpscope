"""Database engine, session factory and schema bootstrap."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine_kwargs: dict = {"pool_pre_ping": True, "future": True}
if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "", 1)
    if db_path and db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}

engine = create_engine(settings.database_url, **engine_kwargs)

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _):  # pragma: no cover - environment specific
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import Base  # noqa: F401  (import registers all tables)

    Base.metadata.create_all(bind=engine)
    _ensure_ai_observation_columns()


def _ensure_ai_observation_columns() -> None:
    """Idempotent shim for hosts that deploy with create_all but not Alembic.

    Revision 0003 ships the same columns as an explicit migration. This guard
    only adds them when an older database is missing them, so a plain code
    deploy never leaves the AI module querying non-existent columns.
    """
    inspector = inspect(engine)
    if "ai_visibility_records" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("ai_visibility_records")}
    additions = []
    if "answer_url" not in existing:
        additions.append("ALTER TABLE ai_visibility_records ADD COLUMN answer_url TEXT NOT NULL DEFAULT ''")
    if "locale" not in existing:
        additions.append("ALTER TABLE ai_visibility_records ADD COLUMN locale VARCHAR(20) NOT NULL DEFAULT ''")
    if not additions:
        return
    with engine.begin() as connection:
        for statement in additions:
            connection.execute(text(statement))
