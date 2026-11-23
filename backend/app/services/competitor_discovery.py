"""Derive competitor and keyword evidence from a public crawl only.

No search-volume, ranking, traffic or private competitor data is invented.
Competitors are hostnames that the crawled pages link to; keyword candidates
are observed page titles, H1s and outbound-link anchor text. Every generated
row carries evidence pointing back to the crawl that produced it.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.url_utils import hostname_of
from app.models.enterprise import Competitor, KeywordGap
from app.models.inventory import LinkEdge, UrlRecord
from app.models.keywords import Keyword, KeywordMapping
from app.models.projects import Project
from app.services.keywords import classify_intent, keyword_tokens, normalize_keyword

# Platforms and utilities are not SEO competitors just because a site links to them.
IGNORED_HOSTS = {
    "facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com",
    "youtube.com", "pinterest.com", "tiktok.com", "reddit.com", "whatsapp.com",
    "google.com", "gstatic.com", "googleapis.com", "googletagmanager.com",
    "google-analytics.com", "doubleclick.net", "w3.org", "schema.org",
    "cloudflare.com", "jsdelivr.net", "cdnjs.cloudflare.com", "bootstrapcdn.com",
    "fontawesome.com", "fonts.googleapis.com", "fonts.gstatic.com", "sentry.io",
    "hotjar.com", "mailchimp.com", "wordpress.org", "wp.com", "gravatar.com",
}

GENERIC_ANCHORS = {
    "click here", "read more", "learn more", "here", "home", "contact", "about",
    "privacy policy", "terms and conditions", "terms of service", "cookie policy",
    "login", "log in", "sign up", "subscribe", "download", "view all", "more",
}

SEPARATORS = re.compile(r"\s+[|–—-]\s+|\s*:\s*")


def _clean_phrase(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if len(text) < 4 or len(text) > 90 or len(text.split()) > 9:
        return ""
    if normalize_keyword(text) in GENERIC_ANCHORS:
        return ""
    if text.lower().startswith(("http://", "https://", "www.")):
        return ""
    return text


def _first_or_create(db: Session, model, query, factory):
    row = db.scalars(query.limit(1)).first()
    if row is not None:
        return row, False
    row = factory()
    db.add(row)
    db.flush()
    return row, True


def _page_tokens(record: UrlRecord) -> set[str]:
    text = " ".join([
        record.title or "",
        " ".join(str(v) for v in (record.h1 or [])),
        record.path or "",
    ])
    return keyword_tokens(normalize_keyword(text))


def derive_public_evidence(db: Session, project_id: int, crawl_id: int) -> dict[str, int]:
    """Populate keyword, mapping, competitor and gap tables from crawl evidence."""
    records = db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id, UrlRecord.crawled.is_(True))
    ).all()
    project = db.get(Project, project_id)
    target_host = hostname_of(project.domain) if project else ""

    candidates: dict[str, dict[str, Any]] = {}
    best_by_url: dict[int, tuple[str, str]] = {}

    for record in records:
        parts: list[tuple[str, str]] = []
        title = (record.title or "").strip()
        if title:
            parts.append((SEPARATORS.split(title)[0].strip(), "public_page_title"))
        for h1 in record.h1 or []:
            parts.append((str(h1), "public_h1"))
        if not parts and record.path:
            parts.append((record.path.strip("/").replace("-", " ").replace("/", " "), "public_url_path"))

        for phrase, source in parts:
            clean = _clean_phrase(phrase)
            key = normalize_keyword(clean)
            if not key:
                continue
            if record.id not in best_by_url and source in {"public_h1", "public_page_title", "public_url_path"}:
                best_by_url[record.id] = (clean, source)
            item = candidates.setdefault(key, {
                "phrase": clean, "source": source, "evidence": [], "count": 0,
            })
            item["count"] += 1
            if len(item["evidence"]) < 5:
                item["evidence"].append({
                    "url": record.url, "field": source, "crawl_id": crawl_id,
                })

    # Bound the derived dataset so a very large crawl stays predictable.
    ordered = sorted(candidates.items(), key=lambda item: (-item[1]["count"], item[0]))[:300]
    keyword_count = 0
    for key, item in ordered:
        intent, intent_reason = classify_intent(item["phrase"])
        _, created = _first_or_create(
            db, Keyword,
            select(Keyword).where(Keyword.project_id == project_id, Keyword.normalized == key),
            lambda: Keyword(
                project_id=project_id, keyword=item["phrase"], normalized=key,
                intent=intent, intent_source="rule", topic=item["phrase"],
                source="public_page_evidence", confidence="derived",
                evidence={
                    "method": "public_page_evidence", "crawl_id": crawl_id,
                    "observations": item["evidence"], "intent_reason": intent_reason,
                    "volume_and_difficulty": "not supplied",
                },
            ),
        )
        keyword_count += int(created)

    mapping_count = 0
    for record_id, (phrase, source) in best_by_url.items():
        record = next((r for r in records if r.id == record_id), None)
        if record is None:
            continue
        _, created = _first_or_create(
            db, KeywordMapping,
            select(KeywordMapping).where(
                KeywordMapping.project_id == project_id,
                KeywordMapping.url == record.url,
                KeywordMapping.primary_keyword == phrase,
            ),
            lambda: KeywordMapping(
                project_id=project_id, url=record.url, url_id=record.id,
                primary_keyword=phrase, intent=classify_intent(phrase)[0],
                page_type=record.page_type or "unknown", confidence=0.65,
                reasoning=f"Derived from observed {source}; no search volume or ranking claim.",
                recommended_changes=["Validate against business priorities and any supplied keyword data."],
                source="public_page_evidence",
            ),
        )
        mapping_count += int(created)

    edges = db.scalars(
        select(LinkEdge).where(
            LinkEdge.project_id == project_id,
            LinkEdge.crawl_id == crawl_id,
            LinkEdge.link_type == "external",
        )
    ).all()

    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"links": [], "anchors": defaultdict(list)})
    for edge in edges:
        host = hostname_of(edge.target_url)
        if not host or host == target_host or any(host == bad or host.endswith("." + bad) for bad in IGNORED_HOSTS):
            continue
        bucket = grouped[host]
        bucket["links"].append(edge)
        anchor = _clean_phrase(edge.anchor)
        if anchor:
            bucket["anchors"][normalize_keyword(anchor)].append(anchor)

    competitor_count = 0
    gap_count = 0
    for host, bucket in sorted(grouped.items(), key=lambda item: (-len(item[1]["links"]), item[0]))[:10]:
        links = bucket["links"]
        sample_links = [{"source": e.source_url, "target": e.target_url, "anchor": e.anchor} for e in links[:8]]
        competitor, created = _first_or_create(
            db, Competitor,
            select(Competitor).where(Competitor.project_id == project_id, Competitor.domain == host),
            lambda: Competitor(
                project_id=project_id, domain=host, name=host,
                notes=f"Discovered from {len(links)} outbound links observed in public crawl {crawl_id}.",
            ),
        )
        competitor_count += int(created)

        for key, anchors in list(bucket["anchors"].items())[:6]:
            phrase = anchors[0]
            tokens = keyword_tokens(key)
            best_url = ""
            best_score = 0.0
            for record in records:
                score = len(tokens & _page_tokens(record)) / max(1, len(tokens | _page_tokens(record)))
                if score > best_score:
                    best_score, best_url = score, record.url
            if best_score < 0.2:
                best_url = ""

            keyword, created_keyword = _first_or_create(
                db, Keyword,
                select(Keyword).where(Keyword.project_id == project_id, Keyword.normalized == key),
                lambda: Keyword(
                    project_id=project_id, keyword=phrase, normalized=key,
                    intent=classify_intent(phrase)[0], intent_source="rule", topic=phrase,
                    source="competitor_public_anchor", confidence="derived",
                    evidence={
                        "method": "outbound_link_anchor", "crawl_id": crawl_id,
                        "competitor_domain": host, "link_count": len(anchors),
                        "observed_links": sample_links[:3], "volume_and_difficulty": "not supplied",
                    },
                ),
            )
            # A phrase can appear in both on-page fields and outbound anchors.
            # Keep one keyword row, but record both observations as evidence.
            keyword_evidence = dict(keyword.evidence or {})
            if keyword_evidence.get("method") == "public_page_evidence":
                keyword_evidence["method"] = "public_page_and_outbound_link"
            anchors_seen = list(keyword_evidence.get("outbound_anchor_evidence") or [])
            if not any(item.get("competitor_domain") == host for item in anchors_seen):
                anchors_seen.append({
                    "crawl_id": crawl_id, "competitor_domain": host,
                    "anchor_observations": len(anchors), "observed_links": sample_links[:3],
                })
            keyword_evidence["outbound_anchor_evidence"] = anchors_seen
            keyword.evidence = keyword_evidence
            keyword_count += int(created_keyword)

            evidence = {
                "method": "outbound_links_in_public_crawl", "crawl_id": crawl_id,
                "competitor_domain": host, "link_count": len(links),
                "anchor_observations": len(anchors), "observed_links": sample_links[:3],
                "topic_overlap_score": round(best_score, 2),
            }
            _, created_gap = _first_or_create(
                db, KeywordGap,
                select(KeywordGap).where(
                    KeywordGap.project_id == project_id,
                    KeywordGap.competitor_id == competitor.id,
                    KeywordGap.keyword == key,
                    KeywordGap.gap_type == "competitor_topic_evidence",
                ),
                lambda: KeywordGap(
                    project_id=project_id, competitor_id=competitor.id, keyword=key,
                    intent=classify_intent(phrase)[0], competitor_url=links[0].target_url,
                    our_url=best_url,
                    gap_type="competitor_topic_evidence",
                    priority="P2", evidence=evidence,
                    recommendation=(
                        "Compare this externally linked topic with our public pages. "
                        "Evidence is an observed link anchor only; no volume, rank or traffic is claimed."
                    ),
                ),
            )
            gap_count += int(created_gap)

    db.commit()
    return {
        "competitors": competitor_count,
        "derived_keywords": keyword_count,
        "keyword_gaps": gap_count,
        "derived_mappings": mapping_count,
    }
