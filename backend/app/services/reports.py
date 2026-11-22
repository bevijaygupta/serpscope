"""Unified reporting with explicit data gaps and business interpretation."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.models.operations import AnalyticsRecord, Report
from app.services.imports import to_float


def _totals(db: Session, project_id: int, start: str | None, end: str | None) -> dict[str, float]:
    if not start or not end:
        return {}
    row = db.execute(text(
        "SELECT COALESCE(SUM(clicks),0), COALESCE(SUM(impressions),0), COALESCE(SUM(sessions),0), "
        "COALESCE(SUM(conversions),0), COALESCE(SUM(revenue),0) FROM analytics_records "
        "WHERE project_id=:p AND period_start>=:s AND period_start<=:e"
    ), {"p": project_id, "s": start, "e": end}).first()
    if not row:
        return {}
    return {
        "clicks": float(row[0]), "impressions": float(row[1]), "sessions": float(row[2]),
        "conversions": float(row[3]), "revenue": float(row[4]),
        "ctr": round(100 * float(row[0]) / float(row[1]), 2) if row[1] else 0.0,
    }


def generate_weekly_report(
    db: Session,
    project_id: int,
    period_start: str | None = None,
    period_end: str | None = None,
    previous_start: str | None = None,
    previous_end: str | None = None,
    generated_by: str = "system",
) -> dict[str, Any]:
    """Generate a report with equivalent-range comparison when both ranges are supplied."""
    now = utcnow()
    end = period_end or now.date().isoformat()
    start = period_start or (now.date().replace(day=max(1, now.day - 7))).isoformat()
    current = _totals(db, project_id, start, end)
    previous = _totals(db, project_id, previous_start, previous_end) if previous_start and previous_end else {}
    missing = []
    if not current:
        missing.append("No analytics data for the current period")
    if not previous:
        missing.append("No equivalent comparison period supplied or available")
    for field in ("conversions", "revenue"):
        if current.get(field, 0) == 0:
            missing.append(f"No {field} data supplied; business impact is not quantified")

    changes = {}
    for key in ("clicks", "impressions", "sessions", "conversions", "revenue"):
        if current and previous and previous.get(key):
            changes[key] = round(100 * (current[key] - previous[key]) / previous[key], 2)
        else:
            changes[key] = None

    top_pages = db.execute(text(
        "SELECT dimension, SUM(clicks) clicks, SUM(impressions) impressions, SUM(sessions) sessions, "
        "SUM(revenue) revenue FROM analytics_records WHERE project_id=:p AND dimension_type='page' "
        "AND period_start>=:s AND period_start<=:e GROUP BY dimension ORDER BY clicks DESC LIMIT 10"
    ), {"p": project_id, "s": start, "e": end}).all()
    top_queries = db.execute(text(
        "SELECT dimension, SUM(clicks), SUM(impressions) FROM analytics_records "
        "WHERE project_id=:p AND dimension_type='query' AND period_start>=:s AND period_start<=:e "
        "GROUP BY dimension ORDER BY clicks DESC LIMIT 10"
    ), {"p": project_id, "s": start, "e": end}).all()
    open_issues = db.execute(text(
        "SELECT priority, COUNT(*) FROM issues WHERE project_id=:p AND status NOT IN ('Closed','Resolved') "
        "GROUP BY priority ORDER BY priority"
    ), {"p": project_id}).all()
    crawl = db.execute(text(
        "SELECT discovered, crawled, failed, summary FROM crawls WHERE project_id=:p "
        "ORDER BY id DESC LIMIT 1"
    ), {"p": project_id}).first()
    completed = db.execute(text(
        "SELECT COUNT(*) FROM tasks WHERE project_id=:p AND status='done'"
    ), {"p": project_id}).scalar() or 0
    pending = db.execute(text(
        "SELECT COUNT(*) FROM tasks WHERE project_id=:p AND status!='done'"
    ), {"p": project_id}).scalar() or 0
    orphans = db.execute(text(
        "SELECT COUNT(*) FROM orphan_records WHERE project_id=:p AND internal_inlinks=0"
    ), {"p": project_id}).scalar() or 0

    exec_summary_lines = []
    if current:
        exec_summary_lines.append(
            f"Organic clicks {current['clicks']:.0f}, impressions {current['impressions']:.0f}, "
            f"sessions {current['sessions']:.0f}."
        )
    if changes.get("clicks") is not None:
        direction = "up" if changes["clicks"] >= 0 else "down"
        exec_summary_lines.append(f"Clicks are {direction} {abs(changes['clicks']):.1f}% versus the equivalent prior period.")
    if current.get("revenue"):
        exec_summary_lines.append(f"Supplied revenue for the period: {current['revenue']:,.2f}.")
    exec_summary_lines.append(f"{orphans} URLs have no discovered internal inlinks; {len(open_issues)} priority groups remain open.")
    if missing:
        exec_summary_lines.append("Data gaps: " + "; ".join(missing))

    resolved_groups = db.execute(
        text("SELECT COUNT(*) FROM issues WHERE project_id=:p AND status IN ('Closed','Resolved')"),
        {"p": project_id},
    ).scalar() or 0

    sections = [
        {
            "heading": "1. Executive summary",
            "lines": exec_summary_lines,
        },
        {
            "heading": "2. Organic performance",
            "lines": [
                f"Current period {start} to {end}: " + (", ".join(f"{k}={v}" for k, v in current.items()) or "no data"),
                "Equivalent-period change %: " + (", ".join(f"{k}={v}" for k, v in changes.items()) or "unavailable"),
                "Business implication: " + (
                    "Traffic movement alone is not a business outcome; pair it with conversions/revenue when supplied."
                ),
            ],
        },
        {
            "heading": "3. Keyword movement",
            "lines": [f"{r[0]}: clicks={r[1]:.0f}, impressions={r[2]:.0f}" for r in top_queries]
                      or ["No query-level data imported."],
        },
        {
            "heading": "4. Landing-page performance",
            "lines": [f"{r[0]}: clicks={r[1]:.0f}, sessions={r[3]:.0f}, revenue={r[4]:.0f}" for r in top_pages]
                      or ["No landing-page data imported."],
        },
        {
            "heading": "5. Technical SEO findings",
            "lines": [f"{r[0]}: {r[1]} open issue groups" for r in open_issues]
                      + ([f"Latest crawl: discovered={crawl[0]}, crawled={crawl[1]}, errors={crawl[2]}"] if crawl else ["No crawl recorded."]),
        },
        {
            "heading": "6. Work completed",
            "lines": [f"Tasks marked done: {completed}"],
        },
        {
            "heading": "7. Issues resolved",
            "lines": [f"Resolved issue groups: {resolved_groups}"],
        },
        {
            "heading": "8. Open priorities",
            "lines": [f"{r[0]}: {r[1]}" for r in open_issues] or ["None recorded."],
        },
        {
            "heading": "9. Opportunities",
            "lines": [
                f"{orphans} orphan URLs are candidates for internal linking, prioritised in the Orphan Finder.",
                "Use the Forecasting module for scenario estimates; these are not guarantees.",
            ],
        },
        {
            "heading": "10. Next week's action plan",
            "lines": [
                "Validate and assign all P0/P1 issues with an owner and due date.",
                "Review high-value 404s and confirm replacement URLs before redirecting.",
                "Implement top internal-link suggestions on orphan and weak pages.",
                "Recrawl after implementation and compare equivalent date ranges again.",
            ],
        },
    ]
    content = {
        "period": {"start": start, "end": end, "previous_start": previous_start, "previous_end": previous_end},
        "current": current, "previous": previous, "changes_percent": changes,
        "sections": sections, "missing_data": missing,
        "data_kinds": ["imported analytics", "derived issue data", "rule-based recommendations"],
    }
    report = Report(
        project_id=project_id, title=f"Weekly SEO Report {start} - {end}",
        report_type="weekly", period_start=start, period_end=end,
        content=content, missing_data=missing, generated_by=generated_by,
    )
    db.add(report)
    db.commit()
    return {"report_id": report.id, **content}
