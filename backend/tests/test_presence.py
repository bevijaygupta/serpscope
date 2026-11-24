"""The live badge counts anonymous sessions, not analytics identities."""
from __future__ import annotations

import pytest

from app.api.v1 import presence


@pytest.fixture(autouse=True)
def clear_presence():
    with presence._lock:
        presence._sessions.clear()
    yield
    with presence._lock:
        presence._sessions.clear()


def test_presence_requires_a_valid_anonymous_token(client):
    response = client.post("/api/v1/presence/ping", json={"session_id": "short"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid anonymous session id"


def test_presence_counts_distinct_anonymous_sessions(client):
    first = client.post("/api/v1/presence/ping", json={"session_id": "a" * 32})
    assert first.status_code == 200, first.text
    assert first.json()["active"] == 1
    assert "No IP address" in first.json()["note"]

    second = client.post("/api/v1/presence/ping", json={"session_id": "b" * 32})
    assert second.json()["active"] == 2

    refreshed = client.post("/api/v1/presence/ping", json={"session_id": "a" * 32})
    assert refreshed.json()["active"] == 2

    count = client.get("/api/v1/presence/count")
    assert count.status_code == 200
    assert count.json()["active"] == 2
    assert count.json()["ttl_seconds"] == 60

    # The raw browser token is never stored, only its hash.
    assert all("a" * 32 != key for key in presence._sessions)
