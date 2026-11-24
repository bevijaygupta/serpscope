"""Source-tracked public-evidence audit and six-month roadmap.

This service deliberately uses only data that SERPScope can observe itself
(crawl, sitemap, robots.txt and derived rules) or that a user imported with a
declared source. It never invents Search Console, Analytics, ranking, volume or
AI-visibility metrics.
"""
from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.models.analysis import ContentAnalysis, Issue, LinkSuggestion, OrphanRecord
from app.models.enterprise import AiReadinessItem, Competitor, KeywordGap
from app.models.inventory import Crawl, CrawlObservation, SitemapEntry, UrlRecord
from app.models.keywords import Keyword, KeywordMapping
from app.models.operations import Report
from app.models.projects import Project
from app.services import crawler as crawler_service
from app.services.supplied_metrics import SIGNAL_LABELS, supplied_signals

SEVERITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Info": 4, "Positive": 5}


def _pct(value: float, total: float) -> float:
    return round(100.0 * value / total, 1) if total else 0.0


def _short_url(url: str, limit: int = 110) -> str:
    text = str(url or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _issue_map(db: Session, project_id: int) -> dict[str, Issue]:
    rows = db.scalars(select(Issue).where(Issue.project_id == project_id)).all()
    # Prefer the open/detected row when a code has both old and current entries.
    result: dict[str, Issue] = {}
    for row in rows:
        existing = result.get(row.code)
        if existing is None or (existing.status in {"Closed", "Resolved"} and row.status not in {"Closed", "Resolved"}):
            result[row.code] = row
    return result


def _ai_rules_summary(robots: dict) -> dict:
    rules = robots.get("ai_rules") or {}
    summary = {}
    for agent, detail in rules.items():
        allow = detail.get("allow") or []
        disallow = detail.get("disallow") or []
        if "/" in disallow:
            policy = "explicitly_disallowed"
        elif "/" in allow:
            policy = "explicitly_allowed"
        elif allow or disallow:
            policy = "path_specific_rule"
        else:
            policy = "declared_without_path_rule"
        summary[agent] = {"policy": policy, "allow": allow[:5], "disallow": disallow[:5]}
    return summary


def _findings(db: Session, project_id: int, crawl: Crawl | None, audit: dict) -> list[dict]:
    issues = _issue_map(db, project_id)
    records = db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id)).all()
    crawled = [r for r in records if r.crawled]
    findings: list[dict] = []

    def add(key, title, severity, category, count, detail, action, evidence=None, source=None, limitation=""):
        if source is None and isinstance(evidence, list):
            source, evidence = evidence, {}
        if not count:
            return
        findings.append({
            "id": key,
            "title": title,
            "severity": severity,
            "category": category,
            "affected_count": int(count),
            "observation": detail,
            "recommended_action": action,
            "evidence": evidence or {},
            "source": source or ["SERPScope crawler / rule engine"],
            "confidence": "verified_from_public_evidence" if category in {"status", "indexability", "sitemap", "robots"} else "derived_from_observations",
            "limitation": limitation,
        })

    status_codes = Counter(r.http_status for r in crawled if r.http_status is not None)
    error_count = sum(v for k, v in status_codes.items() if k and k >= 400)
    add(
        "http_errors", "HTTP error responses observed", "Critical" if status_codes.get(500) else "High", "status",
        error_count,
        f"{error_count} fetched URLs returned 4xx/5xx. Observed distribution: "
        + ", ".join(f"{k}: {v}" for k, v in sorted(status_codes.items()) if k and k >= 400),
        "Triage server errors first, then restore or deliberately retire 4xx URLs; map replacements from observed similar pages.",
        {"status_codes": {str(k): v for k, v in sorted(status_codes.items()) if k is not None}},
        ["crawl_observations", "url_records"],
    )

    canonical_issue = issues.get("canonical_mismatch") or issues.get("canonical_conflict")
    canonical_count = canonical_issue.affected_count if canonical_issue else sum(
        1 for r in crawled if r.canonical and urlsplit(r.canonical).geturl() != r.url
    )
    add(
        "canonical_signals", "Canonical signals require review", "High", "indexability",
        canonical_count,
        "Canonical URL differs from the fetched URL on the observed pages.",
        "Confirm intended canonical, then align canonical tags, sitemap entries and internal links.",
        {"sample_urls": (canonical_issue.evidence or {}).get("sample_urls", [])[:10]} if canonical_issue else {},
        ["crawl_observations", "technical issue rules"],
    )

    redirect_issue = issues.get("redirect_chain") or issues.get("redirect_loop")
    add(
        "redirects", "Redirect chains or loops detected", "Medium", "indexability",
        redirect_issue.affected_count if redirect_issue else 0,
        "One or more fetched URLs required multiple redirect hops.",
        "Point internal links and sitemap entries directly at the final URL; remove cyclical rules.",
        {"sample_urls": (redirect_issue.evidence or {}).get("sample_urls", [])[:10]} if redirect_issue else {},
        ["crawl_observations", "technical issue rules"],
    )

    missing_title = issues.get("missing_title")
    add("missing_title", "Missing title tags", "High", "content",
        missing_title.affected_count if missing_title else 0,
        "Crawled pages with no <title> element.",
        "Add unique, descriptive titles reflecting the page topic and brand.",
        ["crawl_observations", "technical issue rules"])

    missing_desc = issues.get("missing_description")
    add("missing_description", "Missing meta descriptions", "Low", "content",
        missing_desc.affected_count if missing_desc else 0,
        "Crawled pages with no meta description.",
        "Write concise descriptions that differentiate each page; Google may still rewrite them.",
        ["crawl_observations", "technical issue rules"])

    missing_h1 = issues.get("missing_h1")
    add("missing_h1", "Missing H1 headings", "Medium", "content",
        missing_h1.affected_count if missing_h1 else 0,
        "Crawled pages with no H1 element.",
        "Add one clear H1 that matches the page's primary topic.",
        ["crawl_observations", "technical issue rules"])

    duplicate_title = issues.get("duplicate_title")
    add("duplicate_title", "Duplicate title tags", "Medium", "content",
        duplicate_title.affected_count if duplicate_title else 0,
        "Identical titles were observed on more than one URL.",
        "Differentiate titles by topic, intent and location.",
        ["crawl_observations", "technical issue rules"])

    thin = issues.get("thin_content")
    add("thin_content", "Thin content indicators", "Medium", "content",
        thin.affected_count if thin else 0,
        "Crawled pages below the 100-word rule threshold.",
        "Expand with original useful depth or consolidate into a stronger page.",
        source=["crawl_observations", "content rules"],
        limitation="Word count is extracted from server HTML only; JS-rendered content is not counted.")

    slow = issues.get("slow_response")
    add("slow_response", "Slow server responses", "Medium", "performance",
        slow.affected_count if slow else 0,
        "Fetched URLs exceeded the 2,500 ms rule threshold.",
        "Investigate server time, caching and heavy templates; re-crawl after fixes.",
        ["crawl_observations", "technical issue rules"])

    schema_issue = issues.get("missing_schema")
    add("missing_schema", "Structured data missing on commercial pages", "Low", "structured-data",
        schema_issue.affected_count if schema_issue else 0,
        "Service/product/article pages without detected JSON-LD structured data.",
        "Add valid Organization, Service/Product, BreadcrumbList and FAQ markup where genuinely applicable.",
        ["crawl_observations", "structured-data rules"])

    orphans = db.scalars(select(OrphanRecord).where(
        OrphanRecord.project_id == project_id,
        OrphanRecord.classification.in_(["Confirmed crawl orphan", "Sitemap-only orphan"]),
    )).all()
    add("orphans", "URLs with no discovered internal inlinks", "High", "architecture",
        len(orphans),
        f"{len(orphans)} URLs are classified as confirmed crawl or sitemap-only orphans.",
        "Add contextual internal links from relevant authoritative pages and re-crawl.",
        {"samples": [{"url": r.url, "classification": r.classification, "confidence": r.confidence} for r in orphans[:10]]},
        ["sitemap", "link_edges", "orphan reconciliation"],
        "Absence of a discovered link is not proof of no link; JS-rendered and excluded links may be missed.")

    ai_gaps = db.scalars(select(AiReadinessItem).where(
        AiReadinessItem.project_id == project_id, AiReadinessItem.status == "gap",
    )).all()
    gap_counts = Counter(r.dimension for r in ai_gaps)
    add("aeo_readiness", "Answer-engine readiness gaps", "Medium", "aeo",
        len(ai_gaps),
        "Rule-based gaps across question coverage, answer extraction, entity clarity, structured data, provenance and internal context."
        + (" Most common: " + ", ".join(f"{k}={v}" for k, v in gap_counts.most_common(4)) if gap_counts else ""),
        "Prioritise question headings, concise answer blocks, visible organisation details and valid structured data on commercially important pages.",
        {"by_dimension": dict(gap_counts)},
        ["crawl_observations", "AEO readiness rules"],
        "Readiness is not the same as observed visibility in ChatGPT, Claude, Perplexity or Google AI Overviews.")

    suggestions = db.scalars(select(LinkSuggestion).where(LinkSuggestion.project_id == project_id)).all()
    add("internal_link_suggestions", "Reviewable internal-link suggestions", "Info", "architecture",
        len(suggestions),
        "Topical-overlap suggestions generated from the observed internal link graph.",
        "Review and apply the highest-relevance suggestions; no link is deployed automatically.",
        {"samples": [{"source": s.source_url, "target": s.target_url, "relevance": s.relevance} for s in suggestions[:5]]},
        ["link_edges", "graph rules"])

    sitemap_info = (((crawl.summary or {}) if crawl else {}).get("sitemap") or {})
    sitemap_entries = db.scalars(select(SitemapEntry).where(SitemapEntry.project_id == project_id)).all()
    if sitemap_info or sitemap_entries:
        findings.append({
            "id": "sitemap_evidence",
            "title": "Sitemap evidence captured",
            "severity": "Positive",
            "category": "sitemap",
            "affected_count": len(sitemap_entries),
            "observation": f"Discovered {len(sitemap_entries)} sitemap URL entries from "
                           f"{len(sitemap_info.get('sitemap_files') or [])} sitemap document(s).",
            "recommended_action": "Reconcile sitemap URLs with indexable, canonical final URLs and remove obsolete entries.",
            "evidence": {"files": sitemap_info.get("sitemap_files", [])[:10], "declared": sitemap_info.get("declared_sitemaps", [])[:10]},
            "source": ["robots.txt", "sitemap.xml", "sitemap index files"],
            "confidence": "verified_from_public_evidence",
            "limitation": "Sitemap inclusion does not guarantee indexing.",
        })

    robots_info = (((crawl.summary or {}) if crawl else {}).get("robots") or {})
    ai_policy = _ai_rules_summary(robots_info)
    if ai_policy:
        findings.append({
            "id": "ai_crawler_policy",
            "title": "Explicit AI/search crawler policy in robots.txt",
            "severity": "Info",
            "category": "robots",
            "affected_count": len(ai_policy),
            "observation": "robots.txt declares agent-specific rules: "
                           + ", ".join(f"{agent}={v['policy']}" for agent, v in list(ai_policy.items())[:8]),
            "recommended_action": "Keep this policy intentional and documented; verify it against each provider's published crawler names.",
            "evidence": {"robots_url": robots_info.get("url"), "policies": ai_policy},
            "source": ["robots.txt"],
            "confidence": "verified_from_public_evidence",
            "limitation": "A robots.txt allowance does not guarantee crawling, citation, or inclusion in AI answers.",
        })

    coverage = audit["coverage"]
    findings.append({
        "id": "crawl_scope",
        "title": "Public crawl scope and limits",
        "severity": "Info",
        "category": "method",
        "affected_count": coverage["fetched_urls"],
        "observation": f"Fetched {coverage['fetched_urls']} URLs from {coverage['discovered_urls']} discovered URLs "
                       f"with robots respect enabled; {coverage['failed_urls']} fetch failures recorded.",
        "recommended_action": "Treat this as a representative public sample, then widen depth/limits with authorisation for a full-site audit.",
        "evidence": coverage,
        "source": ["crawl run summary", "raw crawl observations"],
        "confidence": "verified_from_public_evidence",
        "limitation": "No JavaScript rendering, authenticated pages, private analytics or vendor APIs are included.",
    })

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 9), -f["affected_count"]))
    return findings


def build_roadmap(audit: dict) -> list[dict]:
    counts = audit["counts"]
    findings = {f["id"]: f for f in audit["findings"]}
    f = lambda key: (findings.get(key) or {}).get("affected_count", 0)

    months = [
        {
            "month": 1,
            "theme": "Baseline, evidence and governance",
            "objective": "Lock a reproducible public-data baseline before changing anything.",
            "actions": [
                f"Re-run the robots-aware crawl and archive raw observations ({audit['coverage']['fetched_urls']} URLs in this run).",
                f"Reconcile {audit['coverage']['sitemap_entries']} sitemap entries with fetched canonical URLs.",
                "Assign owners for technical, content and measurement workstreams.",
                "Agree which pages are commercially important using business input; do not infer value from crawl alone.",
            ],
            "deliverables": ["Raw crawl observation export", "Source-tracked URL inventory", "Issue register", "Signed-off priority page list"],
            "owner": "SEO lead + engineering owner",
            "success_checks": ["Crawl can be reproduced", "Every issue has a source and owner", "No private data is required to start"],
            "without_access": "Fully usable now from crawl, robots.txt, sitemap and public HTML.",
            "with_access": "Add GSC/GA4 exports later to weight pages by actual queries, clicks and conversions.",
        },
        {
            "month": 2,
            "theme": "Technical stabilisation",
            "objective": "Remove confirmed blockers that waste crawl budget or create ambiguous index signals.",
            "actions": [
                f"Triage {f('http_errors')} observed 4xx/5xx URLs; fix server errors first, then restore or retire error URLs.",
                f"Resolve {f('canonical_signals')} canonical conflicts and {f('redirects')} redirect chains/loops.",
                "Align final URL, canonical tag, sitemap entry and internal links for priority templates.",
                "Add regression checks so fixed templates do not reintroduce the same issue.",
            ],
            "deliverables": ["Fix log with before/after evidence", "Updated canonical/redirect rules", "Recrawl comparison"],
            "owner": "Technical SEO + engineering",
            "success_checks": ["Error and canonical issue counts fall on recrawl", "No blanket redirects to the homepage", "Changes are reviewable"],
            "without_access": "Prioritisation uses observed status, canonical and redirect evidence.",
            "with_access": "Use GSC coverage and GA4 landing-page data to confirm which fixed URLs matter commercially.",
        },
        {
            "month": 3,
            "theme": "Architecture and internal link equity",
            "objective": "Make important pages discoverable and reduce reliance on the sitemap alone.",
            "actions": [
                f"Review {f('orphans')} confirmed/sitemap-only orphan URLs and remove obsolete ones from the sitemap.",
                f"Apply the highest-relevance {f('internal_link_suggestions')} link suggestions from hub and topic pages.",
                "Flatten excessive depth for priority service and commercial pages.",
                "Set a rule that every new indexable page ships with at least two contextual internal links.",
            ],
            "deliverables": ["Internal-link implementation sheet", "Updated navigation/hub pages", "Orphan reconciliation report"],
            "owner": "SEO lead + content/design",
            "success_checks": ["Orphan count decreases after recrawl", "Priority pages gain relevant inlinks", "Anchors describe the target topic"],
            "without_access": "Graph evidence comes from observed links, not third-party link databases.",
            "with_access": "Overlay top organic landing pages to prioritise links that protect existing demand.",
        },
        {
            "month": 4,
            "theme": "Content and intent alignment",
            "objective": "Improve clarity and uniqueness using observed on-page evidence.",
            "actions": [
                f"Rewrite {f('missing_title')} missing titles, {f('missing_description')} missing descriptions and {f('missing_h1')} missing H1s.",
                f"Differentiate {f('duplicate_title')} duplicate titles and expand/consolidate {f('thin_content')} thin pages.",
                "Build page briefs from the observed topic and page type; approve each brief before publication.",
                "Define a review cadence for high-value pages based on business priority supplied by the team.",
            ],
            "deliverables": ["On-page fix backlog", "Approved content briefs", "Before/after metadata register"],
            "owner": "Content lead + SEO reviewer",
            "success_checks": ["Metadata uniqueness improves", "Briefs include an explicit source and approval state", "No copied competitor text"],
            "without_access": "On-page gaps are detected without keyword volume or rank data.",
            "with_access": "Import GSC queries/landing pages to choose which real search intent each page should serve.",
        },
        {
            "month": 5,
            "theme": "AEO, GEO and machine-readability",
            "objective": "Improve extractability for answer engines while clearly separating readiness from observed visibility.",
            "actions": [
                f"Close the highest-volume {f('aeo_readiness')} readiness gaps on priority pages.",
                "Add question headings with concise, self-contained answers directly beneath them.",
                "Add valid Organization, Service/Product, BreadcrumbList and FAQ structured data where applicable.",
                "Document and periodically review the robots.txt AI-crawler policy; manually record any AI answer observation.",
            ],
            "deliverables": ["AEO readiness tracker", "Structured-data validation results", "Manual AI visibility observation log"],
            "owner": "SEO lead + content + engineering",
            "success_checks": ["Readiness gaps decrease", "Structured data validates", "Visibility claims only come from recorded observations"],
            "without_access": "Readiness rules run from public crawl evidence; no answer-engine API is claimed.",
            "with_access": "Add manual or licensed AI visibility observations with source and timestamp, never inferred rankings.",
        },
        {
            "month": 6,
            "theme": "Measurement, reporting and scale",
            "objective": "Turn the work into a repeatable management pack with honest data gaps.",
            "actions": [
                "Re-run the same audit and compare source-tracked counts month over month.",
                "Export the site audit, issue register and PPT deck for stakeholders.",
                "Decide whether to add GSC/GA4 CSV imports; if access is refused, keep public-evidence KPIs and label the gap.",
                "Schedule recurring crawls and assign a reviewer for every proposed change.",
            ],
            "deliverables": ["Six-month comparison report", "PPT board deck", "CSV/XLSX/JSON evidence pack", "Next-quarter backlog"],
            "owner": "SEO lead + stakeholders",
            "success_checks": ["Deck opens and every number has a source", "Missing data is listed explicitly", "Next actions have owners"],
            "without_access": "The entire pack is already deliverable from public evidence alone.",
            "with_access": "Vendor data upgrades weighting and outcome measurement; it is not required for the audit to exist.",
        },
    ]
    return months


BASE_SOURCE_REGISTRY: list[dict] = [
    {"source": "robots.txt", "type": "public_document", "confidence": "verified", "used_for": ["crawler permissions", "AI agent policy", "sitemap discovery"]},
    {"source": "sitemap files", "type": "public_document", "confidence": "verified", "used_for": ["URL universe", "orphan reconciliation"]},
    {"source": "crawl observations", "type": "observed_http", "confidence": "verified", "used_for": ["status", "headers", "on-page HTML", "timing"]},
    {"source": "observed outbound links", "type": "observed_public_evidence", "confidence": "verified", "used_for": ["candidate competitor domains", "anchor-text topic evidence"]},
    {"source": "derived keyword candidates", "type": "derived_from_observed_html", "confidence": "explained", "used_for": ["title/H1/anchor topic inventory", "keyword-to-page suggestions"]},
    {"source": "rule engine", "type": "derived", "confidence": "explained", "used_for": ["issues", "priority", "roadmap"]},
]


def supplied_audit_context(
    db: Session, project_id: int, existing_registry: list | None = None
) -> tuple[dict, list[str], list[dict]]:
    """Return current supplied-data status, gaps and a fresh source registry.

    This is deliberately separate from crawl interpretation: a persisted audit
    can keep its original crawl findings while these live user-supplied fields
    are refreshed after an import.
    """
    raw_signals = supplied_signals(db, project_id)
    supplied_data = {
        key: {
            "label": SIGNAL_LABELS[key],
            "supplied": bool(value["supplied"]),
            "rows": int(value["rows"]),
            "sources": value["sources"],
            "latest_period": value["latest_period"],
            "sample": value["sample"],
        }
        for key, value in raw_signals.items()
    }

    def has_signal(*keys: str) -> bool:
        return any(supplied_data[key]["supplied"] for key in keys)

    missing_data: list[str] = []
    if not has_signal("gsc"):
        missing_data.append("No Search Console queries, impressions, clicks or average positions were supplied.")
    if not has_signal("ga4"):
        missing_data.append("No GA4 sessions, conversions or revenue were supplied.")
    if not has_signal("keywords"):
        missing_data.append("No keyword volume, difficulty or CPC dataset was supplied.")
    if not has_signal("rank"):
        missing_data.append("No rank tracking positions or history were supplied.")
    if not has_signal("backlinks", "authority"):
        missing_data.append("No inbound backlink or domain-authority dataset was supplied.")
    if not has_signal("performance", "crux"):
        missing_data.append("No Lighthouse, CrUX or Core Web Vitals dataset was supplied.")
    if not has_signal("local"):
        missing_data.append("No GBP, NAP or local-visibility dataset was supplied.")
    if not has_signal("serp", "paid"):
        missing_data.append("No SERP-feature or paid-ads dataset was supplied.")
    if not has_signal("historical"):
        missing_data.append("No retained audit history was supplied; only the current crawl is observed.")
    missing_data.extend([
        "No JavaScript-rendered DOM was captured; client-only content may be missing.",
        "No authenticated, staging or private pages were crawled.",
        "AI answer visibility is not sampled; only manually observed evidence can be reported.",
        "Competitor domains are link-observed candidates only; third-party rankings, traffic and market share were not supplied unless a provider export was uploaded.",
    ])

    public_entries = [
        dict(entry) for entry in (existing_registry or [])
        if isinstance(entry, dict) and entry.get("type") not in {"user_supplied_export", "not_supplied"}
    ]
    if not public_entries:
        public_entries = [dict(entry) for entry in BASE_SOURCE_REGISTRY]
    for key, value in supplied_data.items():
        if value["supplied"]:
            public_entries.append({
                "source": f"user-supplied: {key}",
                "type": "user_supplied_export",
                "confidence": "user_declared",
                "used_for": [f"{value['rows']} verbatim rows from {', '.join(value['sources'])}"],
            })
    if not has_signal(*supplied_data):
        public_entries.append({"source": "Search Console / GA4", "type": "not_supplied", "confidence": "none", "used_for": ["not used; no private data claimed"]})
    return supplied_data, missing_data, public_entries


def apply_supplied_data(db: Session, project_id: int, audit: dict) -> dict:
    """Refresh only user-supplied fields on a stored or freshly built audit."""
    result = dict(audit)
    supplied_data, missing_data, source_registry = supplied_audit_context(
        db, project_id, result.get("source_registry")
    )
    result["supplied_data"] = supplied_data
    result["missing_data"] = missing_data
    result["source_registry"] = source_registry
    meta = dict(result.get("meta") or {})
    kinds = [kind for kind in meta.get("data_kinds", []) if not str(kind).startswith("user_supplied:")]
    kinds.extend(f"user_supplied:{key}" for key, value in supplied_data.items() if value["supplied"])
    meta["data_kinds"] = kinds
    result["meta"] = meta
    if all(key in result for key in ("meta", "coverage", "counts", "findings", "roadmap")):
        result["sections"] = _report_sections(result)
    return result


def build_public_audit(db: Session, project_id: int, crawl_id: int | None = None) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise ValueError("Project not found")

    query = select(Crawl).where(Crawl.project_id == project_id)
    if crawl_id:
        query = query.where(Crawl.id == crawl_id)
    crawl = db.scalars(query.order_by(Crawl.id.desc()).limit(1)).first()

    records = db.scalars(select(UrlRecord).where(UrlRecord.project_id == project_id)).all()
    crawled = [r for r in records if r.crawled]
    summary = (crawl.summary or {}) if crawl else {}
    status_counts = Counter(str(r.http_status) for r in crawled if r.http_status is not None)
    page_types = Counter(r.page_type for r in crawled if r.page_type)
    content_rows = db.scalars(select(ContentAnalysis).where(ContentAnalysis.project_id == project_id)).all()
    observations = db.scalars(select(CrawlObservation).where(
        CrawlObservation.project_id == project_id,
        CrawlObservation.requested_url.like("%/robots.txt"),
    ).order_by(CrawlObservation.id.desc()).limit(1)).all()
    robots_doc = observations[0].body_excerpt if observations else (summary.get("robots") or {}).get("document", "")
    robots = {
        "url": (summary.get("robots") or {}).get("url") or f"{urlsplit(project.domain).scheme}://{urlsplit(project.domain).netloc}/robots.txt",
        "status": (summary.get("robots") or {}).get("status") or (observations[0].status_code if observations else None),
        "ai_rules": (summary.get("robots") or {}).get("ai_rules") or crawler_service.parse_robots_rules(robots_doc or ""),
        "document_excerpt": (robots_doc or "")[:4000],
    }

    derived_counts = {
        "competitors": db.scalar(select(func.count()).select_from(Competitor).where(
            Competitor.project_id == project_id,
            Competitor.notes.like("Discovered from%public crawl%"),
        )) or 0,
        "keywords": db.scalar(select(func.count()).select_from(Keyword).where(
            Keyword.project_id == project_id,
            Keyword.source.in_(["public_page_evidence", "competitor_public_anchor"]),
        )) or 0,
        "keyword_gaps": db.scalar(select(func.count()).select_from(KeywordGap).where(
            KeywordGap.project_id == project_id,
            KeywordGap.gap_type == "competitor_topic_evidence",
        )) or 0,
        "keyword_mappings": db.scalar(select(func.count()).select_from(KeywordMapping).where(
            KeywordMapping.project_id == project_id,
            KeywordMapping.source == "public_page_evidence",
        )) or 0,
    }

    supplied_data, missing_data, source_registry = supplied_audit_context(db, project_id)

    audit: dict = {
        "meta": {
            "project_id": project_id,
            "project_name": project.name,
            "domain": project.domain,
            "is_demo": bool(project.is_demo),
            "generated_at": iso(utcnow()),
            "method": "public_evidence_audit",
            "crawl_id": crawl.id if crawl else None,
            "crawl_name": crawl.name if crawl else None,
            "crawl_config": crawl.config if crawl else {},
            "data_kinds": [
                "live_crawl" if not project.is_demo else "synthetic",
                "public_sitemap", "robots.txt", "derived_rules",
                *([f"user_supplied:{key}" for key, value in supplied_data.items() if value["supplied"]]),
            ],
        },
        "coverage": {
            "discovered_urls": int(summary.get("discovered", 0)),
            "fetched_urls": int(summary.get("crawled", 0)) or len(crawled),
            "failed_urls": int(summary.get("failed", 0)),
            "excluded_urls": int(summary.get("excluded", 0)),
            "inventory_urls": len(records),
            "crawled_inventory_urls": len(crawled),
            "robots_respected": bool((crawl.config if crawl else {}).get("respect_robots", True)),
            "javascript_rendering": bool((crawl.config if crawl else {}).get("javascript_rendering", False)),
            "sitemap_entries": db.scalar(
                select(func.count()).select_from(SitemapEntry).where(SitemapEntry.project_id == project_id)
            ) or 0,
            "sitemap": summary.get("sitemap") or {},
        },
        "robots": robots,
        "counts": {
            "status_codes": dict(status_counts),
            "page_types": dict(page_types),
            "indexable": sum(1 for r in crawled if r.indexable is True),
            "non_indexable": sum(1 for r in crawled if r.indexable is False),
            "redirects": len([r for r in crawled if r.redirect_chain]),
            "schema_pages": sum(1 for r in crawled if r.schema_types),
            "average_content_score": round(sum(r.score for r in content_rows) / len(content_rows), 1) if content_rows else None,
        },
        "derived_evidence": {
            **derived_counts,
            "method": "Observed outbound links, page titles, H1s and URL paths from the public crawl. No search volume, difficulty, rank or traffic is claimed.",
            "candidate_definition": "A competitor is an external hostname linked by a crawled page; it is a candidate for review, not a verified market-share claim.",
        },
        "supplied_data": supplied_data,
        "source_registry": source_registry,
        "missing_data": missing_data,
        "deliverables": [
            "Site audit JSON/CSV/XLSX/PDF",
            "Editable PPT board deck",
            "Six-month roadmap with owners and success checks",
            "Raw crawl observation export",
            "Source registry and missing-data statement",
        ],
    }
    audit["findings"] = _findings(db, project_id, crawl, audit)
    audit["roadmap"] = build_roadmap(audit)
    audit["sections"] = _report_sections(audit)
    return audit


def _report_sections(audit: dict) -> list[dict]:
    meta = audit["meta"]
    coverage = audit["coverage"]
    counts = audit["counts"]
    top = audit["findings"]
    return [
        {
            "heading": "1. Executive summary",
            "lines": [
                f"Public-evidence audit of {meta['domain']} generated {meta['generated_at']}.",
                f"The crawler fetched {coverage['fetched_urls']} URLs from {coverage['discovered_urls']} discovered URLs; "
                f"{coverage['failed_urls']} fetches failed and {coverage['sitemap_entries']} sitemap entries were stored.",
                f"{len(audit['findings'])} source-tracked finding groups were produced without Search Console or Analytics access.",
                "Every figure below comes from robots.txt, sitemap files, observed HTTP responses or explained rules.",
            ],
        },
        {
            "heading": "2. Evidence and coverage",
            "lines": [
                f"Inventory URLs: {coverage['inventory_urls']}; crawled URLs: {coverage['crawled_inventory_urls']}.",
                f"Robots respected: {coverage['robots_respected']}; JavaScript rendering: {coverage['javascript_rendering']}.",
                f"Status distribution: {counts['status_codes'] or 'none'}.",
                f"Page types observed: {counts['page_types'] or 'none'}.",
            ],
        },
        {
            "heading": "3. Priority findings",
            "lines": [
                f"[{f['severity']}] {f['title']}: {f['affected_count']} — {f['observation']} Action: {f['recommended_action']}"
                for f in top
            ] or ["No finding groups were produced."],
        },
        {
            "heading": "4. Six-month roadmap",
            "lines": [
                f"Month {m['month']} — {m['theme']}: {m['objective']} Deliverables: {', '.join(m['deliverables'])}."
                for m in audit["roadmap"]
            ],
        },
        {
            "heading": "5. User-supplied datasets actually used",
            "lines": [
                f"{value['label']}: {value['rows']} verbatim rows from {', '.join(value['sources'])}"
                + (f" (latest period {value['latest_period']})" if value["latest_period"] else "")
                for value in audit.get("supplied_data", {}).values() if value["supplied"]
            ] or ["No private or vendor dataset was supplied; every vendor-only signal stays 'Not supplied'."],
        },
        {
            "heading": "6. With and without vendor access",
            "lines": [
                "Without access: the full audit, PPT and roadmap are produced from public evidence alone.",
                "With access: upload GSC/GA4, rank, backlink, Lighthouse, SERP, paid, local or history exports in Integrations.",
                "Uploaded values are stored verbatim and labelled user-supplied; they upgrade prioritisation but are never inferred.",
            ],
        },
        {
            "heading": "7. What this audit does not claim",
            "lines": audit["missing_data"],
        },
    ]


def to_ppt_slides(audit: dict) -> list[dict]:
    meta = audit["meta"]
    coverage = audit["coverage"]
    slides = [{
        "title": f"{meta['project_name']} · Public SEO Audit",
        "bullets": [
            meta["domain"],
            f"Generated {meta['generated_at']} from public, source-tracked evidence",
            f"{coverage['fetched_urls']} URLs fetched · {coverage['sitemap_entries']} sitemap entries · robots respected: {coverage['robots_respected']}",
            "Works with public evidence alone; user-supplied exports are labelled verbatim",
        ],
        "note": "Source: SERPScope crawl, robots.txt, sitemap files and explained rules. "
                + ("User-supplied datasets: " + ", ".join(k for k, v in audit.get("supplied_data", {}).items() if v["supplied"]) if any(v["supplied"] for v in audit.get("supplied_data", {}).values()) else "No vendor data was supplied."),
    }]
    slides.append({
        "title": "Evidence baseline",
        "bullets": [
            f"Discovered URLs: {coverage['discovered_urls']}",
            f"Fetched URLs: {coverage['fetched_urls']} · failures: {coverage['failed_urls']}",
            f"Indexable pages: {audit['counts']['indexable']} · non-indexable: {audit['counts']['non_indexable']}",
            f"Status codes: {audit['counts']['status_codes'] or 'none'}",
            f"Sitemap entries: {coverage['sitemap_entries']}",
        ],
        "note": "Coverage is the observed public sample. See raw crawl observations for request-level evidence.",
    })
    for finding in audit["findings"]:
        slides.append({
            "title": f"{finding['severity']} · {finding['title']}",
            "bullets": [
                f"Affected: {finding['affected_count']}",
                finding["observation"][:400],
                f"Action: {finding['recommended_action']}",
                f"Source: {', '.join(finding['source'])}",
            ],
            "note": finding.get("limitation") or f"Confidence: {finding['confidence']}",
        })
    for month in audit["roadmap"]:
        slides.append({
            "title": f"Month {month['month']} · {month['theme']}",
            "bullets": month["actions"][:4] + [f"Owner: {month['owner']}"],
            "note": f"Without access: {month['without_access']} With access: {month['with_access']}",
        })
    slides.append({
        "title": "Limits and data gaps",
        "bullets": audit["missing_data"][:6],
        "note": "No traffic, revenue, ranking or AI-visibility outcome is claimed without a declared source.",
    })
    return slides


def finding_rows(audit: dict) -> list[dict]:
    return [{
        "id": f["id"],
        "severity": f["severity"],
        "category": f["category"],
        "affected_count": f["affected_count"],
        "observation": f["observation"],
        "recommended_action": f["recommended_action"],
        "source": "; ".join(f["source"]),
        "confidence": f["confidence"],
        "limitation": f["limitation"],
    } for f in audit["findings"]]


def roadmap_rows(audit: dict) -> list[dict]:
    return [{
        "month": m["month"],
        "theme": m["theme"],
        "objective": m["objective"],
        "actions": "; ".join(m["actions"]),
        "deliverables": "; ".join(m["deliverables"]),
        "owner": m["owner"],
        "success_checks": "; ".join(m["success_checks"]),
        "without_access": m["without_access"],
        "with_access": m["with_access"],
    } for m in audit["roadmap"]]


def persist_report(db: Session, project_id: int, audit: dict, generated_by: str = "public-audit") -> int:
    report = Report(
        project_id=project_id,
        title=f"Public evidence site audit · {audit['meta']['domain']}",
        report_type="public_audit",
        period_start=audit["meta"]["generated_at"][:10],
        period_end=audit["meta"]["generated_at"][:10],
        content=audit,
        missing_data=audit["missing_data"],
        generated_by=generated_by,
    )
    db.add(report)
    db.commit()
    return report.id
