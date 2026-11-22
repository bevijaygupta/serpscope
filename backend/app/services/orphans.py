"""Orphan-page reconciliation across sitemap, crawl, GSC, analytics and CMS sources."""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import normalize_url
from app.models.analysis import OrphanRecord
from app.models.inventory import LinkEdge, SitemapEntry, UrlRecord
from app.services.priority import calculate_priority, orphan_components


def refresh_link_counts(db: Session, project_id: int) -> dict[str, int]:
    """Recalculate inlink/outlink counts from observed link edges."""
    inlinks: dict[str, int] = defaultdict(int)
    outlinks_internal: dict[str, int] = defaultdict(int)
    outlinks_external: dict[str, int] = defaultdict(int)
    broken: dict[str, int] = defaultdict(int)
    for edge in db.scalars(select(LinkEdge).where(LinkEdge.project_id == project_id)):
        target = normalize_url(edge.target_url)
        source = normalize_url(edge.source_url)
        if edge.link_type == "internal":
            inlinks[target] += 1
            outlinks_internal[source] += 1
        else:
            outlinks_external[source] += 1
        if edge.is_broken:
            broken[target] += 1
    updated = 0
    for rec in db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id)):
        key = normalize_url(rec.url)
        rec.internal_inlinks = inlinks.get(key, 0)
        rec.internal_outlinks = outlinks_internal.get(key, 0)
        rec.external_links = outlinks_external.get(key, 0)
        updated += 1
    # Mark broken link edges where the target is known and returned an error
    statuses = {normalize_url(r.url): r.http_status for r in db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id)
    )}
    for edge in db.scalars(select(LinkEdge).where(LinkEdge.project_id == project_id)):
        status = statuses.get(normalize_url(edge.target_url))
        if status is not None and status >= 400:
            edge.is_broken = True
    db.commit()
    return {"records_updated": updated, "internal_inlinks": sum(inlinks.values()), "broken_targets": len(broken)}


def detect_orphans(db: Session, project_id: int, config: dict | None = None) -> dict[str, Any]:
    """Rebuild the orphan inventory using configurable rules."""
    cfg = {
        "excluded_patterns": [],
        "authoritative_sources": ["sitemap", "crawler", "cms"],
        "weights": {},
        "max_records": 200000,
    }
    cfg.update(config or {})
    refresh_link_counts(db, project_id)
    now = iso(utcnow())

    records = db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id).limit(cfg["max_records"])
    ).all()
    sitemap_urls = {
        normalize_url(e.loc) for e in db.scalars(
            select(SitemapEntry).where(SitemapEntry.project_id == project_id)
        )
    }
    for rec in records:
        if rec.in_sitemap:
            sitemap_urls.add(normalize_url(rec.url))

    inlink_map: dict[str, int] = defaultdict(int)
    for edge in db.scalars(select(LinkEdge).where(
        LinkEdge.project_id == project_id, LinkEdge.link_type == "internal"
    )):
        inlink_map[normalize_url(edge.target_url)] += 1

    all_urls: dict[str, dict] = {}
    for rec in records:
        key = normalize_url(rec.url)
        sources = list(rec.sources or [])
        item = all_urls.setdefault(key, {
            "url": rec.url, "sources": sources, "crawled": bool(rec.crawled),
            "indexable": rec.indexable, "clicks": 0.0, "impressions": 0.0,
            "sessions": 0.0, "conversions": 0.0, "revenue": 0.0,
            "referring_domains": 0, "importance": 0.0, "in_sitemap": False,
            "redirected": False, "canonicalised": False, "page_type": rec.page_type,
            "status": rec.http_status, "robots_allowed": rec.robots_allowed,
        })
        item["sources"] = sorted(set(item["sources"]) | set(sources))
        item["clicks"] = max(item["clicks"], rec.clicks or 0)
        item["impressions"] = max(item["impressions"], rec.impressions or 0)
        item["sessions"] = max(item["sessions"], rec.sessions or 0)
        item["conversions"] = max(item["conversions"], rec.conversions or 0)
        item["revenue"] = max(item["revenue"], rec.revenue or 0)
        item["referring_domains"] = max(item["referring_domains"], rec.referring_domains or 0)
        item["importance"] = max(item["importance"], rec.importance or 0)
        item["crawled"] = item["crawled"] or bool(rec.crawled)
        item["indexable"] = rec.indexable if rec.indexable is not None else item["indexable"]
        item["in_sitemap"] = item["in_sitemap"] or bool(rec.in_sitemap) or key in sitemap_urls
        item["redirected"] = item["redirected"] or bool(rec.redirected_to or (rec.redirect_chain and len(rec.redirect_chain) > 1))
        item["canonicalised"] = item["canonicalised"] or bool(rec.canonical and normalize_url(rec.canonical) != key)
        item["status"] = rec.http_status if rec.http_status is not None else item["status"]
        item["robots_allowed"] = rec.robots_allowed if rec.robots_allowed is not None else item["robots_allowed"]

    for loc in sitemap_urls:
        item = all_urls.setdefault(loc, {
            "url": loc, "sources": ["sitemap"], "crawled": False, "indexable": None,
            "clicks": 0, "impressions": 0, "sessions": 0, "conversions": 0, "revenue": 0,
            "referring_domains": 0, "importance": 0, "in_sitemap": True,
            "redirected": False, "canonicalised": False, "page_type": "unknown",
            "status": None, "robots_allowed": None,
        })
        item["in_sitemap"] = True

    from app.core.url_utils import classify_page_type
    db.query(OrphanRecord).filter(OrphanRecord.project_id == project_id).delete()
    counts: dict[str, int] = defaultdict(int)
    created = 0
    for key, item in all_urls.items():
        inlinks = inlink_map.get(key, 0)
        if inlinks > 0:
            continue
        sources = item["sources"]
        has_authoritative = any(
            s in sources or (s == "sitemap" and item["in_sitemap"])
            for s in cfg["authoritative_sources"]
        )
        has_performance = bool(item["clicks"] or item["impressions"] or item["sessions"])
        excluded = any(
            re.search(p, item["url"])
            for p in (cfg.get("excluded_patterns") or [])
        )
        is_error = item["status"] in (404, 410, 403)
        if excluded or is_error:
            classification = "Excluded or intentionally isolated URL"
        elif item["redirected"]:
            classification = "Redirected orphan"
        elif item["canonicalised"]:
            classification = "Canonicalised orphan"
        elif item["referring_domains"] > 0:
            classification = "Backlink-supported orphan"
        elif item["clicks"] > 0 or item["impressions"] > 0:
            classification = "Search-visible orphan"
        elif item["sessions"] > 0:
            classification = "Analytics-active orphan"
        elif item["in_sitemap"] and not item["crawled"]:
            classification = "Sitemap-only orphan"
        elif item["crawled"] and has_authoritative:
            classification = "Confirmed crawl orphan"
        elif has_performance and not item["crawled"]:
            classification = "Potential orphan"
        elif item["crawled"]:
            classification = "Confirmed crawl orphan" if has_authoritative else "Unverified URL"
        else:
            classification = "Unverified URL"

        confidence = "high" if item["crawled"] and item["in_sitemap"] else (
            "medium" if item["crawled"] or item["in_sitemap"] else "unverified"
        )
        if classification in {"Excluded or intentionally isolated URL", "Unverified URL"}:
            confidence = "unverified"
        components = orphan_components(
            clicks=item["clicks"], impressions=item["impressions"], sessions=item["sessions"],
            conversions=item["conversions"], revenue=item["revenue"],
            referring_domains=item["referring_domains"], importance=item["importance"],
            indexable=item["indexable"], inlinks=inlinks, page_type=item["page_type"],
        )
        scored = calculate_priority(
            components, confidence, cfg.get("weights"),
            context=f"Sources={','.join(sources) or 'none'}; classification={classification}",
        )
        causes = {
            "Confirmed crawl orphan": "No internal link discovered despite authoritative source and crawl",
            "Potential orphan": "Appears in performance/CMS data but was not discovered by the crawl",
            "Sitemap-only orphan": "In sitemap but not linked and not crawled",
            "Analytics-active orphan": "Receives sessions but has no discovered internal links",
            "Search-visible orphan": "Has organic visibility but no discovered internal links",
            "Backlink-supported orphan": "External links exist but internal discovery path is missing",
            "Redirected orphan": "URL redirects; source lists may need updating",
            "Canonicalised orphan": "Canonical points elsewhere; confirm intended target",
            "Excluded or intentionally isolated URL": "Excluded by config or deliberately non-indexable",
            "Unverified URL": "Insufficient evidence; do not treat as confirmed orphan",
        }
        actions = {
            "Confirmed crawl orphan": "Add contextual internal links from relevant authoritative pages",
            "Potential orphan": "Verify accessibility and crawl configuration before linking",
            "Sitemap-only orphan": "Check indexability and add internal links or remove obsolete sitemap entry",
            "Analytics-active orphan": "Protect with internal links from relevant hub pages",
            "Search-visible orphan": "Prioritise internal links from pages ranking for related topics",
            "Backlink-supported orphan": "Add internal links and update canonical/sitemap if needed",
            "Redirected orphan": "Update source lists to the redirect destination",
            "Canonicalised orphan": "Confirm canonical target and clean source lists",
            "Excluded or intentionally isolated URL": "No action unless business intent changed",
            "Unverified URL": "Manual verification required",
        }
        db.add(OrphanRecord(
            project_id=project_id, url=item["url"], normalized_url=key,
            classification=classification, sources=sources, internal_inlinks=inlinks,
            crawled=item["crawled"], indexable=item["indexable"],
            clicks=item["clicks"], impressions=item["impressions"], sessions=item["sessions"],
            conversions=item["conversions"], revenue=item["revenue"],
            referring_domains=item["referring_domains"], importance=item["importance"],
            priority=scored["priority"], priority_score=scored["score"],
            score_components=scored["components"], confidence=confidence,
            likely_cause=causes[classification], recommended_action=actions[classification],
            page_type=item["page_type"] or classify_page_type(item["url"]), observed_at=now,
        ))
        counts[classification] += 1
        created += 1
    db.commit()
    return {
        "detected_at": now, "total_urls_considered": len(all_urls),
        "orphan_urls": created, "by_classification": dict(counts),
        "method": "union_of_sources_minus_discovered_internal_inlinks",
    }
