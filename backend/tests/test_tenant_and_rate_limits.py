"""Tenant isolation and shared database abuse-throttling regression tests."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.main import RATE_LIMIT_WINDOW_SECONDS
from app.models.analysis import ContentBrief, Issue, LinkSuggestion
from app.models.auth import Membership, Organization, RateLimitWindow, User
from app.models.keywords import KeywordCluster
from app.models.operations import Integration, Workflow
from app.models.projects import Job, Project, Task


def _tenant(client: TestClient, db, label: str):
    org = Organization(name=f"{label} org", slug=f"{label}-org")
    db.add(org)
    db.flush()
    email = f"{label}@tenant.example"
    editor = User(email=email, hashed_password=hash_password("tenant1234"), global_role="editor")
    outsider = User(
        email=f"{label}-outsider@tenant.example",
        hashed_password=hash_password("tenant1234"),
        global_role="editor",
    )
    db.add_all([editor, outsider])
    db.flush()
    db.add(Membership(user_id=editor.id, organization_id=org.id, role="admin"))
    db.flush()
    project = Project(organization_id=org.id, name=f"{label} project", domain=f"{label}.example")
    db.add(project)
    db.commit()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tenant1234"})
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    return org, project, headers, outsider


def _headers_for(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "tenant1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_project_and_client_endpoints_reject_cross_tenant_access(client, db):
    org_a, project_a, headers_a, _ = _tenant(client, db, "alpha")
    org_b, project_b, _, _ = _tenant(client, db, "beta")

    assert client.patch(
        f"/api/v1/projects/{project_b.id}", headers=headers_a, json={"name": "hijacked"}
    ).status_code == 403
    assert client.post(
        f"/api/v1/projects/{project_b.id}/meeting-notes", headers=headers_a,
        json={"title": "leak", "notes": "leak"},
    ).status_code == 403

    task = Task(project_id=project_b.id, title="Other tenant task")
    db.add(task)
    db.commit()
    assert client.patch(
        f"/api/v1/projects/{project_b.id}/tasks/{task.id}", headers=headers_a,
        json={"status": "done"},
    ).status_code == 403

    assert client.get(f"/api/v1/clients/organizations/{org_b.id}/projects", headers=headers_a).status_code == 403
    assert client.get(f"/api/v1/clients/organizations/{org_b.id}/members", headers=headers_a).status_code == 403
    assert client.get(f"/api/v1/clients/projects/{project_b.id}/permissions", headers=headers_a).status_code == 403
    assert client.post(
        f"/api/v1/clients/projects/{project_b.id}/permissions", headers=headers_a,
        json={"user_id": 1, "role": "viewer"},
    ).status_code == 403

    # A supplied organisation_id cannot plant a project in another tenant.
    created = client.post("/api/v1/projects", headers=headers_a, json={
        "name": "Cross tenant", "domain": "cross.example", "organization_id": org_b.id,
    })
    assert created.status_code == 403

    # Overview counters no longer include another tenant's projects or jobs.
    overview = client.get(f"/api/v1/projects/{project_a.id}/overview", headers=headers_a)
    assert overview.status_code == 200
    assert overview.json()["cards"]["active_projects"] == 1


def test_job_integration_user_and_child_writes_are_scoped(client, db):
    _, project_a, headers_a, outsider_a = _tenant(client, db, "gamma")
    _, project_b, _, _ = _tenant(client, db, "delta")

    job_b = Job(project_id=project_b.id, organization_id=project_b.organization_id,
                job_type="public_audit", name="Other tenant job")
    db.add(job_b)
    db.commit()
    assert client.get("/api/v1/jobs", headers=headers_a).json()["total"] == 0
    assert client.get(f"/api/v1/jobs?project_id={project_b.id}", headers=headers_a).status_code == 403
    assert client.get(f"/api/v1/jobs/{job_b.id}", headers=headers_a).status_code == 403
    assert client.post(f"/api/v1/jobs/{job_b.id}/cancel", headers=headers_a).status_code == 403

    integration = Integration(project_id=project_b.id, organization_id=project_b.organization_id,
                              provider="semrush", display_name="Semrush")
    db.add(integration)
    db.commit()
    assert client.get("/api/v1/integrations", headers=headers_a).json()["items"] == []
    assert client.get(f"/api/v1/integrations/{integration.id}", headers=headers_a).status_code == 403
    planted = client.post("/api/v1/integrations", headers=headers_a, json={
        "project_id": project_b.id, "organization_id": project_b.organization_id,
        "provider": "ahrefs", "mode": "csv_import",
    })
    assert planted.status_code == 403

    users = client.get("/api/v1/auth/users", headers=headers_a).json()
    emails = {row["email"] for row in users}
    assert "gamma@tenant.example" in emails
    assert "delta@tenant.example" not in emails

    brief = ContentBrief(project_id=project_b.id, url="https://delta.example/", primary_keyword="x")
    cluster = KeywordCluster(project_id=project_b.id, name="Other cluster")
    suggestion = LinkSuggestion(project_id=project_b.id, source_url="https://delta.example/a",
                                target_url="https://delta.example/b", status="proposed")
    issue = Issue(project_id=project_b.id, code="missing_title", name="Other issue", severity="High")
    workflow = Workflow(project_id=project_b.id, name="Other workflow", trigger="manual", steps=[])
    db.add_all([brief, cluster, suggestion, issue, workflow])
    db.commit()
    assert client.patch(f"/api/v1/content/briefs/{brief.id}", headers=headers_a,
                        json={"approval_status": "approved"}).status_code == 403
    assert client.patch(f"/api/v1/keywords/clusters/{cluster.id}", headers=headers_a,
                        json={"name": "hijacked"}).status_code == 403
    assert client.patch(f"/api/v1/internal-links/suggestions/{suggestion.id}", headers=headers_a,
                        json={"status": "approved"}).status_code == 403
    assert client.patch(f"/api/v1/technical/issues/{issue.id}", headers=headers_a,
                        json={"status": "Closed"}).status_code == 403
    assert client.patch(f"/api/v1/workflows/{workflow.id}", headers=headers_a,
                        json={"name": "hijacked"}).status_code == 403

    # A member of the caller's own org with no tenant membership stays isolated.
    assert client.get(f"/api/v1/projects/{project_b.id}", headers=_headers_for(
        client, outsider_a.email)).status_code == 403
    assert client.post("/api/v1/demo/reset", headers=headers_a, json={}).status_code == 403


def test_rate_limits_return_generic_429_without_sensitive_keys(client, db, monkeypatch):
    from app.core.config import settings as live_settings

    email = "brute-force@tenant.example"
    monkeypatch.setattr(live_settings, "rate_limit_enabled", True)
    try:
        assert RATE_LIMIT_WINDOW_SECONDS == 600
        status_codes = []
        for _ in range(11):
            response = client.post("/api/v1/auth/login", json={
                "email": email, "password": "wrong",
            })
            status_codes.append(response.status_code)
        assert status_codes[:10] == [401] * 10
        blocked = client.post("/api/v1/auth/login", json={
            "email": email, "password": "wrong",
        })
        assert blocked.status_code == 429
        assert blocked.headers["Retry-After"].isdigit()
        body = blocked.text.lower()
        for secret in ("testclient", "/api/v1/auth/login", email, "wrong"):
            assert secret not in body

        # Login uses a per-account digest key so one shared proxy egress
        # cannot throttle every public demo visitor. No raw email is stored.
        rows = db.query(RateLimitWindow).filter(
            RateLimitWindow.window_key.startswith("acct-")
        ).all()
        assert len(rows) == 1
        assert rows[0].window_key.startswith("acct-")
        assert all(c in "0123456789abcdef" for c in rows[0].window_key[5:])
        assert email not in rows[0].window_key
        assert rows[0].count == 12
        with SessionLocal() as other_session:
            assert other_session.query(RateLimitWindow).filter(
                RateLimitWindow.window_key.startswith("acct-")
            ).count() == 1
    finally:
        db.query(RateLimitWindow).delete()
        db.commit()
        monkeypatch.setattr(live_settings, "rate_limit_enabled", False)


def test_demo_login_is_exempt_from_account_throttle(client, db, monkeypatch):
    """The mandated one-field auto-login must not trip a shared edge bucket."""
    from app.core.config import settings as live_settings

    monkeypatch.setattr(live_settings, "rate_limit_enabled", True)
    try:
        for _ in range(12):
            response = client.post("/api/v1/auth/login", json={
                "email": "demo@serpscope.local", "password": "demo1234",
            })
            assert response.status_code == 200, response.text
        assert db.query(RateLimitWindow).filter(
            RateLimitWindow.window_key.startswith("acct-")
        ).count() == 0
    finally:
        db.query(RateLimitWindow).delete()
        db.commit()
        monkeypatch.setattr(live_settings, "rate_limit_enabled", False)


def test_rate_limit_counter_is_shared_between_sessions(db):
    from app.services.rate_limiting import consume

    key = "shared-window-test"
    now = time.time()
    with SessionLocal() as first, SessionLocal() as second:
        assert consume(first, key, now, 600)[0] == 1
        assert consume(second, key, now, 600)[0] == 2
        assert consume(first, key, now, 600)[0] == 3
    assert db.query(RateLimitWindow).filter(RateLimitWindow.window_key == key).one().count == 3


def test_registration_is_validated_and_can_be_disabled(client, monkeypatch):
    from app.api.v1 import auth as auth_router

    assert client.post("/api/v1/auth/register", json={
        "email": "not-an-email", "password": "long-enough-password",
    }).status_code == 422
    assert client.post("/api/v1/auth/register", json={
        "email": "short@tenant.example", "password": "short",
    }).status_code == 422

    created = client.post("/api/v1/auth/register", json={
        "email": "new.user@tenant.example", "password": "long-enough-password",
    })
    assert created.status_code == 201, created.text
    assert created.json()["global_role"] == "viewer"

    monkeypatch.setattr(auth_router.settings, "allow_self_registration", False)
    blocked = client.post("/api/v1/auth/register", json={
        "email": "blocked@tenant.example", "password": "long-enough-password",
    })
    assert blocked.status_code == 403
    assert blocked.json()["detail"] == "Self-registration is disabled"


def test_self_registration_defaults_off_in_production():
    from app.core.config import Settings

    production = Settings(
        environment="production",
        secret_key="production-test-secret-1234567890abcdef",
        cors_origins="https://serpscopelive.vercel.app",
        database_url="postgresql+psycopg2://user:pass@db.example.com/serpscope",
    )
    development = Settings(environment="development")
    assert production.self_registration_enabled is False
    assert development.self_registration_enabled is True
    assert Settings(
        environment="production",
        secret_key="production-test-secret-1234567890abcdef",
        cors_origins="https://serpscopelive.vercel.app",
        database_url="postgresql+psycopg2://user:pass@db.example.com/serpscope",
        allow_self_registration=True,
    ).self_registration_enabled is True
