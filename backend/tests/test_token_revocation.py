"""Logout revokes a bearer token in the shared database, never storing the token."""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from app.core.security import token_digest
from app.db.session import SessionLocal
from app.models.auth import RevokedToken
from app.models.projects import Job
from app.services.token_revocation import is_token_revoked


def test_logout_revokes_only_the_presented_token(client, auth_headers, db):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200

    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["detail"] == "Token revoked"

    record = db.query(RevokedToken).filter(
        RevokedToken.token_digest == token_digest(token)
    ).one()
    assert token not in record.token_digest
    assert len(record.token_digest) == 64
    assert record.expires_at > 0

    denied = client.get("/api/v1/auth/me", headers=auth_headers)
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Token has been revoked"

    fresh = client.post("/api/v1/auth/login", json={
        "email": "demo@serpscope.local", "password": "demo1234",
    })
    assert fresh.status_code == 200
    new_token = fresh.json()["access_token"]
    assert new_token != token
    headers = {"Authorization": "Bearer " + new_token}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/health").status_code == 200

    # A second live session is invalidated by the account-wide control too.
    second = client.post("/api/v1/auth/login", json={
        "email": "demo@serpscope.local", "password": "demo1234",
    })
    second_headers = {"Authorization": "Bearer " + second.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=second_headers).status_code == 200

    all_out = client.post("/api/v1/auth/logout-all", headers=headers)
    assert all_out.status_code == 200, all_out.text
    assert all_out.json()["detail"] == "All sessions signed out"
    for stale in (headers, second_headers):
        denied = client.get("/api/v1/auth/me", headers=stale)
        assert denied.status_code == 401
        assert denied.json()["detail"] == "Token has been superseded"

    after = client.post("/api/v1/auth/login", json={
        "email": "demo@serpscope.local", "password": "demo1234",
    })
    assert after.status_code == 200
    assert client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer " + after.json()["access_token"]}
    ).status_code == 200


def test_revocation_is_shared_across_sessions_and_rejects_the_job_websocket(
    client, auth_headers, demo_project, db
):
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    job = Job(name="Revoked WS test", job_type="test", status="succeeded",
              project_id=demo_project["project_id"])
    db.add(job)
    db.commit()

    assert client.post("/api/v1/auth/logout", headers=auth_headers).status_code == 200

    with SessionLocal() as other_session:
        stored = other_session.query(RevokedToken).filter(
            RevokedToken.token_digest == token_digest(token)
        ).count()
        assert stored == 1
        assert is_token_revoked(other_session, token) is True

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(f"/api/v1/jobs/ws/{job.id}?token={token}") as socket:
            socket.receive_json()
    assert caught.value.code == 4401
