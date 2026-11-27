"""Explicit logout revokes a bearer token without storing the raw token."""
from __future__ import annotations

from app.core.security import _REVOKED, _token_digest


def test_logout_revokes_only_the_presented_token(client, auth_headers):
    token = auth_headers["Authorization"].split(" ", 1)[1]
    assert client.get("/api/v1/auth/me", headers=auth_headers).status_code == 200

    response = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["detail"] == "Token revoked"
    assert token not in _REVOKED
    assert _token_digest(token) in _REVOKED

    denied = client.get("/api/v1/auth/me", headers=auth_headers)
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Token has been revoked"

    fresh = client.post("/api/v1/auth/login", json={
        "email": "demo@serpscope.local", "password": "demo1234",
    })
    assert fresh.status_code == 200
    headers = {"Authorization": "Bearer " + fresh.json()["access_token"]}
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 200
    assert client.get("/api/health").status_code == 200
