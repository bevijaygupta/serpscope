"""Background job handlers for analysis and reporting."""
from __future__ import annotations

from app.services import content, domains, issues, links, orphans, reports
from app.services.jobs import progress, register

HANDLER_MAP = {
    "detect_issues": lambda db, p, c: issues.detect_issues(db, p),
    "detect_orphans": lambda db, p, c: orphans.detect_orphans(db, p, c),
    "content_analysis": lambda db, p, c: content.analyse_content(db, p),
    "generate_briefs": lambda db, p, c: content.generate_briefs(db, p),
    "link_suggestions": lambda db, p, c: links.analyse_graph(db, p),
    "generate_report": lambda db, p, c: reports.generate_weekly_report(db, p, **(c or {})),
    "competitor_analysis": lambda db, p, c: domains.competitor_analysis(db, p, c),
    "international_plan": lambda db, p, c: domains.build_international_plan(db, p, c),
    "local_audit": lambda db, p, c: domains.local_audit(db, p),
    "ecommerce_audit": lambda db, p, c: domains.ecommerce_audit(db, p),
    "migration_validate": lambda db, p, c: domains.migration_validate(db, p, c),
    "ai_readiness": lambda db, p, c: domains.ai_readiness(db, p),
}


def _make_handler(job_type: str, label: str):
    @register(job_type)
    def handler(db_session_factory, job_id: int, payload: dict, project_id: int | None, organization_id: int | None):
        db = db_session_factory()
        try:
            progress(job_id, 10, 100, "Starting " + label)
            result = HANDLER_MAP[job_type](db, project_id, payload.get("config") or {})
            # Some services leave changes pending in this session; commit before
            # another session updates job progress, otherwise SQLite sees a lock.
            db.commit()
            progress(job_id, 100, 100, "Completed " + label)
            return result
        finally:
            db.close()

    handler.__name__ = f"run_{job_type}"
    return handler


for _job_type in HANDLER_MAP:
    _make_handler(_job_type, _job_type.replace("_", " "))
