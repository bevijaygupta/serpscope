"""Analytics data, weekly reports and transparent forecasts."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.api.deps import DB, ProjectDep, UserDep, check_write
from app.api.v1._helpers import download, paged, serialize
from app.models.operations import AnalyticsRecord, Forecast, Report
from app.services.forecast import build_forecast
from app.services.jobs import enqueue
from app.services.reports import generate_weekly_report

router = APIRouter(prefix="/analytics", tags=["analytics"])

ANALYTICS_COLUMNS = ["id", "source", "data_kind", "dimension_type", "dimension", "period_start", "period_end", "clicks", "impressions", "ctr", "position", "sessions", "conversions", "revenue", "device", "country", "collected_at"]
REPORT_COLUMNS = ["id", "title", "report_type", "period_start", "period_end", "content", "missing_data", "generated_by", "created_at"]
FORECAST_COLUMNS = ["id", "name", "inputs", "scenarios", "formulas", "created_at"]


@router.get("/records")
def analytics_records(db: DB, project: ProjectDep, source: str | None = None, dimension_type: str | None = None,
                      q: str | None = None, offset: int = 0, limit: int = 100):
    query = select(AnalyticsRecord).where(AnalyticsRecord.project_id == project.id)
    if source:
        query = query.where(AnalyticsRecord.source == source)
    if dimension_type:
        query = query.where(AnalyticsRecord.dimension_type == dimension_type)
    if q:
        query = query.where(AnalyticsRecord.dimension.ilike(f"%{q}%"))
    from app.api.v1._helpers import page_query

    items, total = page_query(db, query, offset, limit, AnalyticsRecord.id)
    return paged([serialize(r, ANALYTICS_COLUMNS) for r in items], total, offset, limit)


@router.get("/summary")
def summary(db: DB, project: ProjectDep):
    sources = db.execute(
        select(AnalyticsRecord.source, AnalyticsRecord.data_kind, func.count(), func.sum(AnalyticsRecord.clicks), func.sum(AnalyticsRecord.sessions), func.sum(AnalyticsRecord.revenue))
        .where(AnalyticsRecord.project_id == project.id)
        .group_by(AnalyticsRecord.source, AnalyticsRecord.data_kind)
    ).all()
    return {"items": [{"source": r[0], "data_kind": r[1], "rows": r[2], "clicks": r[3] or 0, "sessions": r[4] or 0, "revenue": r[5] or 0} for r in sources]}


@router.post("/reports/generate", status_code=202)
def generate_report(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    job = enqueue(db, "generate_report", "Weekly SEO report", {"config": payload or {}},
                  project_id=project.id, organization_id=project.organization_id, created_by=user.id)
    db.commit()
    return {"job_id": job.id, "status": "queued"}


@router.post("/reports/generate-now")
def generate_now(payload: dict | None, db: DB, user: UserDep, project: ProjectDep):
    """Synchronous generation for demo screens with small datasets."""
    check_write(user)
    return generate_weekly_report(db, project.id, **(payload or {}), generated_by=user.email)


@router.get("/reports")
def reports(db: DB, project: ProjectDep, offset: int = 0, limit: int = 100):
    from app.api.v1._helpers import page_query

    items, total = page_query(db, select(Report).where(Report.project_id == project.id), offset, limit, Report.id.desc())
    return paged([serialize(r, ["id", "title", "report_type", "period_start", "period_end", "missing_data", "generated_by", "created_at"]) for r in items], total, offset, limit)


@router.get("/reports/{report_id}")
def get_report(report_id: int, db: DB, project: ProjectDep):
    report = db.get(Report, report_id)
    if report is None or report.project_id != project.id:
        raise HTTPException(404, "Report not found")
    return serialize(report, REPORT_COLUMNS)


@router.get("/reports/{report_id}/export")
def export_report(report_id: int, db: DB, project: ProjectDep, format: str = "pdf"):
    report = db.get(Report, report_id)
    if report is None or report.project_id != project.id:
        raise HTTPException(404, "Report not found")
    content = report.content or {}
    sections = content.get("sections") or []
    if format == "pdf":
        return download([], [], f"weekly_seo_report_{report_id}", "pdf",
                        pdf_sections=sections + [{"heading": "Missing data", "lines": content.get("missing_data") or ["None"]}])
    return download([{"section": s["heading"], "lines": "; ".join(s["lines"])} for s in sections],
                    ["section", "lines"], f"weekly_seo_report_{report_id}", format)


@router.post("/forecasts", status_code=201)
def create_forecast(payload: dict, db: DB, user: UserDep, project: ProjectDep):
    check_write(user)
    return build_forecast(db, project.id, payload.get("name", "SEO opportunity forecast"),
                          payload.get("inputs") or {}, user.id)


@router.get("/forecasts")
def forecasts(db: DB, project: ProjectDep):
    rows = db.scalars(select(Forecast).where(Forecast.project_id == project.id).order_by(Forecast.id.desc()).limit(100)).all()
    return {"items": [serialize(r, FORECAST_COLUMNS) for r in rows]}
