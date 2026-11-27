"""Storage and reporting for supplied vendor/private datasets.

Rows arrive either from a user upload or, only when a live connector is
explicitly enabled and configured, from a real provider response. Both paths
store values verbatim and never invent a private metric. A signal changes from
``Not supplied`` only when rows are actually stored; ``data_kind`` records
whether they came from a file or a live API.
"""
from __future__ import annotations

from typing import Any, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.operations import SuppliedMetric

SOURCE_SIGNALS: dict[str, tuple[str, str]] = {
    "gsc": ("gsc", "Search Console queries, impressions, CTR and position"),
    "gsc_live": ("gsc", "Search Console rows fetched by an explicitly enabled live connector"),
    "ga4": ("ga4", "GA4 sessions, conversions and revenue"),
    "ga4_live": ("ga4", "GA4 rows fetched by an explicitly enabled live connector"),
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


def row_identity(row: dict[str, Any], name: str) -> tuple[str, str | None]:
    """The exact dimension/period pair used when a row is stored.

    Keeping this in one place prevents a live sync from re-inserting rows that
    an earlier sync already recorded under a different alias preference.
    """
    dimension = (_lookup(row, _DIMENSION_ALIASES) or name)[:2000]
    period = _lookup(row, _DATE_ALIASES)[:20] or None
    return dimension, period


def store_supplied_metrics(
    db: Session,
    project_id: int,
    source_type: str,
    name: str,
    rows: list[dict[str, Any]],
    data_kind: str = "imported",
    data_source_id: int | None = None,
    meta: dict[str, Any] | None = None,
) -> int:
    signal, label = signal_for_source(source_type)
    records: list[dict[str, Any]] = []
    for row in rows:
        dimension, period = row_identity(row, name)
        records.append({
            "project_id": project_id,
            "source": source_type,
            "signal": signal,
            "data_kind": data_kind,
            "dimension": dimension,
            "period_start": period,
            "period_end": period,
            "metrics": {str(k): ("" if v is None else str(v)) for k, v in row.items()},
            "meta_info": {
                "label": label, "file": name,
                "import_convention": "verbatim_user_supplied", **(meta or {}),
            },
            "data_source_id": data_source_id,
        })
    for start in range(0, len(records), 2000):
        db.bulk_insert_mappings(SuppliedMetric, records[start:start + 2000])
    db.flush()
    return len(records)


def supplied_signals(db: Session, project_id: int) -> dict[str, dict[str, Any]]:
    """Return a compact status object for every signal the audit talks about."""
    def blank() -> dict[str, Any]:
        return {
            "supplied": False, "rows": 0, "live_rows": 0, "status": "not_supplied",
            "sources": [], "latest_period": "", "sample": [],
        }

    grouped: dict[str, dict[str, Any]] = {key: blank() for key in SIGNAL_LABELS}
    for source, signal, count in db.execute(
        select(SuppliedMetric.source, SuppliedMetric.signal, func.count())
        .where(SuppliedMetric.project_id == project_id)
        .group_by(SuppliedMetric.source, SuppliedMetric.signal)
    ).all():
        entry = grouped.setdefault(signal, blank())
        entry["supplied"] = True
        entry["rows"] += int(count)
        if source not in entry["sources"]:
            entry["sources"].append(source)

    for signal, count in db.execute(
        select(SuppliedMetric.signal, func.count())
        .where(
            SuppliedMetric.project_id == project_id,
            SuppliedMetric.data_kind.like("api_live:%"),
        )
        .group_by(SuppliedMetric.signal)
    ).all():
        grouped.setdefault(signal, blank())["live_rows"] = int(count)

    for signal in grouped:
        if not grouped[signal]["supplied"]:
            continue
        grouped[signal]["status"] = (
            "api_live" if grouped[signal]["live_rows"] else "supplied"
        )
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
