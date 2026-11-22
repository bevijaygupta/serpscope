#!/usr/bin/env python3
"""Generate a fully populated, deterministic synthetic demo database.

Usage (from backend/):
    python scripts/seed_demo.py --size 1000 --reset

Every generated metric is labelled synthetic/simulated. The script also runs the
same analysis services used by the UI and records them as completed jobs so the
Demo Centre and Jobs screens are immediately useful in interviews.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# Set before importing app modules: app.core.config caches settings at import.
os.environ.setdefault("DATABASE_URL", "sqlite:///./data/demo.db")

from sqlalchemy import func, select  # noqa: E402

from app.db.session import SessionLocal, init_db  # noqa: E402
from app.models.auth import Organization  # noqa: E402
from app.models.enterprise import Competitor  # noqa: E402
from app.models.inventory import UrlRecord  # noqa: E402
from app.models.keywords import Keyword  # noqa: E402
from app.models.projects import MeetingNote, Project, Task  # noqa: E402
from app.services.demo import generate_demo  # noqa: E402
from app.services.demo_jobs import reset_demo_job  # noqa: E402
from app.services.forecast import build_forecast  # noqa: E402
from app.services.jobs import enqueue, run_job  # noqa: E402
from app.services.keywords import normalize_keyword  # noqa: E402

# Importing job modules registers their handlers with the shared queue.
from app.services import analysis_jobs, keyword_jobs  # noqa: E402,F401


def _count(db, model, project_id: int) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(
        model.project_id == project_id
    )) or 0)


def _run(db, job_type: str, label: str, project, config: dict | None = None) -> dict:
    # run_job() uses its own sessions; release any read transaction first.
    db.commit()
    job = enqueue(
        db, job_type, label, {"config": config or {}},
        project_id=project.id, organization_id=project.organization_id,
    )
    db.commit()
    result = run_job(job.id)
    db.commit()
    if result.get("error"):
        raise RuntimeError(f"{job_type} failed: {result['error']}")
    print(f"  [job {job.id}] {label}: ok")
    return result


def _seed_competitor_data(db, project) -> None:
    """Add explicitly synthetic competitor rows; no third-party data is scraped."""
    if db.scalar(select(func.count()).select_from(Competitor).where(
        Competitor.project_id == project.id
    )):
        return
    db.add_all([
        Competitor(project_id=project.id, domain="competitor-a.example",
                   name="Competitor A (synthetic)", notes="Synthetic import for rule testing"),
        Competitor(project_id=project.id, domain="competitor-b.example",
                   name="Competitor B (synthetic)", notes="Synthetic import for rule testing"),
    ])
    phrases = [
        ("vapt services singapore", 2400, "competitor-a.example", "https://competitor-a.example/vapt/"),
        ("cloud security provider", 1800, "competitor-a.example", "https://competitor-a.example/cloud/"),
        ("incident response retainer", 950, "competitor-b.example", "https://competitor-b.example/ir/"),
        ("soc as a service pricing", 620, "competitor-b.example", "https://competitor-b.example/soc/"),
    ]
    now = "2026-11-20T00:00:00+00:00"
    for phrase, volume, domain, url in phrases:
        db.add(Keyword(
            project_id=project.id, keyword=phrase, normalized=normalize_keyword(phrase),
            intent="unclassified", intent_source="pending", volume=volume,
            source="competitor_csv", collected_at=now, confidence="synthetic",
            evidence={"data_kind": "synthetic", "competitor_domain": domain, "competitor_url": url},
        ))
    db.commit()


def _seed_project_operations(db, project) -> None:
    if _count(db, Task, project.id):
        return
    db.add_all([
        Task(project_id=project.id, title="Review high-value 404 replacement suggestions",
             priority="P1", status="open", due_date="2026-11-30"),
        Task(project_id=project.id, title="Approve internal-link suggestions before implementation",
             priority="P2", status="open", due_date="2026-12-05"),
        Task(project_id=project.id, title="Validate hreflang plan with local stakeholders",
             priority="P2", status="open", due_date="2026-12-10"),
    ])
    db.add(MeetingNote(
        project_id=project.id, title="Weekly SEO delivery review",
        meeting_date="2026-11-20",
        notes="Synthetic demo note: discuss P0 issues, confirm owners, and validate provider imports before any client-facing reporting.",
    ))
    db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--size", type=int, default=1000, help="Synthetic URL count")
    parser.add_argument("--keyword-count", type=int, default=1000)
    parser.add_argument("--reset", action="store_true", help="Delete and regenerate demo projects")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.reset:
            print("Resetting existing demo data...")
            reset_demo_job(SessionLocal, 0, {}, None, None)
        project = db.scalar(select(Project).where(Project.is_demo.is_(True)).order_by(Project.id.desc()))
        if project is None:
            print(f"Generating {args.size:,} synthetic URLs and {args.keyword_count:,} keywords...")
            info = generate_demo(db, size=args.size, keyword_count=args.keyword_count)
            project = db.get(Project, info["project_id"])
            print(f"Created project {project.id}: {info['urls']:,} URLs")
        else:
            print(f"Reusing demo project {project.id}: {project.name}")
        print("NOTE: all traffic, revenue and keyword metrics in this database are synthetic.")

        _seed_competitor_data(db, project)
        _seed_project_operations(db, project)

        jobs = [
            ("detect_issues", "Detect technical issues", {}),
            ("detect_orphans", "Detect orphan pages", {}),
            ("link_suggestions", "Analyse internal-link graph", {}),
            ("cluster_keywords", "Cluster keywords", {"method": "normalized"}),
            ("map_keywords", "Map keyword clusters to URLs", {}),
            ("content_analysis", "Analyse content", {}),
            ("generate_briefs", "Generate content briefs", {}),
            ("competitor_analysis", "Analyse competitor gaps", {}),
            ("local_audit", "Audit locations", {}),
            ("ecommerce_audit", "Audit product catalogue", {}),
            ("migration_validate", "Validate redirect map", {}),
            ("ai_readiness", "Audit AI-search readiness", {}),
            ("generate_report", "Generate weekly report", {
                "period_start": "2026-11-02", "period_end": "2026-11-08",
                "previous_start": "2026-10-26", "previous_end": "2026-11-01",
                "generated_by": "seed_demo",
            }),
        ]
        for job_type, label, config in jobs:
            _run(db, job_type, label, project, config)

        print("Building labelled forecast scenario...")
        build_forecast(db, project.id, "Synthetic baseline scenario", {
            "current_clicks": 12000, "impressions": 400000, "ctr": 0.03,
            "average_position": 18, "conversion_rate": 0.018,
            "average_value": 420, "opportunity_clicks": 5000,
            "data_kind": "synthetic_assumption",
        })
        db.commit()

        from app.models.analysis import Issue, OrphanRecord
        from app.models.enterprise import AiReadinessItem
        from app.models.keywords import KeywordCluster, KeywordMapping
        from app.models.operations import Report

        summary = {
            "urls": _count(db, UrlRecord, project.id),
            "issues": _count(db, Issue, project.id),
            "orphans": _count(db, OrphanRecord, project.id),
            "keyword_clusters": _count(db, KeywordCluster, project.id),
            "keyword_mappings": _count(db, KeywordMapping, project.id),
            "reports": _count(db, Report, project.id),
            "ai_readiness_items": _count(db, AiReadinessItem, project.id),
        }
        print("Demo database ready:", summary)
        print("Login: demo@serpscope.local / demo1234")
    finally:
        db.close()


if __name__ == "__main__":
    main()
