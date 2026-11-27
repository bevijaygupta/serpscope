"""Tests for the honest-foundation features: history, imports, scheduling and views."""
from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.config import Settings
from app.models.operations import CaseStudyView, Report, Workflow
from app.models.projects import Job, Project
from app.services import workflows
from app.services.public_audit import HEALTH_SCORE_NOTE, health_score, sanitize_public_audit_config


def _real_project(db, demo_project, domain: str = "honest.example") -> Project:
    source = db.get(Project, demo_project["project_id"])
    project = Project(
        organization_id=source.organization_id,
        name=f"Honest project {domain}",
        domain=domain,
        is_demo=False,
        settings={"public_audit": True},
    )
    db.add(project)
    db.commit()
    return project


def _audit_content(domain: str, generated_at: str, high: int, medium: int) -> dict:
    findings = []
    if high:
        findings.append({
            "id": "missing_title", "title": "Missing title tags", "severity": "High",
            "category": "content", "affected_count": high, "observation": "Observed.",
            "recommended_action": "Fix.", "source": ["rule"], "confidence": "derived", "limitation": "",
        })
    if medium:
        findings.append({
            "id": "redirects", "title": "Redirect chains", "severity": "Medium",
            "category": "indexability", "affected_count": medium, "observation": "Observed.",
            "recommended_action": "Fix.", "source": ["rule"], "confidence": "derived", "limitation": "",
        })
    return {
        "meta": {"domain": domain, "generated_at": generated_at, "crawl_id": 1},
        "coverage": {"fetched_urls": 10, "discovered_urls": 20, "sitemap_entries": 5},
        "findings": findings,
        "roadmap": [], "sections": [], "missing_data": [],
    }


def test_health_score_requires_minimum_public_evidence():
    finding = {
        "id": "missing_title", "title": "Missing title tags", "severity": "High",
        "affected_count": 1,
    }
    assert health_score({"coverage": {"fetched_urls": 1}, "findings": [finding]}) is None
    assert health_score({"coverage": {"fetched_urls": 9}, "findings": [finding]}) is None
    assert health_score({"coverage": {"fetched_urls": 10}, "findings": [finding]}) == 90.0
    assert health_score({"coverage": {"fetched_urls": 10}, "findings": []}) is None
    assert "fewer than 10 fetched URLs" in HEALTH_SCORE_NOTE


def test_audit_history_and_compare_use_stored_snapshots(client, db, auth_headers, demo_project):
    project = _real_project(db, demo_project)
    first = Report(
        project_id=project.id, title="First audit", report_type="public_audit",
        content=_audit_content(project.domain, "2026-11-01T00:00:00Z", high=5, medium=2),
        missing_data=[], generated_by="public-audit",
    )
    db.add(first)
    db.commit()
    second = Report(
        project_id=project.id, title="Second audit", report_type="public_audit",
        content=_audit_content(project.domain, "2026-11-24T00:00:00Z", high=2, medium=0),
        missing_data=[], generated_by="public-audit",
    )
    db.add(second)
    db.commit()

    history = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit/history", headers=auth_headers
    )
    assert history.status_code == 200, history.text
    body = history.json()
    assert body["count"] == 2
    assert [item["report_id"] for item in body["items"]] == [first.id, second.id]
    assert body["items"][0]["health_score"] == health_score(first.content)
    assert body["items"][1]["health_score"] == health_score(second.content)
    assert HEALTH_SCORE_NOTE == body["metric_note"]
    assert "not Ubersuggest" in HEALTH_SCORE_NOTE

    compare = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit/compare", headers=auth_headers
    )
    assert compare.status_code == 200, compare.text
    result = compare.json()
    assert result["comparison_available"] is True
    assert result["base"]["report_id"] == first.id
    assert result["target"]["report_id"] == second.id
    assert result["deltas"]["findings"] == -1
    assert result["deltas"]["health_score"] > 0
    assert [row["id"] for row in result["resolved_findings"]] == ["redirects"]
    assert result["new_findings"] == []
    changed = {row["id"]: row["delta"] for row in result["changed_findings"]}
    assert changed["missing_title"] == -3

    explicit = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit/compare"
        f"?base={second.id}&target={first.id}", headers=auth_headers
    )
    assert explicit.status_code == 400


def test_compare_without_two_reports_is_honest(client, db, auth_headers, demo_project):
    project = _real_project(db, demo_project, domain="single.example")
    response = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit/compare", headers=auth_headers
    )
    assert response.status_code == 404

    report = Report(
        project_id=project.id, title="Only audit", report_type="public_audit",
        content=_audit_content(project.domain, "2026-11-24T00:00:00Z", high=1, medium=0),
        missing_data=[], generated_by="public-audit",
    )
    db.add(report)
    db.commit()
    body = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit/compare", headers=auth_headers
    ).json()
    assert body["comparison_available"] is False
    assert "Run another public audit" in body["note"]


def test_ai_observation_import_keeps_provenance_and_not_sampled_semantics(
    client, db, auth_headers, demo_project
):
    project = _real_project(db, demo_project, domain="ai.example")
    url = f"/api/v1/ai-search/observations/import?project_id={project.id}"
    response = client.post(url, headers=auth_headers, json={
        "source": "licensed-export",
        "data_kind": "observed",
        "rows": [
            {
                "question": "best enterprise SEO tool", "answer_engine": "ChatGPT",
                "observed_at": "2026-11-24T00:00:00Z", "brand_mentioned": "yes",
                "competitor_mentioned": "Semrush;Ahrefs", "cited_url": "https://ai.example/services/",
                "answer_url": "https://chatgpt.com/share/verified", "locale": "en-SG",
                "source": "licensed-export", "data_kind": "observed", "notes": "Screenshot reviewed",
            },
            {
                "question": "demo question", "answer_engine": "Claude",
                "source": "demo-generator", "data_kind": "synthetic", "brand_mentioned": "no",
            },
            {"question": "missing engine"},
        ],
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["accepted"], body["rejected"]) == (2, 1)
    assert "question' and 'answer_engine' are required" in body["errors"][0]
    assert body["visibility_status"] == "observations_recorded"
    assert body["verified_observations"] == 1

    rows = client.get(
        f"/api/v1/ai-search/observations?project_id={project.id}", headers=auth_headers
    ).json()["items"]
    verified = next(row for row in rows if row["question"] == "best enterprise SEO tool")
    assert verified["answer_url"] == "https://chatgpt.com/share/verified"
    assert verified["locale"] == "en-SG"
    assert verified["competitor_mentioned"] == ["Semrush", "Ahrefs"]
    assert verified["source"] == "licensed-export"
    assert verified["data_kind"] == "observed"
    synthetic = next(row for row in rows if row["question"] == "demo question")
    assert synthetic["brand_mentioned"] is False

    audit = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit", headers=auth_headers
    ).json()
    assert audit["ai_visibility"]["status"] == "observations_recorded"
    assert audit["ai_visibility"]["unverified_row_count"] == 1
    assert "excluded from every claim" in audit["ai_visibility"]["verification_note"]

    public = client.get(f"/api/v1/public/case-studies/{project.id}").json()
    assert public["ai_visibility"]["status"] == "not_sampled"

    csv_response = client.post(url, headers=auth_headers, json={
        "csv": "question,answer_engine,source,data_kind\ncsv question,Perplexity,licensed-export,observed\n",
    })
    assert csv_response.status_code == 201, csv_response.text
    assert csv_response.json()["accepted"] == 1


def test_synthetic_only_import_stays_not_sampled(client, db, auth_headers, demo_project):
    project = _real_project(db, demo_project, domain="synthetic-ai.example")
    response = client.post(
        f"/api/v1/ai-search/observations/import?project_id={project.id}",
        headers=auth_headers,
        json={"rows": [{"question": "demo", "answer_engine": "ChatGPT",
                        "source": "demo", "data_kind": "synthetic", "brand_mentioned": True}]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["visibility_status"] == "not_sampled"
    audit = client.get(
        f"/api/v1/audits/projects/{project.id}/public-audit", headers=auth_headers
    ).json()
    assert audit["ai_visibility"]["status"] == "not_sampled"
    assert audit["ai_visibility"]["observation_count"] == 0


def test_scheduled_public_audit_step_queues_a_job(client, db, auth_headers, demo_project):
    project = _real_project(db, demo_project, domain="schedule.example")
    library = client.get("/api/v1/workflows/step-library", headers=auth_headers).json()
    assert any(item["type"] == "public_audit" for item in library["items"])
    assert "no vendor API" in library["note"]

    workflow = Workflow(
        project_id=project.id, name="Nightly public audit", trigger="scheduled",
        schedule="daily", enabled=True,
        steps=[{"type": "public_audit", "config": {"start_url": "https://schedule.example/"}}],
    )
    db.add(workflow)
    db.commit()
    assert workflow.id in [row.id for row in workflows.due_workflows(db)]

    result = workflows.execute_workflow(db, workflow.id)
    assert result["status"] == "succeeded", result
    queued = result["steps"][0]["result"]
    assert queued["status"] == "queued"
    job = db.get(Job, queued["job_id"])
    assert job.job_type == "public_audit"
    assert job.project_id == project.id
    assert job.payload["start_url"] == "https://schedule.example/"
    assert workflow.id not in [row.id for row in workflows.due_workflows(db)]


def test_public_audit_config_cannot_override_provenance_or_ssrf_guards(
    client, db, auth_headers, demo_project
):
    hostile_config = {
        "allow_private": True, "auth_headers": {"Authorization": "Bearer secret"},
        "mode": "synthetic", "javascript_rendering": True, "follow_external": True,
        "respect_robots": False, "sitemap_discovery": False,
        "max_urls": 100000, "max_depth": 50, "concurrency": 99,
        "crawl_delay": 0, "timeout": 999,
    }
    config = sanitize_public_audit_config({"config": hostile_config})
    assert config["allow_private"] is False
    assert config["auth_headers"] == {}
    assert config["mode"] == "live"
    assert config["javascript_rendering"] is False
    assert config["follow_external"] is False
    assert config["respect_robots"] is True
    assert config["sitemap_discovery"] is True
    assert config["max_urls"] <= 500
    assert config["max_depth"] <= 5
    assert config["concurrency"] <= 4
    assert config["crawl_delay"] >= 1.0
    assert config["timeout"] <= 30

    project = _real_project(db, demo_project, domain="hardening.example")
    response = client.post(
        f"/api/v1/audits/projects/{project.id}/public-audit/start",
        headers=auth_headers,
        json={"start_url": "https://hardening.example/", "config": hostile_config},
    )
    assert response.status_code == 202, response.text
    job = db.get(Job, response.json()["job_id"])
    queued_config = job.payload["config"]
    assert queued_config["allow_private"] is False
    assert queued_config["auth_headers"] == {}
    assert queued_config["mode"] == "live"
    assert queued_config["max_urls"] == config["max_urls"]


def test_production_configuration_fails_fast_on_unsafe_values():
    safe = {
        "environment": "production",
        "secret_key": "unique-deployment-secret-with-enough-entropy-2026",
        "database_url": "postgresql+psycopg2://user:password@db.example.com/serpscope",
        "cors_origins": "https://serpscopelive.vercel.app",
    }
    assert Settings(**safe).environment == "production"
    for override in (
        {"secret_key": "dev-only-secret-change-before-deployment"},
        {"cors_origins": "http://localhost:5173"},
        {"cors_origins": "*"},
        {"database_url": "sqlite:///./data/serpscope.db"},
    ):
        with pytest.raises(ValidationError):
            Settings(**{**safe, **override})


def test_case_study_analytics_are_anonymous_and_public_only(client, db, auth_headers, demo_project):
    project = _real_project(db, demo_project, domain="views.example")
    report = Report(
        project_id=project.id, title="Views audit", report_type="public_audit",
        content=_audit_content(project.domain, "2026-11-24T00:00:00Z", high=1, medium=0),
        missing_data=[], generated_by="public-audit",
    )
    db.add(report)
    db.commit()
    assert "ip_address" not in CaseStudyView.__table__.columns

    for _ in range(2):
        recorded = client.post(f"/api/v1/public/case-studies/{project.id}/view", json={"source": "case_study_detail"})
        assert recorded.status_code == 201, recorded.text
        assert recorded.json()["recorded"] is True
    rows = db.scalars(select(CaseStudyView).where(CaseStudyView.project_id == project.id)).all()
    assert len(rows) == 2
    assert all(row.report_id == report.id for row in rows)

    analytics = client.get(
        f"/api/v1/audits/projects/{project.id}/case-study-analytics", headers=auth_headers
    ).json()
    assert analytics["published"] is True
    assert analytics["view_count"] == 2
    assert "No IP address, cookie, referrer or user identity is stored" in analytics["note"]

    public = client.get(f"/api/v1/public/case-studies/{project.id}").json()
    assert public["analytics"]["view_count"] == 2
    index = client.get("/api/v1/public/case-studies").json()
    assert next(row for row in index["items"] if row["project_id"] == project.id)["view_count"] == 2

    demo = demo_project["project_id"]
    assert client.post(f"/api/v1/public/case-studies/{demo}/view").status_code == 404
    assert client.get(
        f"/api/v1/audits/projects/{demo}/case-study-analytics", headers=auth_headers
    ).json()["published"] is False


def test_vendor_signal_status_explains_not_supplied(client, auth_headers, demo_project):
    body = client.get(
        f"/api/v1/integrations/supplied-signals?project_id={demo_project['project_id']}",
        headers=auth_headers,
    ).json()
    assert "No provider API is called" in body["note"]
    assert "No real export was supplied" in body["status_explanations"]["not_supplied"]
    assert "not a live API connection" in body["status_explanations"]["supplied"]


def test_cancelled_public_audit_never_persists_or_publishes(monkeypatch, db, demo_project):
    from app.db.session import SessionLocal
    from app.services import public_audit_jobs

    source = db.get(Project, demo_project["project_id"])
    project = Project(
        organization_id=source.organization_id,
        name="Cancelled audit project",
        domain="honest.example",
        is_demo=False,
        settings={},
    )
    db.add(project)
    db.commit()

    class FakeEngine:
        def __init__(self, *args, **kwargs):
            pass

        def run(self):
            return {"discovered": 1, "crawled": 0, "failed": 0, "excluded": 0}

    monkeypatch.setattr(public_audit_jobs, "CrawlEngine", FakeEngine)
    monkeypatch.setattr(public_audit_jobs, "is_cancelled", lambda job_id: True)
    result = public_audit_jobs.run_public_audit_job(
        SessionLocal, 987654, {"start_url": "https://honest.example/"},
        project.id, project.organization_id,
    )
    assert result["cancelled"] is True
    assert result["case_study_published"] is False
    count = db.scalar(select(func.count()).select_from(Report).where(Report.project_id == project.id))
    assert count == 0
    db.refresh(project)
    assert not (project.settings or {}).get("public_audit")
