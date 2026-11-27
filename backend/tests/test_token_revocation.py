"""Logout revokes a bearer token in the shared database, never storing the token."""
from __future__ import annotations

import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.crypto import decrypt, encrypt
from app.core.security import create_access_token, decode_access_token, token_digest
from app.db.session import SessionLocal
from app.models.auth import RevokedToken, User
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


@pytest.mark.parametrize("claims", [
    {"sub": "not-an-id"},
    {"exp": "tomorrow"},
    {"iat": "yesterday"},
    {"ver": "0"},
])
def test_malformed_signed_claims_are_rejected_as_401(client, claims):
    token = create_access_token("1", claims)
    response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 401


def test_optional_token_and_credential_keys_are_independent(monkeypatch):
    monkeypatch.setattr(settings, "token_signing_key", "a" * 32)
    monkeypatch.setattr(settings, "credential_encryption_key", "b" * 32)
    token = create_access_token("1")
    encrypted = encrypt("secret-value")
    assert decode_access_token(token) is not None
    assert decrypt(encrypted) == "secret-value"

    monkeypatch.setattr(settings, "token_signing_key", "c" * 32)
    assert decode_access_token(token) is None
    monkeypatch.setattr(settings, "credential_encryption_key", "d" * 32)
    with pytest.raises(Exception):
        decrypt(encrypted)


def test_job_websocket_closes_after_midstream_logout(
    client, auth_headers, demo_project, db, monkeypatch
):
    from app.api.v1 import jobs as jobs_router

    monkeypatch.setattr(jobs_router, "WS_AUTH_RECHECK_EVERY", 2)
    token = auth_headers["Authorization"].removeprefix("Bearer ")
    job = Job(name="Superseded WS test", job_type="test", status="running",
              progress=10, project_id=demo_project["project_id"])
    db.add(job)
    db.commit()

    with pytest.raises(WebSocketDisconnect) as caught:
        with client.websocket_connect(f"/api/v1/jobs/ws/{job.id}?token={token}") as socket:
            assert socket.receive_json()["status"] == "running"
            user = db.scalar(select(User).where(User.email == "demo@serpscope.local"))
            user.token_version += 1
            db.commit()
            for _ in range(8):
                socket.receive_json()
            pytest.fail("WebSocket stayed open after account-wide logout")
    assert caught.value.code == 4401
