from __future__ import annotations

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.analysis import Issue, IssueUrl
from app.models.inventory import UrlRecord
from app.models.projects import Job
from app.services.demo_jobs import reset_demo_job
from app.services.issues import detect_issues, high_value_404s


def test_demo_generation_creates_labelled_data_and_planted_issues(demo_project, db):
    assert demo_project["size"] == 200
    assert demo_project["urls"] == 200
    assert demo_project["keywords"] == 150
    assert demo_project["planted_issues"]["high_value_404"] >= 1
    assert demo_project["planted_issues"]["ordinary_404"] >= 1
    records = db.scalars(select(UrlRecord).where(UrlRecord.project_id == demo_project["project_id"])).all()
    assert len(records) == 200
    assert {r.data_kind for r in records} == {"synthetic"}
    assert any(r.http_status == 404 and r.revenue > 0 for r in records)


def test_detect_issues_creates_evidence_and_explanations(demo_project, db):
    result = detect_issues(db, demo_project["project_id"])
    assert result["records_scanned"] == 200
    assert result["total_issue_groups"] > 0
    assert "http_404" in result["issues"]
    assert "http_5xx" in result["issues"]
    issues = db.scalars(select(Issue).where(Issue.project_id == demo_project["project_id"])).all()
    assert issues
    assert all(issue.evidence and issue.priority_explanation for issue in issues)
    assert all(issue.priority in {"P0", "P1", "P2", "P3", "Review"} for issue in issues)
    linked = db.scalar(select(func.count()).select_from(IssueUrl).where(
        IssueUrl.project_id == demo_project["project_id"]))
    assert linked > 0


def test_reset_demo_preserves_the_running_reset_job(db):
    job = Job(name="Reset demo data", job_type="reset_demo", status="running")
    db.add(job)
    db.commit()

    reset_demo_job(SessionLocal, job.id, {}, None, None)

    db.expire_all()
    assert db.get(Job, job.id) is not None


def test_high_value_404_workflow_uses_supplied_business_evidence(demo_project, db):
    detect_issues(db, demo_project["project_id"])
    rows = high_value_404s(db, demo_project["project_id"])
    assert len(rows) >= demo_project["planted_issues"]["high_value_404"]
    revenues = [row["revenue"] for row in rows]
    assert revenues == sorted(revenues, reverse=True)
    first = rows[0]
    assert first["url"].startswith("https://demo.example.com/")
    assert first["revenue"] > 0
    assert first["priority"] in {"P0", "P1", "P2", "P3", "Review"}
    assert "Score" in first["explanation"]
    assert first["components"]["revenue_impact"] > 0
    assert "recommended_action" in first and first["recommended_action"]
