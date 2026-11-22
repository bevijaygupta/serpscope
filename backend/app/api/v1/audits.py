"""Public-evidence site audit, six-month roadmap and presentation exports."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
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
    return public_audit.build_public_audit(db, project.id)


@router.get("/projects/{project_id}/public-audit/export")
def export_public_audit(project: ProjectDep, db: DB, format: str = "json", section: str = "all"):
    format = (format or "json").lower()
    audit = public_audit.build_public_audit(db, project.id)
    base = f"serpscope_public_audit_{project.id}"
    if section == "findings":
        rows = public_audit.finding_rows(audit)
        return download(rows, AUDIT_COLUMNS, f"{base}_findings", format)
    if section == "roadmap":
        rows = public_audit.roadmap_rows(audit)
        return download(rows, ROADMAP_COLUMNS, f"{base}_6_month_roadmap", format)
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


@public_router.get("/case-studies/{project_id}")
def published_case_study(project_id: int, db: DB):
    """Read-only audit for projects explicitly marked public in project settings."""
    project = db.get(Project, project_id)
    if project is None or not (project.settings or {}).get("public_audit"):
        raise HTTPException(404, "Published audit not found")
    return public_audit.build_public_audit(db, project_id)
