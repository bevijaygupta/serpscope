"""One-click public-evidence audit job.

Runs a conservative crawl, rebuilds derived analyses, then persists a report
containing the audit, six-month roadmap, sources and missing-data statement.
"""
from __future__ import annotations

from app.core.timeutil import iso, utcnow
from app.core.url_utils import validate_target_url
from app.models.inventory import Crawl
from app.models.projects import Project
from app.services import competitor_discovery, content, domains, issues, links, orphans, public_audit
from app.services.crawler import DEFAULT_CONFIG, CrawlConfig, CrawlEngine
from app.services.jobs import is_cancelled, progress, register


def derived_result_counts(derived: dict) -> dict:
    """Job-result counts use one ``derived_`` prefix, never a doubled one."""
    return {
        (key if key.startswith("derived_") else f"derived_{key}"): value
        for key, value in derived.items()
        if key != "error"
    }


@register("public_audit")
def run_public_audit_job(db_session_factory, job_id: int, payload: dict, project_id: int | None, organization_id: int | None):
    if project_id is None:
        raise ValueError("Public audit requires a project")
    config = dict(DEFAULT_CONFIG)
    config.update({
        "start_url": (payload.get("start_url") or "").strip(),
        "max_urls": 250,
        "max_depth": 3,
        "concurrency": 2,
        "crawl_delay": 1.0,
        "timeout": 12,
        "respect_robots": True,
        "sitemap_discovery": True,
        "follow_external": False,
        "allow_private": False,
        "mode": "live",
    })
    config.update(payload.get("config") or {})
    if not config.get("start_url"):
        db = db_session_factory()
        try:
            project = db.get(Project, project_id)
            config["start_url"] = (project.domain if project else "").strip()
        finally:
            db.close()
    validate_target_url(config["start_url"], allow_private=bool(config.get("allow_private")))
    crawl_config = CrawlConfig.from_dict(config)

    db = db_session_factory()
    try:
        crawl = Crawl(
            project_id=project_id, job_id=job_id,
            name=payload.get("name") or f"Public audit · {crawl_config.start_url}",
            config=crawl_config.as_dict(), status="running", started_at=iso(utcnow()),
            data_kind=crawl_config.mode,
        )
        db.add(crawl)
        db.commit()
        crawl_id = crawl.id
    finally:
        db.close()

    engine_db = db_session_factory()
    try:
        progress(job_id, 5, 100, "Starting robots-aware public crawl")
        engine = CrawlEngine(
            db=engine_db, project_id=project_id, crawl_id=crawl_id, job_id=job_id,
            config=crawl_config,
            on_progress=lambda value, total, message: progress(job_id, 5 + int(value * 0.55), 100, message),
            cancelled=lambda: is_cancelled(job_id),
        )
        stats = engine.run()
    finally:
        engine_db.close()

    db = db_session_factory()
    try:
        crawl = db.get(Crawl, crawl_id)
        crawl.status = "cancelled" if is_cancelled(job_id) else "completed"
        crawl.discovered = stats["discovered"]
        crawl.crawled = stats["crawled"]
        crawl.failed = stats["failed"]
        crawl.excluded = stats["excluded"]
        crawl.summary = stats
        crawl.finished_at = iso(utcnow())
        db.commit()
        progress(job_id, 62, 100, "Rebuilding orphan and link graph")
        orphans.detect_orphans(db, project_id)
        links.analyse_graph(db, project_id)
        progress(job_id, 74, 100, "Deriving competitor and keyword evidence from observed links")
        try:
            derived = competitor_discovery.derive_public_evidence(db, project_id, crawl_id)
        except Exception as exc:  # pragma: no cover - defensive: audit must still finish
            derived = {
                "competitors": 0,
                "derived_keywords": 0,
                "keyword_gaps": 0,
                "derived_mappings": 0,
                "error": str(exc)[:500],
            }
        progress(job_id, 80, 100, "Running technical, content and AEO rules")
        issues.detect_issues(db, project_id)
        content.analyse_content(db, project_id)
        domains.ai_readiness(db, project_id)
        progress(job_id, 90, 100, "Assembling audit, roadmap and report")
        audit = public_audit.build_public_audit(db, project_id, crawl_id)
        report_id = public_audit.persist_report(db, project_id, audit)
        progress(job_id, 100, 100, "Public audit completed")
        return {
            "crawl_id": crawl_id,
            "report_id": report_id,
            "fetched_urls": stats.get("crawled", 0),
            "findings": len(audit["findings"]),
            "roadmap_months": len(audit["roadmap"]),
            **derived_result_counts(derived),
        }
    finally:
        db.close()
