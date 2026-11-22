"""Background job handlers for keyword workflows."""
from __future__ import annotations

from app.services import keywords
from app.services.jobs import progress, register


@register("cluster_keywords")
def run_cluster(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        config = payload.get("config") or {}
        method = config.pop("method", "normalized")
        progress(job_id, 20, 100, "Clustering keywords")
        result = keywords.cluster_keywords(db, project_id, method, config)
        db.commit()
        progress(job_id, 100, 100, "Clustering complete")
        return result
    finally:
        db.close()


@register("map_keywords")
def run_map(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        progress(job_id, 20, 100, "Mapping clusters to URLs")
        result = keywords.map_clusters_to_urls(db, project_id, payload.get("config") or {})
        db.commit()
        progress(job_id, 100, 100, "Mapping complete")
        return result
    finally:
        db.close()


@register("bulk_keyword_workflow")
def run_bulk(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    try:
        config = payload.get("config") or {}
        progress(job_id, 10, 100, "Classifying keyword intent")
        keywords.ensure_intents(db, project_id, config.get("brand_terms", []))
        progress(job_id, 35, 100, "Clustering keywords")
        cluster_result = keywords.cluster_keywords(db, project_id, config.get("method", "normalized"), config)
        progress(job_id, 70, 100, "Mapping clusters to URLs")
        mapping_result = keywords.map_clusters_to_urls(db, project_id, config)
        db.commit()
        progress(job_id, 95, 100, "Analysing cannibalisation")
        progress(job_id, 100, 100, "Complete")
        return {
            "workflow": "1,000-page keyword mapping",
            "clustering": cluster_result,
            "mapping": mapping_result,
            "note": "Automated processing of imported data only; fresh third-party keyword research requires provider credentials.",
        }
    finally:
        db.close()


@register("refresh_priorities")
def run_refresh(db_session_factory, job_id, payload, project_id, organization_id):
    from app.services import issues, orphans

    db = db_session_factory()
    try:
        progress(job_id, 25, 100, "Refreshing orphan scores")
        orphan_result = orphans.detect_orphans(db, project_id, payload.get("config") or {})
        progress(job_id, 65, 100, "Refreshing technical issues")
        issue_result = issues.detect_issues(db, project_id)
        db.commit()
        progress(job_id, 100, 100, "Complete")
        return {"orphans": orphan_result, "issues": issue_result}
    finally:
        db.close()
