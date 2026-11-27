"""Background job handlers for large file imports."""
from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.core.timeutil import iso, utcnow
from app.models.keywords import Keyword
from app.models.projects import DataSource
from app.services.imports import parse_sitemap, parse_table, store_sitemap_entries, to_float, upsert_urls, URL_COLUMN_ALIASES
from app.services.jobs import is_cancelled, progress, register
from app.services.keywords import normalize_keyword
from app.services.supplied_metrics import store_supplied_metrics


def _find_col(columns: list[str], aliases: list[str]) -> str | None:
    lookup = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    for alias in aliases:
        for key, original in lookup.items():
            if alias in key:
                return original
    return None


def _safe_upload_path(file_path: object) -> Path:
    """Resolve a queued upload only inside the configured upload directory."""
    root = settings.upload_path.resolve()
    path = Path(str(file_path or "")).resolve()
    if root != path.parent and root not in path.parents:
        raise ValueError("Upload path is outside the configured upload directory")
    return path


def _remove_upload(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Cleanup failure must not turn a completed import into a failed job.
        pass


def _cancelled_import_result(mapping: dict | None = None, accepted: int = 0, rejected: int = 0) -> dict:
    return {
        "data_source_id": None, "accepted": accepted, "rejected": rejected,
        "supplied_metric_rows": 0, "column_mapping": mapping or {}, "errors": [],
    }


def _cancelled_keyword_result(mapping: dict | None = None) -> dict:
    return {"imported": 0, "column_mapping": mapping or {}, "data_source_id": None}


@register("import_file")
def run_import(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    path: Path | None = None
    try:
        path = _safe_upload_path(payload.get("file_path"))
        if is_cancelled(job_id):
            return _cancelled_import_result()
        source_type = payload.get("source_type", "csv_urls")
        name = payload.get("name") or path.name
        content = path.read_bytes()
        rules = payload.get("normalization_rules") or {}
        accepted = rejected = 0
        errors: list[str] = []
        mapping: dict = {}
        if source_type in {"sitemap", "sitemap_index"}:
            entries, kind = parse_sitemap(content)
            urls = [e["loc"] for e in entries]
            if is_cancelled(job_id):
                return _cancelled_import_result({"loc": "url"})
            if kind == "sitemap":
                store_sitemap_entries(db, project_id, entries, name)
                accepted, rejected, errors = upsert_urls(
                    db, project_id, urls, source_type, "imported", rules,
                    extra={"in_sitemap": True},
                )
            else:
                accepted, rejected, errors = upsert_urls(
                    db, project_id, urls, "sitemap_index", "imported", rules,
                )
            mapping = {"loc": "url"}
        else:
            columns, rows = parse_table(content, name)
            mapping = {
                "url": _find_col(columns, URL_COLUMN_ALIASES) or "",
                "clicks": _find_col(columns, ["clicks", "organic clicks"]) or "",
                "impressions": _find_col(columns, ["impressions", "organic impressions"]) or "",
                "sessions": _find_col(columns, ["sessions", "users", "pageviews"]) or "",
                "conversions": _find_col(columns, ["conversions", "key events", "transactions"]) or "",
                "revenue": _find_col(columns, ["revenue", "item revenue", "value"]) or "",
                "title": _find_col(columns, ["title", "page title", "h1"]) or "",
                "referring_domains": _find_col(columns, ["referring domains", "domains", "backlinks"]) or "",
            }
            if not mapping["url"] and source_type in {"csv_urls", "cms", "screaming_frog", "sitebulb"}:
                raise ValueError("No URL-like column found. Columns: " + ", ".join(columns[:30]))
            total = len(rows)
            for index, row in enumerate(rows):
                if is_cancelled(job_id):
                    break
                if not mapping["url"]:
                    # Query/domain/location exports have no landing-page URL;
                    # their rows are stored verbatim as supplied metrics.
                    accepted += 1
                    continue
                extra = {
                    "title": row.get(mapping["title"], "") if mapping["title"] else "",
                    "clicks": to_float(row.get(mapping["clicks"])) if mapping["clicks"] else 0,
                    "impressions": to_float(row.get(mapping["impressions"])) if mapping["impressions"] else 0,
                    "sessions": to_float(row.get(mapping["sessions"])) if mapping["sessions"] else 0,
                    "conversions": to_float(row.get(mapping["conversions"])) if mapping["conversions"] else 0,
                    "revenue": to_float(row.get(mapping["revenue"])) if mapping["revenue"] else 0,
                    "referring_domains": to_float(row.get(mapping["referring_domains"])) if mapping["referring_domains"] else 0,
                    "in_sitemap": source_type == "sitemap",
                }
                a, r, e = upsert_urls(
                    db, project_id, [row.get(mapping["url"], "")], source_type,
                    payload.get("data_kind", "imported"), rules, extra=extra,
                )
                accepted += a
                rejected += r
                errors.extend(e[:3])
                if index % 500 == 0:
                    progress(job_id, index, total, f"Imported {index}/{total} rows")
                    db.commit()
        if is_cancelled(job_id):
            return _cancelled_import_result(mapping, accepted, rejected)
        source = DataSource(
            project_id=project_id, source_type=source_type, name=name,
            file_name=path.name, row_count=accepted, rejected_count=rejected,
            status="ready", data_kind=payload.get("data_kind", "imported"),
            meta_info={"column_mapping": mapping, "errors": errors[:20]}, job_id=job_id,
        )
        db.add(source)
        db.flush()
        if is_cancelled(job_id):
            return _cancelled_import_result(mapping, accepted, rejected)
        supplied_rows = store_supplied_metrics(
            db, project_id, source_type, name, rows,
            payload.get("data_kind", "imported"), source.id,
        )
        source.meta_info = {**(source.meta_info or {}), "supplied_metric_rows": supplied_rows}
        db.commit()
        progress(job_id, 100, 100, "Import complete")
        return {
            "data_source_id": source.id, "accepted": accepted, "rejected": rejected,
            "supplied_metric_rows": supplied_rows,
            "column_mapping": mapping, "errors": errors[:20],
        }
    finally:
        _remove_upload(path)
        db.close()


@register("import_keywords")
def import_keywords_job(db_session_factory, job_id, payload, project_id, organization_id):
    db = db_session_factory()
    path: Path | None = None
    try:
        path = _safe_upload_path(payload.get("file_path"))
        if is_cancelled(job_id):
            return _cancelled_keyword_result()
        source_type = payload.get("source_type", "keyword_csv")
        columns, rows = parse_table(path.read_bytes(), path.name)
        mapping = {
            "keyword": _find_col(columns, ["keyword", "query", "search query", "term", "search term", "phrase"]),
            "volume": _find_col(columns, ["volume", "search volume", "monthly volume", "avg monthly searches"]),
            "difficulty": _find_col(columns, ["difficulty", "keyword difficulty", "kd", "competition difficulty"]),
            "cpc": _find_col(columns, ["cpc", "cost per click"]),
            "intent": _find_col(columns, ["intent", "search intent"]),
            "topic": _find_col(columns, ["topic", "category", "group"]),
            "parent_topic": _find_col(columns, ["parent topic", "parent", "theme"]),
            "country": _find_col(columns, ["country", "location", "region"]),
            "language": _find_col(columns, ["language", "lang"]),
            "confidence": _find_col(columns, ["confidence", "data confidence"]),
            "competitor_url": _find_col(columns, ["competitor url", "url", "page", "sitemap url"]),
            "collected_at": _find_col(columns, ["date collected", "collected at", "date"]),
        }
        if not mapping["keyword"]:
            raise ValueError("No keyword column found. Columns: " + ", ".join(columns[:30]))
        records = []
        for index, row in enumerate(rows):
            if is_cancelled(job_id):
                break
            keyword = (row.get(mapping["keyword"]) or "").strip()
            if not keyword or len(keyword) > 300:
                continue
            evidence = {}
            if source_type == "competitor_csv":
                evidence["competitor_domain"] = payload.get("competitor_domain", "")
                if mapping["competitor_url"]:
                    evidence["competitor_url"] = row.get(mapping["competitor_url"], "")
            records.append({
                "project_id": project_id, "keyword": keyword,
                "normalized": normalize_keyword(keyword),
                "intent": (row.get(mapping["intent"], "") if mapping["intent"] else "") or "unclassified",
                "intent_source": "imported" if mapping["intent"] else "pending",
                "topic": (row.get(mapping["topic"], "") if mapping["topic"] else "")[:150],
                "parent_topic": (row.get(mapping["parent_topic"], "") if mapping["parent_topic"] else "")[:150],
                "country": (row.get(mapping["country"], "") if mapping["country"] else "")[:10],
                "language": (row.get(mapping["language"], "") if mapping["language"] else "")[:20],
                "volume": int(to_float(row.get(mapping["volume"]))) if mapping["volume"] else None,
                "difficulty": to_float(row.get(mapping["difficulty"])) if mapping["difficulty"] else None,
                "cpc": to_float(row.get(mapping["cpc"])) if mapping["cpc"] else None,
                "source": source_type, "collected_at": (row.get(mapping["collected_at"]) if mapping["collected_at"] else iso(utcnow()))[:40],
                "confidence": (row.get(mapping["confidence"], "imported") if mapping["confidence"] else "imported"),
                "evidence": evidence,
            })
            if index % 1000 == 0:
                progress(job_id, index, len(rows), f"Imported {index}/{len(rows)} keywords")
        if is_cancelled(job_id):
            return _cancelled_keyword_result(mapping)
        for start in range(0, len(records), 4000):
            db.bulk_insert_mappings(Keyword, records[start:start + 4000])
        if is_cancelled(job_id):
            return _cancelled_keyword_result(mapping)
        source = DataSource(
            project_id=project_id, source_type=source_type, name=path.name,
            file_name=path.name, row_count=len(records), status="ready",
            data_kind="imported", meta_info={"column_mapping": mapping}, job_id=job_id,
        )
        db.add(source)
        db.flush()
        if is_cancelled(job_id):
            return _cancelled_keyword_result(mapping)
        store_supplied_metrics(db, project_id, source_type, path.name, rows, "imported", source.id)
        db.commit()
        progress(job_id, 100, 100, "Keyword import complete")
        return {"imported": len(records), "column_mapping": mapping, "data_source_id": source.id}
    finally:
        _remove_upload(path)
        db.close()
