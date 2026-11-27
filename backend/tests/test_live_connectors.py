"""Dormant live connectors never fabricate data or bypass the honesty contract."""
from __future__ import annotations

import json

import pytest

from app.core.config import settings
from app.core.crypto import encrypt
from app.models.operations import Integration, SuppliedMetric
from app.models.projects import Project
from app.services import vendor_connectors
from app.services.supplied_metrics import supplied_signals


def _integration(db, project_id: int, organization_id: int, provider: str, config: dict) -> Integration:
    item = Integration(
        project_id=project_id,
        organization_id=organization_id,
        provider=provider,
        display_name=provider,
        mode="oauth_api",
        status="configured",
        credentials_encrypted=encrypt(json.dumps({"refresh_token": "test-refresh-token"})),
        config=config,
    )
    db.add(item)
    db.commit()
    return item


def test_connector_settings_default_off_and_can_be_read_from_environment(monkeypatch):
    defaults = settings.__class__()
    assert defaults.live_connectors_enabled is False
    assert defaults.gsc_client_id == ""
    assert defaults.ga4_client_id == ""
    assert defaults.llm_api_key == ""

    with monkeypatch.context() as env:
        env.setenv("LIVE_CONNECTORS_ENABLED", "true")
        env.setenv("GSC_CLIENT_ID", "env-client-id")
        env.setenv("LLM_API_KEY", "env-llm-key")
        configured = settings.__class__()
        assert configured.live_connectors_enabled is True
        assert configured.gsc_client_id == "env-client-id"
        assert configured.llm_api_key == "env-llm-key"


def test_connectors_are_dormant_until_explicitly_opted_in(db, demo_project, client, auth_headers):
    assert all(ready is False for ready in vendor_connectors.connector_readiness().values())

    response = client.get("/api/v1/integrations/connectors", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert all(item["ready"] is False for item in response.json()["items"])

    item = _integration(
        db, demo_project["project_id"], demo_project["organization_id"],
        "google_search_console", {"site_url": "https://example.com/"},
    )
    blocked = client.post(f"/api/v1/integrations/{item.id}/sync", headers=auth_headers)
    assert blocked.status_code == 503
    assert "disabled" in blocked.json()["detail"]
    assert db.query(SuppliedMetric).filter(SuppliedMetric.source == "gsc_live").count() == 0


def test_gsc_sync_stores_verbatim_rows_and_is_idempotent(
    db, demo_project, client, auth_headers, monkeypatch
):
    project_id = demo_project["project_id"]
    monkeypatch.setattr(settings, "live_connectors_enabled", True)
    monkeypatch.setattr(settings, "gsc_client_id", "client-id")
    monkeypatch.setattr(settings, "gsc_client_secret", "client-secret")
    monkeypatch.setattr(settings, "gsc_redirect_uri", "https://example.com/oauth")
    urls: list[str] = []

    def fake_post_json(url, *, data=None, payload=None, headers=None):
        urls.append(url)
        if url == vendor_connectors.TOKEN_ENDPOINT:
            return {"access_token": "test-access-token"}
        if "searchAnalytics/query" in url:
            return {"rows": [{
                "keys": ["2026-11-01", "seo audit course", "https://example.com/audit/"],
                "clicks": 12, "impressions": 400, "ctr": 0.03, "position": 8.4,
            }]}
        raise AssertionError(f"Unexpected provider URL: {url}")

    monkeypatch.setattr(vendor_connectors, "_post_json", fake_post_json)
    item = _integration(
        db, project_id, demo_project["organization_id"], "google_search_console",
        {"site_url": "https://example.com/", "start_date": "2026-11-01",
         "end_date": "2026-11-01", "row_limit": 10},
    )

    first = client.post(f"/api/v1/integrations/{item.id}/sync", headers=auth_headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["rows_fetched"] == 1
    assert body["rows_stored"] == 1
    assert body["data_kind"] == "api_live:gsc"
    assert "test-refresh-token" not in str(body)
    assert any("oauth2.googleapis.com" in url for url in urls)
    assert any("www.googleapis.com" in url for url in urls)

    db.expire_all()
    rows = db.query(SuppliedMetric).filter(SuppliedMetric.source == "gsc_live").all()
    assert len(rows) == 1
    assert rows[0].metrics["query"] == "seo audit course"
    assert rows[0].metrics["clicks"] == "12"
    assert rows[0].meta_info["import_convention"] == "verbatim_live_api"
    assert rows[0].meta_info["generated"] is False
    assert rows[0].meta_info["live_connector"] == "google_search_console"

    status = supplied_signals(db, project_id)
    assert status["gsc"]["live_rows"] == 1
    assert status["gsc"]["status"] == "api_live"
    assert "gsc_live" in status["gsc"]["sources"]
    assert status["rank"]["status"] == "not_supplied"

    explanation = client.get(
        f"/api/v1/integrations/supplied-signals?project_id={project_id}",
        headers=auth_headers,
    ).json()
    assert "api_live" in explanation["status_explanations"]
    assert "No provider API is called" in explanation["note"]

    second = client.post(f"/api/v1/integrations/{item.id}/sync", headers=auth_headers)
    assert second.status_code == 200, second.text
    assert second.json()["rows_stored"] == 0
    assert db.query(SuppliedMetric).filter(SuppliedMetric.source == "gsc_live").count() == 1
    assert db.get(Integration, item.id).status == "connected"
    assert db.get(Integration, item.id).last_sync_at


def test_ga4_sync_requires_valid_property_and_stores_reported_values(
    db, demo_project, client, auth_headers, monkeypatch
):
    monkeypatch.setattr(settings, "live_connectors_enabled", True)
    monkeypatch.setattr(settings, "ga4_client_id", "ga4-client")
    monkeypatch.setattr(settings, "ga4_client_secret", "ga4-secret")
    monkeypatch.setattr(settings, "ga4_redirect_uri", "https://example.com/oauth")

    def fake_post_json(url, *, data=None, payload=None, headers=None):
        if url == vendor_connectors.TOKEN_ENDPOINT:
            return {"access_token": "ga4-access-token"}
        if "/runReport" in url:
            return {"rows": [{
                "dimensionValues": [{"value": "2026-11-01"}, {"value": "/audit/"}],
                "metricValues": [{"value": "42"}, {"value": "2"}, {"value": "310.50"}],
            }]}
        raise AssertionError(f"Unexpected provider URL: {url}")

    monkeypatch.setattr(vendor_connectors, "_post_json", fake_post_json)
    bad = _integration(
        db, demo_project["project_id"], demo_project["organization_id"],
        "google_analytics_4", {"property_id": "javascript:alert(1)"},
    )
    rejected = client.post(f"/api/v1/integrations/{bad.id}/sync", headers=auth_headers)
    assert rejected.status_code == 503
    assert "property_id" in rejected.json()["detail"]

    item = _integration(
        db, demo_project["project_id"], demo_project["organization_id"],
        "google_analytics_4", {"property_id": "123456789", "start_date": "2026-11-01",
                               "end_date": "2026-11-02"},
    )
    response = client.post(f"/api/v1/integrations/{item.id}/sync", headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data_kind"] == "api_live:ga4"
    db.expire_all()
    row = db.query(SuppliedMetric).filter(SuppliedMetric.source == "ga4_live").one()
    assert row.metrics["sessions"] == "42"
    assert row.metrics["totalRevenue"] == "310.50"
    assert supplied_signals(db, demo_project["project_id"])["ga4"]["status"] == "api_live"


def test_llm_connector_is_gated_and_generated_text_is_never_evidence(monkeypatch):
    with pytest.raises(vendor_connectors.ConnectorUnavailable):
        vendor_connectors.assistive_llm_text("draft a readiness note")

    monkeypatch.setattr(settings, "live_connectors_enabled", True)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(
        vendor_connectors, "_post_json",
        lambda url, **kwargs: {"choices": [{"message": {"content": "Assistive draft"}}]},
    )
    result = vendor_connectors.assistive_llm_text("draft a readiness note")
    assert result == {
        "text": "Assistive draft",
        "generated": True,
        "note": (
            "Model-generated draft. Not a verified observation, public-evidence "
            "finding or measured metric."
        ),
    }


def test_live_rows_stay_out_of_public_case_studies(
    db, demo_project, client, auth_headers, monkeypatch
):
    source = db.get(Project, demo_project["project_id"])
    published = Project(
        organization_id=source.organization_id,
        name="Published live-sync project", domain="published.example",
        is_demo=False, settings={"public_audit": True},
    )
    db.add(published)
    db.commit()

    monkeypatch.setattr(settings, "live_connectors_enabled", True)
    monkeypatch.setattr(settings, "gsc_client_id", "client-id")
    monkeypatch.setattr(settings, "gsc_client_secret", "client-secret")
    monkeypatch.setattr(settings, "gsc_redirect_uri", "https://example.com/oauth")
    monkeypatch.setattr(vendor_connectors, "_access_token", lambda *args: "test-token")
    monkeypatch.setattr(
        vendor_connectors, "_post_json",
        lambda url, **kwargs: {"rows": [{
            "keys": ["2026-11-01", "private query", "https://example.com/private"],
            "clicks": 9, "impressions": 100, "ctr": 0.09, "position": 4,
        }]},
    )
    item = _integration(
        db, published.id, published.organization_id, "google_search_console",
        {"site_url": "https://example.com/", "start_date": "2026-11-01",
         "end_date": "2026-11-01"},
    )
    assert client.post(f"/api/v1/integrations/{item.id}/sync", headers=auth_headers).status_code == 200

    private = client.get(
        f"/api/v1/audits/projects/{published.id}/public-audit", headers=auth_headers
    ).json()
    assert private["supplied_data"]["gsc"]["supplied"] is True
    public = client.get(f"/api/v1/public/case-studies/{published.id}").json()
    assert public["meta"]["publication_scope"] == "public_evidence_only"
    assert public["supplied_data"]["gsc"]["supplied"] is False
    assert public["supplied_data"]["gsc"]["rows"] == 0
    assert "private query" not in str(public)
