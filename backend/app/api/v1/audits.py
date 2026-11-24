"""Public-evidence site audit, six-month roadmap and presentation exports."""
from __future__ import annotations

import html
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy import select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, serialize
from app.core.config import settings
from app.models.operations import Report
from app.models.projects import Project
from app.services import public_audit
from app.services.exports import export_pptx_report
from app.services.jobs import enqueue

router = APIRouter(prefix="/audits", tags=["audits"])
public_router = APIRouter(prefix="/public", tags=["public"])

AUDIT_COLUMNS = [
    "id", "severity", "category", "affected_count", "observation",
    "recommended_action", "source", "confidence", "limitation",
]
ROADMAP_COLUMNS = [
    "month", "theme", "objective", "actions", "deliverables", "owner",
    "success_checks", "without_access", "with_access",
]
CASE_STUDY_BASE_URL = "https://serpscopelive.vercel.app"


def _published_case_studies(db) -> list[dict]:
    """List successful public audits that are safe to publish."""
    projects = db.scalars(select(Project).where(Project.is_demo.is_(False))).all()
    items: list[dict] = []
    for project in projects:
        if not (project.settings or {}).get("public_audit"):
            continue
        report = db.scalars(
            select(Report).where(
                Report.project_id == project.id,
                Report.report_type == "public_audit",
            ).order_by(Report.id.desc()).limit(1)
        ).first()
        if report is None or not isinstance(report.content, dict) or not report.content.get("meta"):
            continue
        content = report.content
        meta = content.get("meta") or {}
        coverage = content.get("coverage") or {}
        findings = content.get("findings") or []
        items.append({
            "project_id": project.id,
            "report_id": report.id,
            "name": project.name,
            "domain": project.domain,
            "generated_at": meta.get("generated_at"),
            "fetched_urls": coverage.get("fetched_urls", 0),
            "sitemap_entries": coverage.get("sitemap_entries", 0),
            "findings": len(findings),
            "roadmap_months": len(content.get("roadmap") or []),
            "roadmap_themes": [row.get("theme") for row in (content.get("roadmap") or []) if isinstance(row, dict)],
            "top_findings": [
                {
                    "title": row.get("title"),
                    "severity": row.get("severity"),
                    "affected_count": row.get("affected_count", 0),
                }
                for row in findings[:3] if isinstance(row, dict)
            ],
            "ai_visibility_status": (content.get("ai_visibility") or {}).get("status", "not_sampled"),
            "case_study_path": f"/case-studies/{project.id}",
            "case_study_url": f"{CASE_STUDY_BASE_URL}/case-studies/{project.id}",
        })
    items.sort(key=lambda row: str(row.get("generated_at") or ""), reverse=True)
    return items


def _audit_for_project(db, project_id: int) -> dict:
    """Return the persisted public-audit report when one exists.

    Rebuilding from the latest crawl can silently switch the numbers to an
    unrelated or still-running crawl. The stored report is the exact output
    produced when the public-audit job succeeded, so it is the authoritative
    evidence pack for that job.
    """
    report = db.scalars(
        select(Report).where(
            Report.project_id == project_id,
            Report.report_type == "public_audit",
        ).order_by(Report.id.desc()).limit(1)
    ).first()
    if report and isinstance(report.content, dict) and report.content.get("meta"):
        audit = dict(report.content)
        audit["meta"] = dict(audit["meta"])
        audit["meta"]["report_id"] = report.id
    else:
        audit = public_audit.build_public_audit(db, project_id)
    # Crawl findings remain the persisted evidence pack; supplied-data status,
    # source registry, gaps and report sections must reflect current imports.
    return public_audit.apply_supplied_data(db, project_id, audit)


@router.post("/projects/{project_id}/public-audit/start", status_code=202)
def start_public_audit(db: DB, user: UserDep, project: ProjectDep, payload: dict | None = None):
    """Queue a full public-evidence audit: crawl → analysis → report → roadmap."""
    check_write(user)
    body = payload or {}
    job = enqueue(
        db, "public_audit", body.get("name") or f"Public audit · {project.domain}",
        {"start_url": body.get("start_url") or project.domain, "config": body.get("config") or {}, "name": body.get("name")},
        project_id=project.id, organization_id=project.organization_id, created_by=user.id,
    )
    db.commit()
    return {
        "job_id": job.id,
        "status": "queued",
        "note": "Robots-aware crawl from public evidence only. No Search Console or Analytics access is required.",
    }


@router.get("/projects/{project_id}/public-audit")
def get_public_audit(db: DB, project: ProjectDep):
    return _audit_for_project(db, project.id)


@router.get("/projects/{project_id}/public-audit/export")
def export_public_audit(project: ProjectDep, db: DB, format: str = "json", section: str = "all"):
    format = (format or "json").lower()
    audit = _audit_for_project(db, project.id)
    base = f"serpscope_public_audit_{project.id}"
    if section == "findings":
        rows = public_audit.finding_rows(audit)
        return download(rows, AUDIT_COLUMNS, f"{base}_findings", format)
    if section == "roadmap":
        rows = public_audit.roadmap_rows(audit)
        return download(rows, ROADMAP_COLUMNS, f"{base}_6_month_roadmap", format)
    if section == "all" and format == "json":
        # "All" must mean the complete source-tracked audit, not a summary row.
        content = json.dumps(audit, ensure_ascii=False, indent=2, default=str).encode("utf-8")
        settings.export_path.mkdir(parents=True, exist_ok=True)
        path = settings.export_path / f"{base}.json"
        path.write_bytes(content)
        return FileResponse(str(path), media_type="application/json", filename=f"{base}.json")
    if format == "pdf":
        return download([], [], base, "pdf", pdf_sections=audit["sections"])
    if format == "pptx":
        content, media_type, filename = export_pptx_report(
            f"{audit['meta']['project_name']} · Public SEO Audit",
            public_audit.to_ppt_slides(audit),
            f"{base}.pptx",
        )
        settings.export_path.mkdir(parents=True, exist_ok=True)
        path = settings.export_path / filename
        path.write_bytes(content)
        return FileResponse(str(path), media_type=media_type, filename=filename)
    rows = [{
        "project": audit["meta"]["project_name"],
        "domain": audit["meta"]["domain"],
        "generated_at": audit["meta"]["generated_at"],
        "crawl_id": audit["meta"]["crawl_id"] or "",
        "fetched_urls": audit["coverage"]["fetched_urls"],
        "sitemap_entries": audit["coverage"]["sitemap_entries"],
        "findings": len(audit["findings"]),
        "roadmap_months": len(audit["roadmap"]),
        "missing_data": "; ".join(audit["missing_data"]),
    }]
    columns = ["project", "domain", "generated_at", "crawl_id", "fetched_urls", "sitemap_entries", "findings", "roadmap_months", "missing_data"]
    return download(rows, columns, base, format)


@router.get("/projects/{project_id}/public-audit/reports")
def list_public_reports(db: DB, project: ProjectDep):
    rows = db.scalars(
        select(Report).where(Report.project_id == project.id, Report.report_type == "public_audit")
        .order_by(Report.id.desc()).limit(50)
    ).all()
    return {"items": [serialize(r, ["id", "title", "generated_by", "created_at", "missing_data"]) for r in rows]}


@public_router.get("/case-studies")
def published_case_studies(db: DB):
    """Index every successful public audit for discovery and internal linking."""
    items = _published_case_studies(db)
    return {
        "count": len(items),
        "source": "public_evidence_only",
        "note": "Every real public audit is published automatically after its job succeeds. Private uploads are excluded.",
        "items": items,
    }


@public_router.get("/case-studies/sitemap.xml")
def published_case_studies_sitemap(db: DB):
    """Dynamic sitemap of published case studies."""
    urls = [
        (f"{CASE_STUDY_BASE_URL}/case-studies", None),
        *[
            (row["case_study_url"], str(row.get("generated_at") or "")[:10] or None)
            for row in _published_case_studies(db)
        ],
    ]
    entries = []
    for url, lastmod in urls:
        modified = f"<lastmod>{html.escape(lastmod)}</lastmod>" if lastmod else ""
        entries.append(
            "<url>"
            f"<loc>{html.escape(url)}</loc>{modified}"
            "<changefreq>weekly</changefreq>"
            "<priority>0.8</priority>"
            "</url>"
        )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + "".join(entries)
        + "</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@public_router.get("/case-studies/{project_id}")
def published_case_study(project_id: int, db: DB):
    """Read-only, public-evidence-only audit for a published project."""
    project = db.get(Project, project_id)
    if project is None or project.is_demo or not (project.settings or {}).get("public_audit"):
        raise HTTPException(404, "Published audit not found")
    audit = _audit_for_project(db, project_id)
    return public_audit.public_case_study_view(audit)
