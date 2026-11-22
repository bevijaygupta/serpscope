"""Domain-specific analysis services built on the shared data layer."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import classify_page_type, normalize_url
from app.models.enterprise import (
    AiReadinessItem,
    AiVisibilityRecord,
    Competitor,
    HreflangRecord,
    InternationalPlan,
    KeywordGap,
    Location,
    MigrationMapping,
    MigrationProject,
    Product,
)
from app.models.inventory import UrlRecord
from app.models.keywords import Keyword
from app.services.keywords import keyword_tokens, normalize_keyword
from app.services.priority import calculate_priority, issue_components


def competitor_analysis(db: Session, project_id: int, config: dict | None = None) -> dict[str, Any]:
    """Build keyword/content gap matrix from supplied competitor data only."""
    cfg = {"max_rows": 20000}
    cfg.update(config or {})
    competitors = db.scalars(select(Competitor).where(Competitor.project_id == project_id)).all()
    keywords = db.scalars(select(Keyword).where(Keyword.project_id == project_id).limit(cfg["max_rows"])).all()
    own = {normalize_keyword(k.keyword) for k in keywords if (k.source or "").lower() not in {"competitor", "competitor_import"}}
    competitor_kws = [k for k in keywords if (k.source or "").lower().startswith("competitor")]
    db.query(KeywordGap).filter(KeywordGap.project_id == project_id).delete()
    created = 0
    for kw in competitor_kws[:cfg["max_rows"]]:
        if normalize_keyword(kw.keyword) in own:
            gap_type = "intent_or_coverage_difference"
        else:
            gap_type = "keyword_gap"
        competitor = next((c for c in competitors if (kw.evidence or {}).get("competitor_domain") == c.domain), None)
        evidence = {
            "source": kw.source, "collected_at": kw.collected_at,
            "supplied_volume": kw.volume, "supplied_difficulty": kw.difficulty,
            "note": "No competitor private analytics or conversion data is available.",
        }
        db.add(KeywordGap(
            project_id=project_id, competitor_id=competitor.id if competitor else None,
            keyword=kw.keyword, intent=kw.intent,
            competitor_url=str((kw.evidence or {}).get("competitor_url", "")),
            gap_type=gap_type, priority="P1" if (kw.volume or 0) > 1000 else "P2",
            evidence=evidence,
            recommendation=("Create or improve a page matching this intent" if gap_type == "keyword_gap"
                            else "Compare SERP intent and page structure; improve existing page"),
        ))
        created += 1
    competitor_domains = [c.domain for c in competitors]
    return {
        "competitors": competitor_domains, "competitor_keywords": len(competitor_kws),
        "gaps_created": created,
        "note": "Analysis uses user-supplied exports only; no private competitor data is implied.",
    }


DEFAULT_SG_SERVICES = [
    "VAPT", "Managed security services", "Cloud security",
    "Incident response", "Cybersecurity consulting",
]


def build_international_plan(db: Session, project_id: int, config: dict | None = None) -> dict[str, Any]:
    """Build a transparent country/language plan from supplied inputs and observed data."""
    cfg = {
        "market": "Singapore", "language": "en", "url_structure": "subdirectory",
        "services": DEFAULT_SG_SERVICES, "seed_keywords": [], "competitors": [],
        "local_intent_modifiers": ["singapore", "sg", "near me", "provider", "services"],
    }
    cfg.update(config or {})
    market = str(cfg["market"])
    language = str(cfg["language"])
    slug = re.sub(r"[^a-z0-9]+", "-", market.lower()).strip("-") or "market"
    base = f"/{slug}/"
    service_pages = []
    for service in cfg["services"]:
        s = str(service)
        service_slug = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
        service_pages.append({
            "service": s, "url": f"{base}services/{service_slug}/",
            "intent": "commercial investigation/transactional",
            "primary_keyword": f"{s.lower()} {market.lower()}",
            "supporting_keywords": [f"{s.lower()} provider singapore", f"{s.lower()} services sg"],
        })
    support_content = []
    for i, seed in enumerate(cfg["seed_keywords"][:30]):
        seed_slug = re.sub(r"[^a-z0-9]+", "-", str(seed).lower()).strip("-")
        support_content.append({
            "title": str(seed), "url": f"{base}insights/{seed_slug}/",
            "intent": "informational",
            "links_to": [p["url"] for p in service_pages[:2]],
        })
    hreflang = [
        {"from": f"{base}services/", "hreflang": language, "to": f"{base}services/"},
        {"from": f"{base}services/", "hreflang": "x-default", "to": f"{base}services/"},
        {"from": f"{base}services/", "hreflang": "en-SG", "to": f"{base}services/"},
    ]
    internal_links = [
        {"source": f"{base}insights/", "target": p["url"], "anchor": p["service"]}
        for p in service_pages[:5]
    ] + [
        {"source": p["url"], "target": f"{base}services/", "anchor": "All cybersecurity services"}
        for p in service_pages[:5]
    ]
    roadmap = [
        {"phase": 1, "task": "Confirm market demand with imported GSC/keyword data", "owner": "SEO lead"},
        {"phase": 1, "task": "Decide URL structure and language targeting", "owner": "Technical SEO"},
        {"phase": 2, "task": "Build commercial service pages with local proof and contact paths", "owner": "Content + Design"},
        {"phase": 2, "task": "Publish supporting informational clusters with internal links to services", "owner": "Content"},
        {"phase": 3, "task": "Implement reciprocal hreflang and validate canonical/hreflang alignment", "owner": "Technical SEO"},
        {"phase": 3, "task": "Build local competitor comparison from supplied data only", "owner": "SEO analyst"},
    ]
    plan = InternationalPlan(
        project_id=project_id, market=market, language=language,
        url_structure=str(cfg["url_structure"]),
        search_intent="commercial + informational",
        service_pages=service_pages, supporting_content=support_content,
        keyword_clusters=[{
            "cluster": s, "keywords": [f"{s.lower()} singapore", f"{s.lower()} provider sg"],
            "source": "supplied seed/services, not invented volumes",
        } for s in cfg["services"]],
        hreflang_recommendations=hreflang,
        internal_link_architecture=internal_links, roadmap=roadmap,
        evidence={
            "data_kind": "plan_derived_from_supplied_inputs",
            "market": market, "language": language,
            "note": "Translation alone is not an international SEO strategy.",
        },
    )
    db.add(plan)
    db.flush()

    # Hreflang validation from crawl observations
    db.query(HreflangRecord).filter(HreflangRecord.project_id == project_id).delete()
    checked = 0
    for rec in db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id)):
        anns = rec.hreflang or {}
        if not anns:
            continue
        targets = {normalize_url(v) for v in anns.values() if v}
        for lang, target in anns.items():
            status = "ok"
            evidence = ""
            lang_norm = str(lang).lower()
            if not re.match(r"^[a-z]{2,3}(-[a-z0-9]{2,4})?$|^x-default$", lang_norm):
                status = "invalid_language_code"
                evidence = f"Unrecognised hreflang value: {lang}"
            elif normalize_url(rec.url) not in targets:
                status = "missing_self_reference"
                evidence = "No annotation pointing back to this URL"
            elif "x-default" not in anns:
                status = "missing_x_default"
                evidence = "No x-default annotation"
            if rec.canonical and normalize_url(rec.canonical) != normalize_url(rec.url):
                status = "canonical_hreflang_conflict"
                evidence = "Canonical differs from hreflang self reference"
            db.add(HreflangRecord(
                project_id=project_id, url=rec.url, lang=lang_norm, target=target,
                status=status, evidence=evidence,
            ))
            checked += 1
    db.commit()
    return {"plan_id": plan.id, "market": market, "language": language,
            "service_pages": len(service_pages), "supporting_content": len(support_content),
            "hreflang_records_checked": checked}


def _norm_phone(value: str) -> str:
    return re.sub(r"\D", "", value or "")[-10:]


def local_audit(db: Session, project_id: int) -> dict[str, Any]:
    locations = db.scalars(select(Location).where(Location.project_id == project_id)).all()
    groups: dict[str, list[Location]] = defaultdict(list)
    for loc in locations:
        key = re.sub(r"\W+", "", (loc.name or "").lower())[:25] + "|" + re.sub(r"\W+", "", (loc.address or "").lower())[:40]
        groups[key].append(loc)
        issues = []
        for field in ("name", "address", "city", "country", "phone", "website", "category"):
            if not getattr(loc, field):
                issues.append(f"missing_{field}")
        if loc.phone and not re.match(r"^\+?[\d\s().-]{7,20}$", loc.phone):
            issues.append("suspicious_phone_format")
        if loc.website and not str(loc.website).startswith(("http://", "https://")):
            issues.append("website_url_format")
        if not loc.landing_page:
            issues.append("no_location_landing_page")
        loc.issues = issues
        loc.audit = {
            "checked_at": iso(utcnow()),
            "gbp_fields": {f: bool(getattr(loc, f)) for f in ("name", "address", "phone", "website", "category")},
            "schema_recommendation": ["LocalBusiness", "BreadcrumbList"],
            "note": "GBP data must come from an authorised API or user import; no restricted scraping.",
        }
    dup_count = 0
    for key, group in groups.items():
        if len(group) > 1:
            dup_count += len(group) - 1
            group_id = key[:30]
            for loc in group:
                loc.duplicate_group = group_id
                if "possible_duplicate_location" not in loc.issues:
                    loc.issues.append("possible_duplicate_location")
    # phone consistency across same brand
    phone_by_brand: dict[str, set[str]] = defaultdict(set)
    for loc in locations:
        if loc.brand and loc.phone:
            phone_by_brand[loc.brand].add(_norm_phone(loc.phone))
    inconsistent_brands = [b for b, phones in phone_by_brand.items() if len(phones) > 1]
    db.commit()
    return {
        "locations": len(locations), "duplicate_suspects": dup_count,
        "incomplete_profiles": sum(1 for l in locations if l.issues),
        "inconsistent_phone_brands": inconsistent_brands[:20],
        "note": "Review duplicates manually; identical phone numbers can be legitimate for shared call centres.",
    }


def ecommerce_audit(db: Session, project_id: int) -> dict[str, Any]:
    products = db.scalars(select(Product).where(Product.project_id == project_id).limit(100000)).all()
    descriptions = Counter((p.description or "").strip().lower() for p in products if p.description)
    urls = db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id)).all()
    status_by_url = {normalize_url(u.url): u for u in urls}
    for p in products:
        diagnostics = []
        if not p.identifier:
            diagnostics.append("missing_product_identifier")
        if not p.price:
            diagnostics.append("missing_price")
        if p.availability and p.availability.lower() in {"out of stock", "discontinued", "sold out"}:
            diagnostics.append("unavailable_product")
        if not p.description or len(p.description) < 40:
            diagnostics.append("thin_description")
        elif descriptions[(p.description or "").strip().lower()] > 1:
            diagnostics.append("duplicate_description")
        if not p.canonical:
            diagnostics.append("no_canonical_declared")
        if "Product" not in (p.schema_types or []):
            diagnostics.append("missing_product_schema")
        if "BreadcrumbList" not in (p.schema_types or []):
            diagnostics.append("missing_breadcrumb_schema")
        params = urlsplit(p.url).query
        if params and any(k in params for k in ("filter", "sort", "page", "color", "size")):
            diagnostics.append("faceted_or_parameter_url")
        rec = status_by_url.get(normalize_url(p.url))
        if rec:
            if rec.http_status and rec.http_status >= 400:
                diagnostics.append(f"landing_page_status_{rec.http_status}")
            if rec.indexable is False:
                diagnostics.append("landing_page_not_indexable")
            p.canonical = p.canonical or rec.canonical
        p.diagnostics = diagnostics
        scored = calculate_priority(issue_components(
            affected_count=1, severity="high" if any(d.startswith("landing_page_status") for d in diagnostics) else "medium",
            confidence="imported", business_impact="unknown",
        ))
        p.priority = scored["priority"] if diagnostics else "P3"
        if p.status.lower() in {"discontinued", "archived"}:
            p.priority = "P3"
    db.commit()
    diag_counts = Counter(d for p in products for d in (p.diagnostics or []))
    return {
        "products": len(products), "diagnostic_counts": dict(diag_counts),
        "note": "Merchant Center issues are from imported diagnostics or user data unless an official integration is configured.",
    }


def migration_validate(db: Session, project_id: int, config: dict | None = None) -> dict[str, Any]:
    mappings = db.scalars(select(MigrationMapping).where(MigrationMapping.project_id == project_id)).all()
    records = {normalize_url(r.url): r for r in db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id)
    )}
    sitemap = set()
    from app.models.inventory import SitemapEntry
    for entry in db.scalars(select(SitemapEntry).where(SitemapEntry.project_id == project_id)):
        sitemap.add(normalize_url(entry.loc))
    findings_counts: Counter = Counter()
    for mapping in mappings:
        findings = []
        target = records.get(normalize_url(mapping.new_url)) if mapping.new_url else None
        if not mapping.new_url:
            findings.append("missing_redirect_target")
        if target:
            mapping.http_status = target.http_status
            mapping.new_canonical = target.canonical
            mapping.new_indexable = target.indexable
            if target.http_status == 404:
                findings.append("new_url_404")
            if target.redirect_chain and len(target.redirect_chain) > 2:
                findings.append("redirect_chain")
            norm_chain = [normalize_url(u) for u in (target.redirect_chain or [])]
            if len(norm_chain) > 2 and len(set(norm_chain)) != len(norm_chain):
                findings.append("redirect_loop")
            if target.canonical and normalize_url(target.canonical) != normalize_url(mapping.new_url):
                findings.append("canonical_mismatch")
            if target.indexable is False:
                findings.append("new_url_not_indexable")
        elif mapping.new_url:
            findings.append("new_url_not_crawled")
        mapping.in_new_sitemap = bool(mapping.new_url and normalize_url(mapping.new_url) in sitemap)
        if mapping.in_old_sitemap and not mapping.in_new_sitemap:
            findings.append("missing_from_new_sitemap")
        scored = calculate_priority(issue_components(
            affected_count=1,
            clicks=mapping.clicks, revenue=mapping.revenue,
            severity="critical" if mapping.revenue > 1000 or mapping.clicks > 500 else "high",
            confidence="verified" if target else "unverified",
            business_impact="critical" if mapping.revenue > 1000 else "high",
        ))
        mapping.risk = scored["priority"]
        mapping.findings = findings
        if not findings:
            mapping.redirect_status = "validated" if target else mapping.redirect_status
            mapping.recommendation = "No issue detected from supplied data; revalidate after launch"
        elif "redirect_loop" in findings:
            mapping.recommendation = "Remove redirect loop before launch"
        elif "missing_redirect_target" in findings:
            mapping.recommendation = "Define a relevant destination or a deliberate 410; do not send to homepage by default"
        else:
            mapping.recommendation = "Fix listed findings and re-crawl"
        findings_counts.update(findings)
    db.commit()
    report = {
        "mappings_checked": len(mappings), "findings": dict(findings_counts),
        "high_risk_mappings": sum(1 for m in mappings if m.risk in {"P0", "P1"}),
        "pre_launch_checklist": [
            "All old URLs have an intended destination or deliberate 410",
            "Redirects are 301 for permanent moves and direct to final URL",
            "No redirect loops or chains",
            "Canonicals point to new URLs",
            "New sitemap contains intended indexable URLs",
            "Internal links updated to new URLs",
            "GSC/GA baselines captured for equivalent comparison",
        ],
    }
    return report


def ai_readiness(db: Session, project_id: int) -> dict[str, Any]:
    records = db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id).limit(50000)).all()
    db.query(AiReadinessItem).filter(AiReadinessItem.project_id == project_id).delete()
    dimensions = [
        ("question_coverage", lambda r: bool(r.h2 and any(str(h).strip().endswith("?") for h in r.h2)),
         "Add question-based headings derived from real queries"),
        ("answer_extraction", lambda r: r.word_count >= 150 and bool(r.h1),
         "Place a concise, self-contained answer directly under the heading"),
        ("entity_clarity", lambda r: bool(r.title and r.h1),
         "State the organisation, service and location clearly"),
        ("structured_data", lambda r: bool(r.schema_types),
         "Add valid Organization/FAQ/Service structured data where appropriate"),
        ("author_organisation_info", lambda r: "organization" in str(r.og or {}).lower() or bool(r.schema_types),
         "Add visible author and organisation provenance"),
        ("internal_link_context", lambda r: r.internal_inlinks >= 2,
         "Add contextual internal links that clarify topic relationships"),
    ]
    created = 0
    for rec in records:
        for name, predicate, recommendation in dimensions:
            ok = bool(predicate(rec))
            db.add(AiReadinessItem(
                project_id=project_id, url=rec.url, dimension=name,
                status="present" if ok else "gap",
                evidence=(f"word_count={rec.word_count}; h1={len(rec.h1 or [])}; "
                          f"schema={rec.schema_types}; inlinks={rec.internal_inlinks}"),
                recommendation="" if ok else recommendation,
                data_kind="derived_from_crawl",
            ))
            created += 1
    observations = db.scalars(select(AiVisibilityRecord).where(AiVisibilityRecord.project_id == project_id)).all()
    db.commit()
    return {
        "readiness_items": created,
        "observed_questions": len({o.question for o in observations}),
        "brand_mentions_observed": sum(1 for o in observations if o.brand_mentioned),
        "note": "Readiness is derived from crawl evidence. Visibility is only reported from user-supplied or manually verified observations. No guarantee of AI answer inclusion is made.",
    }
