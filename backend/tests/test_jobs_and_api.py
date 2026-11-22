from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.auth import Membership, Organization, User
from app.models.projects import Job, Project
from app.services.jobs import HANDLERS, enqueue, is_cancelled, run_job


def _viewer_headers(client: TestClient, db, email: str = "viewer@serpscope.local") -> dict[str, str]:
    viewer = User(email=email, hashed_password=hash_password("viewer1234"), global_role="viewer")
    db.add(viewer)
    db.commit()
    response = client.post("/api/v1/auth/login", json={"email": email, "password": "viewer1234"})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_authentication_is_required_and_invalid_tokens_are_rejected(client, demo_project):
    url = f"/api/v1/inventory/urls?project_id={demo_project['project_id']}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer not-a-real-token"}).status_code == 401
    response = client.post("/api/v1/auth/login", json={"email": "demo@serpscope.local", "password": "wrong"})
    assert response.status_code == 401
    assert client.get("/api/health").status_code == 200
    me = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + client.post(
        "/api/v1/auth/login", json={"email": "demo@serpscope.local", "password": "demo1234"}
    ).json()["access_token"]})
    assert me.status_code == 200
    assert me.json()["global_role"] == "owner"


def test_viewer_membership_scoping_and_write_permissions(client, db, demo_project, auth_headers):
    viewer_headers = _viewer_headers(client, db)
    project_id = demo_project["project_id"]
    read_url = f"/api/v1/inventory/urls?project_id={project_id}"
    write_url = "/api/v1/imports/url-list"

    assert client.get(read_url, headers=viewer_headers).status_code == 403
    write = client.post(write_url, headers=viewer_headers, json={
        "project_id": project_id, "urls": ["https://demo.example.com/viewer-blocked/"],
    })
    assert write.status_code == 403

    viewer = db.query(User).filter(User.email == "viewer@serpscope.local").one()
    db.add(Membership(user_id=viewer.id, organization_id=demo_project["organization_id"], role="viewer"))
    db.commit()

    assert client.get(read_url, headers=viewer_headers).status_code == 200
    write = client.post(write_url, headers=viewer_headers, json={
        "project_id": project_id, "urls": ["https://demo.example.com/viewer-blocked/"],
    })
    assert write.status_code == 403

    other_org = Organization(name="Other client", slug="other-client")
    db.add(other_org)
    db.flush()
    other_project = Project(organization_id=other_org.id, name="Other project", domain="other.example.com")
    db.add(other_project)
    db.commit()
    assert client.get(f"/api/v1/inventory/urls?project_id={other_project.id}",
                      headers=viewer_headers).status_code == 403

    owner_response = client.get(read_url, headers=auth_headers)
    assert owner_response.status_code == 200
    assert owner_response.json()["total"] == demo_project["urls"]


def test_pagination_and_exports_are_bounded(client, auth_headers, demo_project):
    base = f"/api/v1/inventory/urls?project_id={demo_project['project_id']}"
    first = client.get(base + "&limit=2&offset=0", headers=auth_headers).json()
    second = client.get(base + "&limit=2&offset=2", headers=auth_headers).json()
    assert first["total"] == second["total"] == demo_project["urls"]
    assert len(first["items"]) == len(second["items"]) == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert first["has_more"] is True
    assert client.get(base + "&limit=501", headers=auth_headers).status_code == 422

    csv_response = client.get(
        f"/api/v1/inventory/export?project_id={demo_project['project_id']}"
        "&format=csv&columns=id,url,data_kind",
        headers=auth_headers,
    )
    assert csv_response.status_code == 200
    assert "attachment" in csv_response.headers["content-disposition"]
    assert csv_response.content.startswith(b"\xef\xbb\xbfid,url,data_kind")
    assert len(csv_response.content) < 200_000

    xlsx_response = client.get(
        f"/api/v1/inventory/export?project_id={demo_project['project_id']}&format=xlsx",
        headers=auth_headers,
    )
    assert xlsx_response.status_code == 200
    assert xlsx_response.content.startswith(b"PK")


def test_crawler_start_accepts_the_ui_payload_shape(client, auth_headers, demo_project):
    url = f"/api/v1/crawler/start?project_id={demo_project['project_id']}"
    bad = client.post(url, headers=auth_headers, json={"max_urls": 10})
    assert bad.status_code == 400

    response = client.post(url, headers=auth_headers, json={
        "config": {
            "start_url": "https://demo.example.com/",
            "max_urls": 25,
            "max_depth": 2,
            "concurrency": 2,
            "crawl_delay": 0.5,
            "respect_robots": True,
            "follow_external": False,
            "allow_private": False,
        }
    })
    assert response.status_code == 202, response.text
    assert response.json()["status"] == "queued"
    job_id = response.json()["job_id"]
    detail = client.get(f"/api/v1/jobs/{job_id}", headers=auth_headers).json()
    assert detail["job_type"] == "crawl"
    assert detail["payload"]["config"]["crawl_delay"] == 0.5


def test_job_progress_websocket_requires_token_and_project_access(client, auth_headers, demo_project, db):
    job = Job(name="WS test", job_type="test", status="succeeded",
              project_id=demo_project["project_id"])
    db.add(job)
    db.commit()
    path = f"/api/v1/jobs/ws/{job.id}"

    try:
        with client.websocket_connect(path) as socket:
            socket.receive_json()
        pytest.fail("Unauthenticated WebSocket should be rejected")
    except WebSocketDisconnect:
        pass

    token = auth_headers["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(f"{path}?token={token}") as socket:
        message = socket.receive_json()
    assert message["id"] == job.id
    assert message["status"] == "succeeded"


def test_job_cancellation_is_recorded_and_honoured_by_worker(client, auth_headers, db, demo_project):
    def cancellable_handler(db_session_factory, job_id, payload, project_id, organization_id):
        ticks = 0
        while ticks < 100:
            if is_cancelled(job_id):
                return {"ticks": ticks, "stopped": True}
            ticks += 1
        return {"ticks": ticks, "stopped": False}

    HANDLERS["test_cancellable"] = cancellable_handler
    job = enqueue(
        db, "test_cancellable", "Cancellation test", {},
        project_id=demo_project["project_id"],
        organization_id=demo_project["organization_id"],
    )
    db.commit()

    response = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["success"] is True

    result = run_job(job.id)
    assert result == {"ticks": 0, "stopped": True}

    fresh = SessionLocal()
    try:
        stored = fresh.get(Job, job.id)
        assert stored.status == "cancelled"
        assert stored.cancel_requested is True
        assert stored.finished_at
    finally:
        fresh.close()

    again = client.post(f"/api/v1/jobs/{job.id}/cancel", headers=auth_headers)
    assert again.json()["success"] is False

    listed = client.get(f"/api/v1/jobs?project_id={demo_project['project_id']}&limit=5",
                        headers=auth_headers).json()
    assert listed["total"] >= 1
    assert listed["items"][0]["status"] == "cancelled"
    HANDLERS.pop("test_cancellable", None)


def test_public_audit_routes_and_exports_are_registered(client, db, auth_headers, demo_project):
    project = db.get(Project, demo_project["project_id"])
    project.settings = {"public_audit": True}
    db.commit()
    base = f"/api/v1/audits/projects/{project.id}/public-audit"

    audit = client.get(base, headers=auth_headers)
    assert audit.status_code == 200, audit.text
    payload = audit.json()
    assert payload["meta"]["method"] == "public_evidence_audit"
    assert len(payload["roadmap"]) == 6
    assert "No Search Console queries" in " ".join(payload["missing_data"])

    reports = client.get(base + "/reports", headers=auth_headers)
    assert reports.status_code == 200
    assert "items" in reports.json()

    deck = client.get(base + "/export?format=pptx", headers=auth_headers)
    assert deck.status_code == 200
    assert deck.content.startswith(b"PK")
    assert "attachment" in deck.headers["content-disposition"]

    case_study = client.get(f"/api/v1/public/case-studies/{project.id}")
    assert case_study.status_code == 200
    assert case_study.json()["meta"]["project_id"] == project.id

    # The body is optional so the Overview one-click button can POST with no JSON.
    started = client.post(base + "/start", headers=auth_headers)
    assert started.status_code == 202, started.text
    assert started.json()["status"] == "queued"


def test_bootstrap_reuses_existing_demo_organisation(db):
    from app.main import bootstrap

    db.query(Membership).delete()
    db.query(User).delete()
    db.add(Organization(name="Demo Organisation", slug="demo-organisation", is_demo=True))
    db.commit()

    bootstrap()
    bootstrap()
    db.expire_all()

    assert db.query(Organization).filter(Organization.slug == "demo-organisation").count() == 1
    assert db.query(User).filter(User.email == "demo@serpscope.local").count() == 1
    assert db.query(Membership).count() == 1
