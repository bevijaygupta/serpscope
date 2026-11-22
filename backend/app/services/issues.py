"""Technical SEO rule engine with explainable prioritisation."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlsplit

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import hostname_of, normalize_url
from app.models.analysis import Issue, IssueUrl
from app.models.inventory import LinkEdge, UrlRecord
from app.services.priority import calculate_priority, issue_components

RULES: list[dict] = [
    {"code": "http_404", "name": "404 pages", "category": "status", "severity": "high", "fix": "Restore the page, redirect to a genuinely relevant replacement, or return a deliberate 410 for obsolete URLs."},
    {"code": "http_4xx", "name": "Other 4xx responses", "category": "status", "severity": "high", "fix": "Investigate access control, authentication or broken routing; do not blanket-redirect."},
    {"code": "http_5xx", "name": "Server errors (5xx)", "category": "status", "severity": "critical", "fix": "Escalate to engineering; verify upstream dependencies and retry after fix."},
    {"code": "redirect_chain", "name": "Redirect chains", "category": "redirect", "severity": "medium", "fix": "Redirect directly to the final destination and update internal links."},
    {"code": "redirect_loop", "name": "Redirect loops", "category": "redirect", "severity": "critical", "fix": "Remove the cyclical redirect rule and validate with a fresh crawl."},
    {"code": "temporary_redirect", "name": "Temporary redirect on important URL", "category": "redirect", "severity": "medium", "fix": "Use 301 only where the move is permanent; otherwise retain 302/307 intentionally."},
    {"code": "canonical_mismatch", "name": "Canonical points to a different URL", "category": "canonical", "severity": "medium", "fix": "Confirm intended canonical and align sitemap, internal links and hreflang."},
    {"code": "canonical_chain", "name": "Canonical to redirected URL", "category": "canonical", "severity": "medium", "fix": "Point canonicals at the final URL and update internal links."},
    {"code": "canonical_conflict", "name": "Conflicting canonical signals", "category": "canonical", "severity": "high", "fix": "Resolve disagreement between canonical tag, sitemap, redirect destination and hreflang."},
    {"code": "noindex_in_sitemap", "name": "Noindex URL in sitemap", "category": "indexability", "severity": "high", "fix": "Remove the URL from the sitemap, or remove noindex if the page should rank."},
    {"code": "robots_blocked", "name": "Robots-blocked indexed URL", "category": "indexability", "severity": "high", "fix": "Verify whether blocking is intentional; check for orphaned indexing signals."},
    {"code": "indexability_inconsistent", "name": "Indexability inconsistency", "category": "indexability", "severity": "medium", "fix": "Align meta robots, X-Robots-Tag, canonical and status code."},
    {"code": "missing_title", "name": "Missing title", "category": "content", "severity": "medium", "fix": "Add a unique, descriptive title aligned to the page's primary topic."},
    {"code": "missing_description", "name": "Missing meta description", "category": "content", "severity": "low", "fix": "Add a unique description that summarises the page's value proposition."},
    {"code": "missing_h1", "name": "Missing H1", "category": "content", "severity": "low", "fix": "Add one clear H1 describing the page topic."},
    {"code": "multiple_h1", "name": "Multiple H1 elements (review)", "category": "content", "severity": "info", "fix": "Review hierarchy; multiple H1s are a signal, not automatically an error."},
    {"code": "duplicate_title", "name": "Duplicate title tags", "category": "content", "severity": "medium", "fix": "Differentiate titles by topic, intent and location."},
    {"code": "duplicate_description", "name": "Duplicate meta descriptions", "category": "content", "severity": "low", "fix": "Rewrite descriptions to reflect each page's distinct offering."},
    {"code": "thin_content", "name": "Thin content", "category": "content", "severity": "medium", "fix": "Expand with original, useful depth or consolidate into a stronger page."},
    {"code": "broken_internal_link", "name": "Broken internal links", "category": "links", "severity": "high", "fix": "Fix or remove the link and update any templates that generated it."},
    {"code": "broken_external_link", "name": "Broken external links", "category": "links", "severity": "low", "fix": "Replace or remove dead external references; verify manually before bulk changes."},
    {"code": "orphan_page", "name": "Orphan pages", "category": "links", "severity": "medium", "fix": "Add relevant contextual internal links from authoritative pages."},
    {"code": "excessive_depth", "name": "Excessive crawl depth", "category": "architecture", "severity": "medium", "fix": "Flatten architecture so important pages are reachable in fewer clicks."},
    {"code": "slow_response", "name": "Slow server response", "category": "performance", "severity": "medium", "fix": "Investigate server time, caching and heavy templates."},
    {"code": "oversized_page", "name": "Oversized pages", "category": "performance", "severity": "low", "fix": "Reduce payload size and defer non-critical resources."},
    {"code": "missing_schema", "name": "Missing structured data", "category": "structured-data", "severity": "low", "fix": "Add valid structured data appropriate to the page type."},
    {"code": "invalid_schema", "name": "Invalid structured data", "category": "structured-data", "severity": "medium", "fix": "Correct JSON-LD against schema.org and revalidate."},
    {"code": "hreflang_error", "name": "Hreflang inconsistencies", "category": "international", "severity": "medium", "fix": "Ensure self-referencing and reciprocal annotations with valid language codes."},
    {"code": "pagination_problem", "name": "Pagination signals missing", "category": "architecture", "severity": "low", "fix": "Add rel=next/prev or validated crawlable pagination links."},
    {"code": "parameter_duplication", "name": "Parameter-based duplicate URLs", "category": "architecture", "severity": "medium", "fix": "Define canonical parameter handling and block worthless facet combinations."},
    {"code": "soft_404", "name": "Soft 404 indicators", "category": "status", "severity": "medium", "fix": "Return a real 404/410 or restore useful content; requires manual confirmation."},
]
RULE_MAP = {r["code"]: r for r in RULES}

SERVICES = {"vapt", "managed security", "cloud security", "incident response", "cybersecurity", "pentest"}
STOPWORDS = {"the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with", "www", "com", "sg", "singapore", "https", "http"}


def tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 2 and t not in STOPWORDS}


def relevance_tokens(text: str) -> set[str]:
    tokens = tokenize(text)
    return tokens | {t for t in tokens if t in SERVICES}


def choose_replacements(missing_url: str, records: list[UrlRecord], limit: int = 3) -> list[dict]:
    """Suggest candidate replacements from observed live pages. Rule-based only."""
    target_tokens = tokenize(urlsplit(missing_url).path.replace("-", " ").replace("/", " "))
    target_tokens |= tokenize(missing_url)
    candidates = []
    for rec in records:
        if rec.http_status is None or not (200 <= rec.http_status < 300):
            continue
        if normalize_url(rec.url) == normalize_url(missing_url):
            continue
        text = f"{rec.url} {rec.title or ''} {' '.join(rec.h1 or [])}"
        tokens = tokenize(text)
        if not tokens:
            continue
        overlap = target_tokens & tokens
        score = len(overlap) / max(1, len(target_tokens | tokens))
        if score > 0.12:
            candidates.append({
                "url": rec.url,
                "title": rec.title,
                "similarity": round(score, 3),
                "shared_terms": sorted(overlap)[:8],
                "source": "rule-based token overlap",
            })
    candidates.sort(key=lambda x: x["similarity"], reverse=True)
    return candidates[:limit]


def _iter_records(db: Session, project_id: int, batch: int = 2000) -> Iterable[UrlRecord]:
    last_id = 0
    while True:
        rows = db.scalars(
            select(UrlRecord)
            .where(UrlRecord.project_id == project_id, UrlRecord.id > last_id)
            .order_by(UrlRecord.id)
            .limit(batch)
        ).all()
        if not rows:
            break
        for row in rows:
            yield row
        last_id = rows[-1].id


def detect_issues(db: Session, project_id: int, max_records: int = 200000) -> dict[str, Any]:
    """Run all rules over the shared inventory and persist grouped issues."""
    now = iso(utcnow())
    groups: dict[str, list[dict]] = {code: [] for code in RULE_MAP}
    duplicates: dict[str, Counter] = {"title": Counter(), "description": Counter()}

    records = list(_iter_records(db, project_id))
    records = records[:max_records]
    live_candidates = [r for r in records if r.crawled]

    # Duplicate metadata grouped across inventory
    for rec in records:
        if rec.title:
            duplicates["title"][rec.title.strip().lower()] += 1
        if rec.meta_description:
            duplicates["description"][rec.meta_description.strip().lower()] += 1

    # Broken links
    broken_targets: dict[str, list[str]] = {}
    for edge in db.scalars(select(LinkEdge).where(
        LinkEdge.project_id == project_id, LinkEdge.is_broken.is_(True)
    )):
        broken_targets.setdefault(edge.target_url, []).append(edge.source_url)

    for rec in records:
        status = rec.http_status
        url = rec.url
        chain = rec.redirect_chain or []
        ev = {
            "status": status, "crawled": rec.crawled, "indexable": rec.indexable,
            "sitemap": rec.in_sitemap, "clicks": rec.clicks, "impressions": rec.impressions,
            "sessions": rec.sessions, "conversions": rec.conversions, "revenue": rec.revenue,
            "inlinks": rec.internal_inlinks, "data_kind": rec.data_kind,
        }
        add = lambda code, extra=None: groups[code].append({"url": url, "evidence": {**ev, **(extra or {})}})
        if status == 404:
            add("http_404", {"replacements": choose_replacements(url, live_candidates)})
        elif status is not None and 400 <= status < 500:
            add("http_4xx")
        elif status is not None and status >= 500:
            add("http_5xx")
        if len(chain) > 1:
            add("redirect_chain", {"chain": chain})
            normalized = [normalize_url(u) for u in chain]
            if len(normalized) > 2 and len(set(normalized)) < len(normalized):
                add("redirect_loop")
        if len(chain) == 2 and any(s in str(rec.redirected_to or "") for s in ("?temp", "temp", "/tmp")):
            add("temporary_redirect")
        canonical = rec.canonical or ""
        if canonical and normalize_url(canonical) != normalize_url(url):
            add("canonical_mismatch", {"canonical": canonical})
            if rec.redirected_to and normalize_url(canonical) == normalize_url(rec.redirected_to):
                add("canonical_chain")
            if rec.in_sitemap or rec.hreflang or (rec.http_status == 200):
                add("canonical_conflict", {"canonical": canonical, "in_sitemap": rec.in_sitemap})
        if rec.in_sitemap and ("noindex" in (rec.meta_robots or "").lower() or "noindex" in (rec.x_robots_tag or "").lower()):
            add("noindex_in_sitemap")
        if rec.robots_allowed is False and (rec.clicks or rec.impressions or rec.in_sitemap):
            add("robots_blocked")
        if rec.indexable is False and rec.in_sitemap:
            add("indexability_inconsistent")
        if rec.crawled and not rec.title.strip():
            add("missing_title")
        if rec.crawled and not rec.meta_description.strip():
            add("missing_description")
        if rec.crawled and not rec.h1:
            add("missing_h1")
        if rec.crawled and len(rec.h1) > 1:
            add("multiple_h1", {"count": len(rec.h1)})
        if rec.crawled and rec.title.strip() and duplicates["title"][rec.title.strip().lower()] > 1:
            add("duplicate_title")
        if rec.crawled and rec.meta_description.strip() and duplicates["description"][rec.meta_description.strip().lower()] > 1:
            add("duplicate_description")
        if rec.crawled and rec.word_count and rec.word_count < 100 and rec.page_type not in {"homepage", "category"}:
            add("thin_content", {"word_count": rec.word_count})
        if (rec.response_time_ms or 0) > 2500:
            add("slow_response", {"response_time_ms": rec.response_time_ms})
        if (rec.content_size or 0) > 2_000_000:
            add("oversized_page", {"bytes": rec.content_size})
        if rec.page_type in {"product", "service", "article"} and not rec.schema_types:
            add("missing_schema", {"page_type": rec.page_type})
        if "invalid-json-ld" in (rec.schema_types or []):
            add("invalid_schema")
        if rec.hreflang:
            self_ref = rec.hreflang.get("x-default") or rec.hreflang.get("en")
            langs = set(rec.hreflang)
            problems = []
            if not self_ref:
                problems.append("No x-default/en annotation")
            for lang, target in rec.hreflang.items():
                if not hostname_of(target):
                    problems.append(f"Invalid target for {lang}")
            if len(langs) >= 2 and normalize_url(rec.url) not in {normalize_url(t) for t in rec.hreflang.values()}:
                problems.append("No self-referencing annotation")
            if problems:
                add("hreflang_error", {"problems": problems})
        if rec.page_type in {"category", "product"} and rec.pagination and not (rec.pagination.get("next") or rec.pagination.get("prev")):
            add("pagination_problem")
        params = [k for k, _ in parse_qsl(urlsplit(url).query)]
        if len(params) >= 2 and rec.crawled and status == 200:
            add("parameter_duplication", {"parameters": params[:10]})
        if status == 200 and rec.word_count < 60 and rec.clicks == 0 and rec.in_sitemap:
            add("soft_404", {"word_count": rec.word_count, "note": "Indicators only; manual confirmation required"})

    for target, sources in broken_targets.items():
        groups["broken_internal_link"].append({
            "url": target,
            "evidence": {"linking_sources": sources[:20], "source_count": len(sources)},
        })

    # Detected orphan issues come from the orphan engine's persisted classification
    orphan_rows = db.execute(text(
        "SELECT url, internal_inlinks, clicks, revenue, confidence FROM orphan_records "
        "WHERE project_id=:p AND classification IN ('Confirmed crawl orphan','Sitemap-only orphan') LIMIT 50000"
    ), {"p": project_id}).all()
    for row in orphan_rows:
        groups["orphan_page"].append({
            "url": row[0],
            "evidence": {"inlinks": row[1], "clicks": row[2], "revenue": row[3], "confidence": row[4]},
        })

    # Replace previous detections that are no longer present. Manual edits are preserved.
    existing = db.scalars(select(Issue).where(Issue.project_id == project_id)).all()
    for issue in existing:
        if issue.source != "rule-engine":
            continue
        if issue.status == "Detected" and not groups.get(issue.code):
            issue.status = "Resolved"
            issue.validation_status = "pending"

    by_code: dict[str, dict] = {}
    existing_by_code = {(i.code, i.status): i for i in existing if i.source == "rule-engine"}
    for code, urls in groups.items():
        if not urls:
            continue
        rule = RULE_MAP[code]
        severity = rule["severity"]
        confidence = "verified" if code.startswith("http_") else "imported"
        business_impact = "critical" if any(
            (u["evidence"].get("revenue") or 0) > 1000 or (u["evidence"].get("clicks") or 0) > 500
            for u in urls
        ) else ("high" if any((u["evidence"].get("clicks") or 0) > 50 for u in urls) else "unknown")
        components = issue_components(
            affected_count=len(urls),
            clicks=sum(float(u["evidence"].get("clicks") or 0) for u in urls),
            impressions=sum(float(u["evidence"].get("impressions") or 0) for u in urls),
            revenue=sum(float(u["evidence"].get("revenue") or 0) for u in urls),
            conversions=sum(float(u["evidence"].get("conversions") or 0) for u in urls),
            severity=severity, confidence=confidence, business_impact=business_impact,
        )
        scored = calculate_priority(components, confidence, context=f"{len(urls)} URLs affected; code={code}")
        issue = existing_by_code.get((code, "Detected"))
        if issue is None:
            issue = Issue(
                project_id=project_id, code=code, name=rule["name"], category=rule["category"],
                status="Detected", detected_at=now, source="rule-engine",
            )
            db.add(issue)
            db.flush()
            existing_by_code[(code, "Detected")] = issue
        issue.severity = severity
        issue.priority = scored["priority"]
        issue.priority_score = scored["score"]
        issue.priority_explanation = scored["explanation"]
        issue.business_impact = business_impact
        issue.affected_count = len(urls)
        issue.page_templates = sorted({str(u["evidence"].get("page_type", "")) for u in urls if u["evidence"].get("page_type")})[:20]
        issue.evidence = {
            "sample_urls": [u["url"] for u in urls[:15]],
            "detection_rule": code,
            "data_kind": "derived_from_observations",
            "replacements": next((u["evidence"].get("replacements") for u in urls if u["evidence"].get("replacements")), []),
        }
        issue.recommended_fix = rule["fix"]
        issue.updated_at = utcnow().replace(tzinfo=None)
        db.flush()
        db.query(IssueUrl).filter(IssueUrl.issue_id == issue.id).delete()
        for entry in urls[:5000]:
            db.add(IssueUrl(project_id=project_id, issue_id=issue.id, url=entry["url"], evidence=entry["evidence"]))
        by_code[code] = {"count": len(urls), "priority": scored["priority"], "score": scored["score"]}
    db.commit()
    return {"detected_at": now, "issues": by_code, "total_issue_groups": len(by_code), "records_scanned": len(records)}


def high_value_404s(db: Session, project_id: int) -> list[dict]:
    """Dedicated workflow: 404s ranked by supplied business evidence."""
    rows = db.execute(text(
        "SELECT url, title, clicks, impressions, sessions, conversions, revenue, referring_domains, "
        "internal_inlinks, in_sitemap, redirect_chain, page_type FROM url_records "
        "WHERE project_id=:p AND http_status=404 ORDER BY revenue DESC, clicks DESC LIMIT 5000"
    ), {"p": project_id}).all()
    result = []
    for row in rows:
        (url, title, clicks, impressions, sessions, conversions, revenue, rd, inlinks, in_sitemap, chain, page_type) = row
        components = issue_components(
            affected_count=1, clicks=clicks, impressions=impressions, revenue=revenue,
            conversions=conversions, severity="high",
            confidence="verified" if (clicks or revenue or sessions) else "unverified",
            business_impact="critical" if revenue > 1000 or conversions > 10 else ("high" if clicks > 50 else "unknown"),
        )
        scored = calculate_priority(components, components["confidence"] >= 50 and "verified" or "unverified")
        if revenue > 0 and inlinks > 0:
            action = "Restore original page or implement a relevant 301; update internal links"
        elif revenue > 0:
            action = "Investigate business value, then restore or redirect to a matching page (never blanket to homepage)"
        elif clicks > 0:
            action = "Match with GSC queries and redirect/restore where intent is still served"
        else:
            action = "Verify whether the URL should return 404/410 or be restored"
        result.append({
            "url": url, "title": title, "clicks": clicks, "impressions": impressions,
            "sessions": sessions, "conversions": conversions, "revenue": revenue,
            "referring_domains": rd, "internal_inlinks": inlinks, "in_sitemap": bool(in_sitemap),
            "redirect_chain": chain, "page_type": page_type,
            "priority": scored["priority"], "score": scored["score"],
            "components": scored["components"], "explanation": scored["explanation"],
            "recommended_action": action,
        })
    return result
