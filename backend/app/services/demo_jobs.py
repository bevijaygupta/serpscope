"""Background handlers for demo data generation and reset."""
from __future__ import annotations

from sqlalchemy import text

from app.services import demo
from app.services.jobs import progress, register

DEMO_TABLES = [
    "url_records", "crawl_observations", "crawls", "link_edges", "sitemap_entries",
    "issues", "issue_urls", "orphan_records", "keywords", "keyword_clusters",
    "keyword_mappings", "content_analyses", "content_briefs", "link_suggestions",
    "analytics_records", "reports", "forecasts", "workflows", "workflow_runs",
    "data_sources", "tasks", "meeting_notes", "project_members",
    "competitors", "keyword_gaps", "international_plans", "hreflang_records",
    "locations", "products", "migration_mappings", "migration_projects",
    "ai_visibility_records", "ai_readiness_items", "integrations", "jobs",
]


@register("generate_demo")
def generate_demo_job(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        progress(job_id, 10, 100, "Generating synthetic inventory")
        result = demo.generate_demo(
            db, int(payload.get("size", 1000)), int(payload.get("keyword_count", 1000)),
            label=payload.get("label"), include_scenarios=bool(payload.get("include_scenarios", True)),
        )
        progress(job_id, 100, 100, "Demo dataset ready")
        return result
    finally:
        db.close()


@register("reset_demo")
def reset_demo_job(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        project_ids = [r[0] for r in db.execute(text("SELECT id FROM projects WHERE is_demo IS TRUE")).all()]
        progress(job_id, 10, 100, "Removing demo projects")
        for pid in project_ids:
            for table in DEMO_TABLES:
                db.execute(text(f"DELETE FROM {table} WHERE project_id=:p"), {"p": pid})
            db.execute(text("DELETE FROM projects WHERE id=:p"), {"p": pid})
        db.execute(text("DELETE FROM organizations WHERE is_demo IS TRUE AND slug='demo-organisation'"))
        db.execute(text("DELETE FROM jobs WHERE job_type IN ('generate_demo','reset_demo')"))
        db.commit()
        if payload.get("regenerate"):
            result = demo.generate_demo(
                db, int(payload.get("size", 1000)), int(payload.get("keyword_count", 1000)),
                label=payload.get("label"),
            )
            return {"reset": True, "regenerated": result}
        return {"reset": True, "deleted_projects": project_ids}
    finally:
        db.close()
