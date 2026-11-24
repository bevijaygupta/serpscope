"""Storage and reporting for user-supplied vendor/private datasets.

SERPScope never calls a vendor API on the user's behalf and never invents a
private metric. When a user uploads an export, its rows are stored verbatim in
``supplied_metrics`` and grouped into a signal so the audit can honestly change
a status from ``Not supplied`` to ``Supplied by user``.
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.operations import SuppliedMetric

SOURCE_SIGNALS: dict[str, tuple[str, str]] = {
    "gsc": ("gsc", "Search Console queries, impressions, CTR and position"),
    "ga4": ("ga4", "GA4 sessions, conversions and revenue"),
    "analytics": ("ga4", "Analytics sessions, conversions and revenue"),
    "rank_tracking": ("rank", "Rank tracking positions over time"),
    "backlinks": ("backlinks", "Inbound backlinks and referring domains"),
    "authority": ("authority", "Third-party domain authority"),
    "lighthouse": ("performance", "Lighthouse and Core Web Vitals"),
    "crux": ("crux", "CrUX field Core Web Vitals"),
    "serp_features": ("serp", "SERP features and rich results"),
    "paid_ads": ("paid", "Paid ads, paid keywords and spend"),
    "gbp": ("local", "Google Business Profile and local visibility"),
    "historical_audit": ("historical", "Retained audit history and trends"),
    "keyword_csv": ("keywords", "Keyword volume, difficulty and CPC"),
    "competitor_csv": ("keywords", "Competitor keyword estimates"),
}

SIGNAL_LABELS: dict[str, str] = {
    "gsc": "Search Console",
    "ga4": "GA4 / analytics",
    "keywords": "Keyword volume, difficulty and CPC",
    "rank": "Rank tracking",
    "backlinks": "Inbound backlinks",
    "authority": "Domain authority",
    "performance": "Lighthouse / Core Web Vitals",
    "crux": "CrUX field data",
    "serp": "SERP features",
    "paid": "Paid ads",
    "local": "Local / GBP",
    "historical": "Historical trends",
}

_DIMENSION_ALIASES = (
    "url", "page", "landing page", "query", "keyword", "search query",
    "domain", "referring domain", "hostname", "location", "business name",
)
_DATE_ALIASES = ("date", "period", "day", "month", "week", "collected at", "date collected")


def signal_for_source(source_type: str) -> tuple[str, str]:
    return SOURCE_SIGNALS.get(source_type, ("other", "User-supplied data"))


def _lookup(row: dict[str, Any], aliases: Iterable[str]) -> str:
    lower = {str(k).lower().strip(): v for k, v in row.items()}
    for alias in aliases:
        if alias in lower and lower[alias] not in (None, ""):
            return str(lower[alias])
    for alias in aliases:
        for key, value in lower.items():
            if alias in key and value not in (None, ""):
                return str(value)
    return ""


def store_supplied_metrics(
    db: Session,
    project_id: int,
    source_type: str,
    name: str,
    rows: list[dict[str, Any]],
    data_kind: str = "imported",
    data_source_id: int | None = None,
) -> int:
    signal, label = signal_for_source(source_type)
    records: list[dict[str, Any]] = []
    for row in rows:
        dimension = _lookup(row, _DIMENSION_ALIASES) or name
        period = _lookup(row, _DATE_ALIASES)
        records.append({
            "project_id": project_id,
            "source": source_type,
            "signal": signal,
            "data_kind": data_kind,
            "dimension": dimension[:2000],
            "period_start": period[:20] or None,
            "period_end": period[:20] or None,
            "metrics": {str(k): ("" if v is None else str(v)) for k, v in row.items()},
            "meta_info": {"label": label, "file": name, "import_convention": "verbatim_user_supplied"},
            "data_source_id": data_source_id,
        })
    for start in range(0, len(records), 2000):
        db.bulk_insert_mappings(SuppliedMetric, records[start:start + 2000])
    db.flush()
    return len(records)


def supplied_signals(db: Session, project_id: int) -> dict[str, dict[str, Any]]:
    """Return a compact status object for every signal the audit talks about."""
    grouped: dict[str, dict[str, Any]] = {
        key: {"supplied": False, "rows": 0, "sources": [], "latest_period": "", "sample": []}
        for key in SIGNAL_LABELS
    }
    for source, signal, count in db.execute(
        select(SuppliedMetric.source, SuppliedMetric.signal, func.count())
        .where(SuppliedMetric.project_id == project_id)
        .group_by(SuppliedMetric.source, SuppliedMetric.signal)
    ).all():
        entry = grouped.setdefault(signal, {"supplied": False, "rows": 0, "sources": [], "latest_period": "", "sample": []})
        entry["supplied"] = True
        entry["rows"] += int(count)
        if source not in entry["sources"]:
            entry["sources"].append(source)

    for signal in grouped:
        if not grouped[signal]["supplied"]:
            continue
        rows = db.scalars(
            select(SuppliedMetric)
            .where(SuppliedMetric.project_id == project_id, SuppliedMetric.signal == signal)
            .order_by(SuppliedMetric.id.desc())
            .limit(5)
        ).all()
        periods = sorted({r.period_start for r in rows if r.period_start})
        grouped[signal]["latest_period"] = periods[-1] if periods else ""
        grouped[signal]["sample"] = [
            {"dimension": r.dimension, "period": r.period_start or "", "metrics": r.metrics}
            for r in rows[:3]
        ]
    return grouped


def supplied_record_rows(db: Session, project_id: int, signal: str, limit: int = 100) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id, "source": r.source, "signal": r.signal, "data_kind": r.data_kind,
            "dimension": r.dimension, "period": r.period_start or "", "metrics": r.metrics,
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else "",
        }
        for r in db.scalars(
            select(SuppliedMetric)
            .where(SuppliedMetric.project_id == project_id, SuppliedMetric.signal == signal)
            .order_by(SuppliedMetric.id.desc())
            .limit(limit)
        ).all()
    ]
