"""File import and normalisation for URL, sitemap, GSC and analytics exports."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import classify_page_type, hostname_of, normalize_url, path_of, url_hash, validate_target_url
from app.models.inventory import SitemapEntry, UrlRecord

URL_COLUMN_ALIASES = [
    "url", "address", "page", "page url", "landing page", "landing page + query string",
    "full url", "final url", "location", "loc", "canonical", "source url", "old url", "new url",
]
CLICK_ALIASES = ["clicks", "organic clicks", "sessions", "pageviews", "screen page views"]
IMPRESSION_ALIASES = ["impressions", "organic impressions"]
CTR_ALIASES = ["ctr", "click through rate"]
POSITION_ALIASES = ["position", "average position", "avg position"]
CONVERSION_ALIASES = ["conversions", "key events", "goals", "transactions"]
REVENUE_ALIASES = ["revenue", "item revenue", "total revenue", "value"]


@dataclass
class ImportResult:
    source_type: str
    total_rows: int = 0
    accepted: int = 0
    rejected: int = 0
    columns: list[str] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    preview: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "total_rows": self.total_rows,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "columns": self.columns,
            "mapping": self.mapping,
            "errors": self.errors[:20],
            "preview": self.preview,
        }


def sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        comma = sample[:4096].count(",")
        semi = sample[:4096].count(";")
        tab = sample[:4096].count("\t")
        return max({",": comma, ";": semi, "\t": tab}, key=lambda k: {",": comma, ";": semi, "\t": tab}[k])


def parse_table(content: bytes, filename: str = "") -> tuple[list[str], list[dict]]:
    """Parse CSV/TSV, JSON arrays and XLSX workbooks into a common row shape."""
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".xlsx":
        from openpyxl import load_workbook

        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        try:
            sheet = wb.active
            iterator = sheet.iter_rows(values_only=True)
            header = next(iterator, ())
            columns = [str(value).strip() if value is not None else "" for value in header]
            rows = []
            for values in iterator:
                rows.append({
                    columns[index]: ("" if value is None else str(value).strip())
                    for index, value in enumerate(values) if index < len(columns) and columns[index]
                })
            return columns, rows
        finally:
            wb.close()
    if suffix == ".json":
        payload = json.loads(content.decode("utf-8-sig"))
        if isinstance(payload, dict):
            payload = payload.get("items") or payload.get("rows") or payload.get("data") or [payload]
        if not isinstance(payload, list):
            raise ValueError("JSON import must be an array of objects or an object with items/rows/data")
        records = [item for item in payload if isinstance(item, dict)]
        columns = list(dict.fromkeys(key for item in records for key in item.keys()))
        rows = [{key: ("" if value is None else str(value).strip()) for key, value in item.items()} for item in records]
        return columns, rows
    text = content.decode("utf-8-sig", errors="replace")
    delimiter = sniff_delimiter(text)
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    columns = [c.strip() if c else "" for c in (reader.fieldnames or [])]
    rows = []
    for raw in reader:
        rows.append({(k or "").strip(): (v or "").strip() for k, v in raw.items() if k is not None})
    return columns, rows


def _find_column(columns: list[str], aliases: Iterable[str]) -> str | None:
    lookup = {c.lower().strip(): c for c in columns}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    for alias in aliases:
        for key, original in lookup.items():
            if alias in key:
                return original
    return None


def parse_sitemap(content: bytes) -> tuple[list[dict], str]:
    """Parse an XML sitemap or sitemap index. Returns entries and detected kind."""
    root = ET.fromstring(content)
    tag = root.tag.split("}")[-1].lower()
    namespace = root.tag.split("}")[0][1:] if "}" in root.tag else ""
    ns = {"s": namespace} if namespace else {}
    if tag == "sitemapindex":
        locs = [{"loc": (n.findtext("s:loc", default="", namespaces=ns) or "").strip()} for n in root.findall("s:sitemap", ns)]
        return locs, "sitemap_index"
    entries = []
    for node in root.findall("s:url", ns):
        entries.append({
            "loc": (node.findtext("s:loc", default="", namespaces=ns) or "").strip(),
            "lastmod": (node.findtext("s:lastmod", default="", namespaces=ns) or "").strip(),
            "changefreq": (node.findtext("s:changefreq", default="", namespaces=ns) or "").strip(),
            "priority": (node.findtext("s:priority", default="", namespaces=ns) or "").strip(),
        })
    return entries, "sitemap"


def upsert_urls(
    db: Session,
    project_id: int,
    urls: Iterable[str],
    source: str,
    data_kind: str = "imported",
    rules: dict | None = None,
    batch_size: int = 2000,
    extra: dict[str, Any] | None = None,
) -> tuple[int, int, list[str]]:
    """Insert or update URL inventory records in batches. Returns (accepted, rejected, errors)."""
    now = iso(utcnow())
    accepted = 0
    rejected = 0
    errors: list[str] = []
    extra = extra or {}
    buffer: dict[str, dict] = {}
    seen_hashes: set[str] = set()

    def flush() -> None:
        nonlocal buffer, seen_hashes
        if not buffer:
            return
        hashes = list(buffer.keys())
        existing: dict[str, UrlRecord] = {}
        for i in range(0, len(hashes), 500):
            chunk = hashes[i:i + 500]
            for rec in db.scalars(select(UrlRecord).where(
                UrlRecord.project_id == project_id, UrlRecord.url_hash.in_(chunk)
            )):
                existing[rec.url_hash] = rec
        new_rows: list[dict] = []
        updates: list[dict] = []
        for h, payload in buffer.items():
            rec = existing.get(h)
            if rec is None:
                new_rows.append({"project_id": project_id, "url_hash": h, **payload})
            else:
                changes: dict[str, Any] = {"id": rec.id, "last_seen": now}
                for key, value in payload.items():
                    if key == "sources":
                        if source not in (rec.sources or []):
                            changes["sources"] = list(rec.sources or []) + [source]
                        continue
                    if key in {"title", "clicks", "impressions", "sessions", "conversions", "revenue", "referring_domains", "importance", "page_type"} and value not in (None, "", 0, "unknown"):
                        changes[key] = value
                    elif key == "in_sitemap" and value:
                        changes["in_sitemap"] = True
            if rec is not None:
                updates.append(changes)
        # Core batches avoid per-row ORM bookkeeping for large imports.
        if new_rows:
            db.execute(insert(UrlRecord), new_rows)
        if updates:
            db.bulk_update_mappings(UrlRecord, updates)
        db.flush()
        buffer = {}
        seen_hashes = set()

    for raw in urls:
        url = (raw or "").strip() if isinstance(raw, str) else ""
        if not url or len(url) > 4096:
            rejected += 1
            if len(errors) < 20:
                errors.append(f"Rejected empty or oversized URL: {str(raw)[:120]}")
            continue
        try:
            # Imports persist URLs; they do not fetch them. Literal/private hosts
            # are still rejected here, while DNS answers are checked immediately
            # before any outbound request by the crawler's fetch path.
            validate_target_url(url, resolve_dns=False)
            norm = normalize_url(url, rules)
            h = url_hash(url, rules)
        except ValueError as exc:
            rejected += 1
            if len(errors) < 20:
                errors.append(f"Rejected {str(url)[:120]}: {exc}")
            continue
        if h in seen_hashes or h in buffer:
            continue
        seen_hashes.add(h)
        payload = {
            "url": url,
            "normalized_url": norm,
            "hostname": hostname_of(url),
            "path": path_of(url),
            "sources": [source],
            "data_kind": data_kind,
            "first_seen": now,
            "last_seen": now,
            "page_type": classify_page_type(url, extra.get("title", "")),
            "in_sitemap": bool(extra.get("in_sitemap")),
            "clicks": float(extra.get("clicks") or 0),
            "impressions": float(extra.get("impressions") or 0),
            "sessions": float(extra.get("sessions") or 0),
            "conversions": float(extra.get("conversions") or 0),
            "revenue": float(extra.get("revenue") or 0),
            "referring_domains": int(extra.get("referring_domains") or 0),
        }
        if extra.get("title"):
            payload["title"] = str(extra["title"])
        buffer[h] = payload
        accepted += 1
        if len(buffer) >= batch_size:
            flush()
    flush()
    return accepted, rejected, errors


def store_sitemap_entries(db: Session, project_id: int, entries: list[dict], source: str) -> int:
    count = 0
    for entry in entries:
        loc = (entry.get("loc") or "").strip()
        if not loc:
            continue
        db.add(SitemapEntry(
            project_id=project_id, source=source, loc=loc,
            lastmod=str(entry.get("lastmod") or ""),
            changefreq=str(entry.get("changefreq") or ""),
            priority=str(entry.get("priority") or ""),
            observed_at=iso(utcnow()),
        ))
        count += 1
    db.flush()
    return count


def to_float(value: Any) -> float:
    if value is None:
        return 0.0
    text = str(value).strip().replace(",", "").replace("%", "").replace("$", "")
    if not text or text.lower() in {"n/a", "-", "none", "null"}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
