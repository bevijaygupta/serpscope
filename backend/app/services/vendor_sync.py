"""Explicit, tenant-scoped live sync that stores verbatim provider rows only.

There is no background scheduler and no automatic sync. A caller must already
be authenticated, have write access to the project, and target an Integration
record whose mode is ``oauth_api`` and whose credentials were stored earlier.
No value is generated, inferred or back-filled here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.operations import Integration, SuppliedMetric
from app.services import vendor_connectors as connectors
from app.services.supplied_metrics import row_identity, store_supplied_metrics

SOURCE_TYPES = {
    "google_search_console": "gsc_live",
    "google_analytics_4": "ga4_live",
}


def sync_integration(db: Session, item: Integration) -> dict[str, Any]:
    """Fetch one provider's rows and store only rows not already recorded."""
    provider = item.provider
    if provider not in SOURCE_TYPES:
        raise connectors.ConnectorUnavailable("This provider has no live sync adapter")
    if item.project_id is None:
        raise connectors.ConnectorUnavailable("Live sync requires a project-scoped integration")
    if item.mode != "oauth_api":
        raise connectors.ConnectorUnavailable("Live sync requires oauth_api mode")
    if item.status not in {"configured", "connected"} or not item.credentials_encrypted:
        raise connectors.ConnectorUnavailable("Integration has no stored credentials")

    config = item.config or {}
    fetched_at = datetime.now(timezone.utc).isoformat()
    if provider == "google_search_console":
        rows = connectors.fetch_gsc_rows(
            item.credentials_encrypted, config.get("site_url"),
            config.get("start_date"), config.get("end_date"), config.get("row_limit"),
        )
    else:
        rows = connectors.fetch_ga4_rows(
            item.credentials_encrypted, config.get("property_id"),
            config.get("start_date"), config.get("end_date"), config.get("row_limit"),
        )

    source_type = SOURCE_TYPES[provider]
    existing = {
        (source, dimension, period)
        for source, dimension, period in db.execute(
            select(SuppliedMetric.source, SuppliedMetric.dimension, SuppliedMetric.period_start)
            .where(SuppliedMetric.project_id == item.project_id, SuppliedMetric.source == source_type)
        ).all()
    }
    fresh: list[dict[str, Any]] = []
    name = f"{provider} live sync"
    for row in rows:
        dimension, period = row_identity(row, name)
        key = (source_type, dimension, period)
        if key in existing:
            continue
        existing.add(key)
        fresh.append(row)

    stored = store_supplied_metrics(
        db, item.project_id, source_type, name, fresh,
        data_kind=connectors.DATA_KINDS[provider],
        meta={
            "import_convention": "verbatim_live_api",
            "fetched_at": fetched_at,
            "live_connector": provider,
            "generated": False,
        },
    )
    item.last_sync_at = fetched_at
    item.status = "connected"
    item.notes = f"{item.notes or ''}\nLive sync {fetched_at}: {len(rows)} fetched, {stored} stored."
    db.commit()
    return {
        "provider": provider,
        "rows_fetched": len(rows),
        "rows_stored": stored,
        "source": source_type,
        "data_kind": connectors.DATA_KINDS[provider],
        "fetched_at": fetched_at,
    }
