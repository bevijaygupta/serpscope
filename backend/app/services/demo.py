"""Synthetic demonstration datasets with intentionally planted SEO issues.

All generated metrics are labelled `synthetic` / `simulated`. They are not real
client data and do not prove real-world performance.
"""
from __future__ import annotations

import hashlib
import json
import random
from collections import defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import hostname_of, normalize_url, path_of
from app.models.analysis import OrphanRecord
from app.models.auth import Organization, User
from app.models.inventory import LinkEdge, SitemapEntry, UrlRecord
from app.models.keywords import Keyword
from app.models.operations import (
    AnalyticsRecord,
    DemoScenario,
    Integration,
    Report,
    Workflow,
)
from app.models.projects import Project, ProjectMember
from app.services.priority import calculate_priority, orphan_components

SERVICE_SLUGS = [
    "vapt", "managed-security-services", "cloud-security", "incident-response",
    "cybersecurity-consulting", "penetration-testing", "soc-as-a-service", "compliance-audit",
]
TOPICS = [
    "password-security", "phishing-awareness", "zero-trust", "ransomware-response",
    "cloud-misconfiguration", "vapt-checklist", "soc-operations", "incident-playbook",
    "data-encryption", "access-control", "security-logging", "supply-chain-risk",
]
CITIES = ["singapore", "japan", "australia", "germany", "india", "united-kingdom", "canada"]
BRANDS = ["Acme Cyber", "Northstar Security", "Sentinel Labs"]
KEYWORD_MODIFIERS = [
    "services", "provider", "pricing", "best", "guide", "checklist", "near me",
    "singapore", "comparison", "review", "what is", "how to", "tools", "company",
]


def _hash(norm: str) -> str:
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _base_record(project_id: int, url: str, now: str, **extra) -> dict:
    norm = normalize_url(url)
    page_type = extra.get("page_type", "unknown")
    record = {
        "project_id": project_id,
        "url": url,
        "url_hash": _hash(norm),
        "normalized_url": norm,
        "hostname": hostname_of(url),
        "path": path_of(url),
        "sources": extra.get("sources", ["synthetic_sitemap"]),
        "data_kind": "synthetic",
        "first_seen": now,
        "last_seen": now,
        "crawled": True,
        "crawled_at": now,
        "http_status": extra.get("http_status", 200),
        "content_type": extra.get("content_type", "text/html; charset=utf-8"),
        "response_time_ms": extra.get("response_time_ms", 250),
        "content_size": extra.get("content_size", 65000),
        "title": extra.get("title", f"{page_type.title()} {url.split('/')[-1] or 'Home'} | Example"),
        "meta_description": extra.get("meta_description", "Synthetic demonstration description for testing detection rules."),
        "h1": extra.get("h1", [f"{page_type.title()} overview"]),
        "h2": extra.get("h2", ["What it is", "How it works", "FAQ"]),
        "canonical": extra.get("canonical", norm),
        "meta_robots": extra.get("meta_robots", "index, follow"),
        "x_robots_tag": "",
        "robots_allowed": extra.get("robots_allowed", True),
        "indexable": extra.get("indexable", True),
        "word_count": extra.get("word_count", 900),
        "internal_inlinks": extra.get("internal_inlinks", 0),
        "internal_outlinks": 5,
        "external_links": 2,
        "image_count": 4,
        "images_missing_alt": extra.get("images_missing_alt", 0),
        "schema_types": extra.get("schema_types", ["Organization"]),
        "og": {},
        "hreflang": extra.get("hreflang", {}),
        "pagination": {},
        "redirect_chain": extra.get("redirect_chain", []),
        "redirected_to": extra.get("redirected_to", ""),
        "crawl_depth": extra.get("crawl_depth", 2),
        "javascript_rendered": False,
        "page_type": page_type,
        "template": extra.get("template", page_type),
        "importance": extra.get("importance", 0.3),
        "in_sitemap": extra.get("in_sitemap", True),
        "is_orphan": extra.get("is_orphan", False),
        "has_traffic": extra.get("has_traffic", False),
        "clicks": extra.get("clicks", 0.0),
        "impressions": extra.get("impressions", 0.0),
        "sessions": extra.get("sessions", 0.0),
        "conversions": extra.get("conversions", 0.0),
        "revenue": extra.get("revenue", 0.0),
        "referring_domains": extra.get("referring_domains", 0),
        "notes": "SYNTHETIC DEMONSTRATION RECORD",
    }
    return record


def _url_for(i: int) -> tuple[str, str]:
    """Deterministic synthetic URL and page type."""
    bucket = i % 20
    if bucket == 0:
        return ("https://demo.example.com/" if i == 0 else f"https://demo.example.com/home-{i}/"), "homepage"
    if bucket in (1, 2, 3, 4):
        return f"https://demo.example.com/services/{SERVICE_SLUGS[i % len(SERVICE_SLUGS)]}-{i // 20}/", "service"
    if bucket in (5, 6, 7, 8, 9):
        return f"https://demo.example.com/insights/{TOPICS[i % len(TOPICS)]}-{i}/", "article"
    if bucket in (10, 11, 12):
        return f"https://demo.example.com/products/category-{i % 12}/product-{i}/", "product"
    if bucket in (13, 14):
        return f"https://demo.example.com/category/category-{i % 12}/page-{i}/", "category"
    if bucket == 15:
        return f"https://demo.example.com/locations/{CITIES[i % len(CITIES)]}-{i}/", "location"
    if bucket == 16:
        return f"https://demo.example.com/sg/services/{SERVICE_SLUGS[i % len(SERVICE_SLUGS)]}-{i}/", "service"
    if bucket == 17:
        return f"https://demo.example.com/insights/{TOPICS[i % len(TOPICS)]}-{i}/?utm_source=newsletter", "article"
    if bucket == 18:
        return f"https://demo.example.com/support/faq-{i}/", "faq"
    return f"https://demo.example.com/blog/{TOPICS[i % len(TOPICS)]}-{i}/", "article"


def _planted_issue(i: int) -> dict:
    """Deterministic planted issue pattern so findings are reproducible."""
    out: dict[str, Any] = {}
    if i % 137 == 17:
        out.update(http_status=404, title="Missing page", indexable=False, clicks=40 + (i % 300),
                   impressions=800 + i % 5000, sessions=20 + i % 100,
                   revenue=1800 + (i % 9000), conversions=2 + i % 20,
                   referring_domains=3 + i % 40, planted="high_value_404")
    elif i % 151 == 31:
        out.update(http_status=404, planted="ordinary_404")
    elif i % 173 == 43:
        out.update(http_status=301, redirect_chain=[
            f"https://demo.example.com/old/{i}/",
            f"https://demo.example.com/temp/{i}/",
            f"https://demo.example.com/new/{i}/",
        ], redirected_to=f"https://demo.example.com/new/{i}/", planted="redirect_chain")
    elif i % 181 == 59:
        out.update(http_status=500, planted="server_error")
    elif i % 191 == 71:
        out.update(canonical=f"https://demo.example.com/wrong-canonical/{i}/", planted="canonical_conflict")
    elif i % 211 == 83:
        out.update(meta_robots="noindex, follow", in_sitemap=True, planted="noindex_in_sitemap")
    elif i % 223 == 97:
        out.update(title="Duplicate Synthetic Title", meta_description="Duplicate synthetic description used for testing.",
                   planted="duplicate_metadata")
    elif i % 229 == 101:
        out.update(title="", h1=[], word_count=45, images_missing_alt=3, planted="thin_content")
    elif i % 233 == 109:
        out.update(response_time_ms=5200, content_size=3_100_000, planted="slow_oversized")
    elif i % 239 == 113:
        out.update(schema_types=["invalid-json-ld"], planted="invalid_schema")
    elif i % 241 == 127:
        out.update(hreflang={"en-SG": f"https://demo.example.com/sg/page-{i}/",
                             "x-default": f"https://demo.example.com/page-{i}/"}, planted="hreflang_partial")
    elif i % 251 == 131:
        out.update(http_status=410, indexable=False, planted="intentional_410")
    return out


def generate_demo(
    db: Session,
    size: int = 1000,
    keyword_count: int = 1000,
    label: str | None = None,
    include_scenarios: bool = True,
) -> dict[str, Any]:
    """Generate a synthetic project. Returns counts and planted-issue inventory."""
    size = max(100, int(size))
    now = iso(utcnow())
    rng = random.Random(20261122)
    from sqlalchemy import select

    org = db.scalar(select(Organization).where(Organization.slug == "demo-organisation"))
    if org is None:
        org = Organization(
            name="Demo Organisation", slug="demo-organisation", plan="demo", is_demo=True,
        )
        db.add(org)
        db.flush()
    project = Project(
        organization_id=org.id,
        name=label or f"Demo — {size:,} URLs",
        domain="demo.example.com", status="active", is_demo=True,
        description="SYNTHETIC demonstration dataset. Metrics are simulated for rule testing only.",
        settings={
            "data_kind": "synthetic",
            "size": size,
            "planted_issues": "see docs/DEMO_GUIDE.md and project notes",
            "disclaimer": "Not real client data. No real crawl or API response was used.",
        },
    )
    db.add(project)
    db.flush()

    records: list[dict] = []
    sitemap: list[dict] = []
    edges: list[dict] = []
    planted_counts: dict[str, int] = defaultdict(int)
    orphan_targets: list[str] = []
    inlinks: dict[str, int] = defaultdict(int)
    for i in range(size):
        url, page_type = _url_for(i)
        issue = _planted_issue(i)
        if "planted" in issue:
            planted_counts[issue["planted"]] += 1
        clicks = float(issue.get("clicks", rng.randint(0, 120) if i % 7 == 0 else 0))
        impressions = float(issue.get("impressions", clicks * 12 if clicks else 0))
        sessions = float(issue.get("sessions", clicks * 0.6 if clicks else 0))
        extra = {
            "page_type": page_type,
            "template": page_type,
            "importance": 0.85 if page_type in {"service", "product"} else 0.4,
            "clicks": clicks, "impressions": impressions, "sessions": sessions,
            "referring_domains": issue.get("referring_domains", rng.randint(0, 12) if i % 11 == 0 else 0),
            "crawl_depth": 1 if page_type in {"homepage", "service"} else rng.randint(2, 8),
            "internal_inlinks": inlinks.get(normalize_url(url), 0),
        }
        extra.update({k: v for k, v in issue.items() if k != "planted"})
        if i % 53 == 7:
            extra["is_orphan"] = True
            extra["internal_inlinks"] = 0
        records.append(_base_record(project.id, url, now, **extra))
        if i % 7 != 3:  # some URLs deliberately omitted from sitemap
            sitemap.append({
                "project_id": project.id, "source": "synthetic-sitemap.xml",
                "loc": url, "lastmod": "2026-11-01", "changefreq": "weekly",
                "priority": "0.8", "observed_at": now,
            })
        if i % 53 == 7:
            orphan_targets.append(url)
        else:
            target_index = min(size - 1, i + rng.randint(1, 4))
            target_url, _ = _url_for(target_index)
            inlinks[normalize_url(target_url)] += 1
            edges.append({
                "project_id": project.id, "source_url": url, "target_url": target_url,
                "anchor": TOPICS[i % len(TOPICS)].replace("-", " "),
                "link_type": "internal", "is_broken": False, "observed_at": now,
            })

    for chunk_start in range(0, len(records), 5000):
        db.bulk_insert_mappings(UrlRecord, records[chunk_start:chunk_start + 5000])
    for chunk_start in range(0, len(sitemap), 5000):
        db.bulk_insert_mappings(SitemapEntry, sitemap[chunk_start:chunk_start + 5000])
    for chunk_start in range(0, len(edges), 5000):
        db.bulk_insert_mappings(LinkEdge, edges[chunk_start:chunk_start + 5000])
    db.flush()

    # Keywords with clearly synthetic, documented metrics
    keywords_list = []
    for i in range(min(keyword_count, 50000)):
        root = SERVICE_SLUGS[i % len(SERVICE_SLUGS)] if i % 3 else TOPICS[i % len(TOPICS)]
        modifier = KEYWORD_MODIFIERS[i % len(KEYWORD_MODIFIERS)]
        keyword = f"{root} {modifier}"
        if i % 17 == 0:
            keyword += " singapore"
        keywords_list.append({
            "project_id": project.id, "keyword": keyword, "normalized": " ".join(sorted(keyword.split())),
            "intent": "unclassified", "intent_source": "pending", "topic": root.replace("-", " ").title(),
            "parent_topic": "Cybersecurity", "country": "SG" if "singapore" in keyword else "",
            "language": "en", "volume": (i * 37) % 5000, "difficulty": round((i % 100) / 2, 1),
            "cpc": round((i % 50) / 4, 2), "competition": "medium" if i % 3 else "low",
            "serp_features": [], "source": "synthetic_demo", "collected_at": now,
            "confidence": "synthetic", "evidence": {"data_kind": "synthetic", "note": "Simulated metric for rule testing only"},
        })
    for chunk_start in range(0, len(keywords_list), 5000):
        db.bulk_insert_mappings(Keyword, keywords_list[chunk_start:chunk_start + 5000])

    # Analytics samples (GSC-style and GA4-style)
    analytics = []
    for i in range(0, size, max(1, size // min(2000, size))):
        url, _ = _url_for(i)
        clicks = float(rng.randint(0, 200))
        analytics.append({
            "project_id": project.id, "source": "synthetic_gsc" if i % 2 else "synthetic_ga4",
            "data_kind": "synthetic", "dimension_type": "page", "dimension": url,
            "period_start": "2026-11-02", "period_end": "2026-11-08",
            "clicks": clicks, "impressions": clicks * rng.randint(5, 40),
            "ctr": 0.03, "position": round(rng.uniform(3, 50), 1),
            "sessions": clicks * 0.7, "conversions": rng.randint(0, 5),
            "revenue": rng.randint(0, 1500), "device": "desktop", "country": "SG",
            "collected_at": now,
        })
        if i < 200:
            analytics.append({
                "project_id": project.id, "source": "synthetic_gsc", "data_kind": "synthetic",
                "dimension_type": "query", "dimension": f"{SERVICE_SLUGS[i % len(SERVICE_SLUGS)]} {KEYWORD_MODIFIERS[i % len(KEYWORD_MODIFIERS)]}",
                "period_start": "2026-11-02", "period_end": "2026-11-08",
                "clicks": rng.randint(0, 60), "impressions": rng.randint(100, 4000),
                "ctr": 0.02, "position": round(rng.uniform(2, 40), 1),
                "collected_at": now,
            })
    db.bulk_insert_mappings(AnalyticsRecord, analytics)

    # Singapore cybersecurity scenario content
    from app.services.domains import build_international_plan

    build_international_plan(db, project.id, {
        "market": "Singapore", "language": "en-SG", "url_structure": "subdirectory",
        "seed_keywords": ["vapt services singapore", "managed security services singapore",
                          "cloud security provider singapore", "incident response singapore",
                          "cybersecurity consulting sg", "vapt cost", "what is vapt"],
        "competitors": ["competitor-a.example", "competitor-b.example"],
    })

    # Local / e-commerce / migration / AI samples
    from app.models.enterprise import Location, Product, MigrationMapping, AiVisibilityRecord

    db.bulk_insert_mappings(Location, [{
        "project_id": project.id, "name": f"{BRANDS[i % 3]} {CITIES[i % len(CITIES)]}",
        "brand": BRANDS[i % 3], "address": f"{100 + i} Demo Street",
        "city": CITIES[i % len(CITIES)], "country": "Singapore" if i % 3 == 0 else "Australia",
        "phone": f"+65 6{i % 10}00 {1000 + i}", "website": "https://demo.example.com",
        "category": "Cybersecurity service", "status": "active",
        "landing_page": f"https://demo.example.com/locations/{CITIES[i % len(CITIES)]}/",
        "local_keywords": [f"vapt {CITIES[i % len(CITIES)]}"], "issues": [], "data_kind": "synthetic",
    } for i in range(min(500, max(20, size // 4)))])
    db.bulk_insert_mappings(Product, [{
        "project_id": project.id, "url": f"https://demo.example.com/products/c-{i % 12}/p-{i}/",
        "product_id": f"DEMO-{i}", "title": f"Synthetic Security Product {i}",
        "description": "Synthetic product description for testing duplicate detection." if i % 13 == 0 else f"Synthetic product {i} details and specifications.",
        "category": f"category-{i % 12}", "price": f"{(i % 90 + 10) * 10}.00",
        "availability": "out of stock" if i % 29 == 0 else "in stock",
        "identifier": "" if i % 9 == 0 else f"SKU-{i}",
        "canonical": "" if i % 11 == 0 else f"https://demo.example.com/products/c-{i % 12}/p-{i}/",
        "schema_types": [] if i % 5 == 0 else ["Product", "BreadcrumbList"],
        "diagnostics": [], "status": "active", "priority": "P2", "data_kind": "synthetic",
    } for i in range(min(600, max(50, size // 5)))])
    db.bulk_insert_mappings(MigrationMapping, [{
        "project_id": project.id,
        "old_url": f"https://old-demo.example.com/services/{SERVICE_SLUGS[i % len(SERVICE_SLUGS)]}/",
        "new_url": _url_for(i % size)[0],
        "redirect_status": "not_checked", "clicks": rng.randint(0, 300),
        "revenue": rng.randint(0, 2000), "risk": "P2", "findings": [],
    } for i in range(min(250, size))])
    db.bulk_insert_mappings(AiVisibilityRecord, [{
        "project_id": project.id, "question": f"What is {SERVICE_SLUGS[i % len(SERVICE_SLUGS)].replace('-', ' ')}?",
        "answer_engine": "manual-observation", "observed_at": now,
        "brand_mentioned": bool(i % 3 == 0), "competitor_mentioned": ["competitor-a.example"] if i % 4 == 0 else [],
        "source": "synthetic_manual_observation", "data_kind": "synthetic",
    } for i in range(30)])

    # Example workflows and integrations (never pretend credentials exist)
    db.add_all([
        Workflow(project_id=project.id, name="Weekly technical audit", trigger="scheduled",
                 schedule="weekly", steps=[
                     {"type": "detect_issues", "config": {}},
                     {"type": "detect_orphans", "config": {}},
                     {"type": "generate_report", "config": {}},
                 ], enabled=True),
        Workflow(project_id=project.id, name="404 monitoring", trigger="manual", schedule="",
                 steps=[{"type": "detect_issues", "config": {}}, {"type": "generate_report", "config": {}}],
                 enabled=True),
        Workflow(project_id=project.id, name="Keyword mapping", trigger="manual", schedule="",
                 steps=[{"type": "cluster_keywords", "config": {"method": "normalized"}},
                        {"type": "map_keywords", "config": {}}], enabled=True),
    ])
    db.add_all([
        Integration(project_id=project.id, provider="google_search_console",
                    display_name="Google Search Console", mode="csv_import", status="not_configured",
                    notes="Import GSC exports as CSV. Official API requires OAuth credentials."),
        Integration(project_id=project.id, provider="google_analytics_4",
                    display_name="Google Analytics 4", mode="csv_import", status="not_configured",
                    notes="Import GA4 exports as CSV. No credentials are stored in demo mode."),
        Integration(project_id=project.id, provider="screaming_frog",
                    display_name="Screaming Frog export", mode="csv_import", status="not_configured",
                    notes="Upload a crawling export to enrich the shared URL inventory."),
    ])
    if include_scenarios:
        from app.services.scenarios import seed_scenarios

        seed_scenarios(db)
    db.commit()

    return {
        "project_id": project.id, "organization_id": org.id, "size": size,
        "urls": len(records), "sitemap_entries": len(sitemap), "link_edges": len(edges),
        "keywords": len(keywords_list), "analytics_rows": len(analytics),
        "planted_issues": dict(planted_counts),
        "data_kind": "synthetic",
        "disclaimer": "All traffic, revenue and keyword metrics are simulated for rule testing only.",
    }
