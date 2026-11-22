"""Test fixtures. Run with: pytest -q (from backend/)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
TEST_DB = BACKEND_ROOT / "data" / "test_serpscope.db"
TEST_DB.parent.mkdir(parents=True, exist_ok=True)
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["RUN_JOBS_IN_API"] = "false"
os.environ["SECRET_KEY"] = "test-only-secret"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db()
    yield


@pytest.fixture(autouse=True)
def clean_db():
    db = SessionLocal()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(text(f"DELETE FROM {table.name}"))
        db.commit()
    finally:
        db.close()
    yield


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def demo_project(db):
    from app.services.demo import generate_demo

    return generate_demo(db, size=200, keyword_count=150, include_scenarios=False)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def auth_headers(client):
    response = client.post("/api/v1/auth/login", json={"email": "demo@serpscope.local", "password": "demo1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
