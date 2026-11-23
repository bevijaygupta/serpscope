"""Configurable, conservative HTTP crawler.

Raw evidence is written to crawl_observations. Interpreted SEO fields are
written to url_records. Robots.txt is honoured by default and private network
targets are rejected before any request.
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import (
    canonical_url,
    classify_page_type,
    hostname_of,
    is_same_host,
    normalize_url,
    url_hash,
    validate_target_url,
)
from app.models.inventory import CrawlObservation, LinkEdge, SitemapEntry, UrlRecord

AI_CRAWLER_AGENTS = (
    "GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot",
    "Claude-User", "PerplexityBot", "Perplexity-User", "Google-Extended",
    "Googlebot-Extended", "CCBot", "Meta-ExternalAgent",
)


def parse_robots_rules(text: str) -> dict[str, dict]:
    """Extract explicit allow/disallow rules for known AI/search agents.

    This is evidence extraction only: it does not predict inclusion in an answer
    engine or imply that an operator's policy is enforced by those engines.
    """
    rules: dict[str, dict] = {}
    current: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current = [value]
        elif key in {"allow", "disallow"} and current:
            for agent in current:
                entry = rules.setdefault(agent, {"allow": [], "disallow": []})
                if value:
                    entry[key].append(value)
    return {agent: rules.get(agent, {"allow": [], "disallow": []}) for agent in AI_CRAWLER_AGENTS if agent in rules}


DEFAULT_CONFIG = {
    "start_url": "",
    "seed_urls": [],
    "max_urls": 500,
    "max_depth": 3,
    "concurrency": 4,
    "timeout": 10,
    "retries": 1,
    "user_agent": "SERPScopeAuditBot/1.0 (+respects robots.txt)",
    "crawl_delay": 1.0,
    "javascript_rendering": False,
    "follow_internal": True,
    "follow_external": False,
    "include_patterns": [],
    "exclude_patterns": [],
    "query_handling": "strip_tracking",
    "canonical_handling": "record",
    "respect_robots": True,
    "sitemap_discovery": True,
    "auth_headers": {},
    "allow_private": False,
    "schedule": "manual",
    "mode": "live",
}


@dataclass
class CrawlConfig:
    start_url: str = ""
    seed_urls: list[str] = field(default_factory=list)
    max_urls: int = 500
    max_depth: int = 3
    concurrency: int = 4
    timeout: int = 10
    retries: int = 1
    user_agent: str = DEFAULT_CONFIG["user_agent"]
    crawl_delay: float = 1.0
    javascript_rendering: bool = False
    follow_internal: bool = True
    follow_external: bool = False
    include_patterns: list[str] = field(default_factory=list)
    exclude_patterns: list[str] = field(default_factory=list)
    query_handling: str = "strip_tracking"
    canonical_handling: str = "record"
    respect_robots: bool = True
    sitemap_discovery: bool = True
    auth_headers: dict = field(default_factory=dict)
    allow_private: bool = False
    schedule: str = "manual"
    mode: str = "live"

    @classmethod
    def from_dict(cls, data: dict | None) -> "CrawlConfig":
        raw = {**DEFAULT_CONFIG, **(data or {})}
        allowed = {f: raw[f] for f in cls.__dataclass_fields__ if f in raw}
        allowed["max_urls"] = max(1, min(int(allowed.get("max_urls", 500)), 100000))
        allowed["max_depth"] = max(0, min(int(allowed.get("max_depth", 3)), 20))
        allowed["concurrency"] = max(1, min(int(allowed.get("concurrency", 4)), 32))
        allowed["crawl_delay"] = max(0.0, float(allowed.get("crawl_delay", 1.0)))
        return cls(**allowed)

    def as_dict(self) -> dict:
        clean = dict(self.__dict__)
        clean.pop("auth_headers", None)
        return clean

    def rules(self) -> dict:
        return {
            "strip_tracking_params": self.query_handling == "strip_tracking",
            "strip_fragment": True,
        }


class RobotsCache:
    """Thread-safe robots.txt cache. Fetch failures fail closed when robots are enabled."""

    def __init__(self, client: httpx.Client, config: CrawlConfig):
        self.client = client
        self.config = config
        self.cache: dict[str, RobotFileParser | None] = {}
        self.delay: dict[str, float] = {}
        self.errors: dict[str, str] = {}
        self.documents: dict[str, str] = {}
        self.sitemaps: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def parser(self, url: str) -> RobotFileParser | None:
        host = hostname_of(url)
        with self._lock:
            if host in self.cache:
                return self.cache[host]
        parser: RobotFileParser | None = None
        error = ""
        if self.config.respect_robots:
            robots_url = f"{urlsplit(url).scheme}://{host}/robots.txt"
            try:
                validate_target_url(robots_url, allow_private=self.config.allow_private)
                resp = self.client.get(robots_url, timeout=5)
                with self._lock:
                    self.documents[host] = resp.text[:20000] if resp.status_code == 200 else ""
                if resp.status_code == 200:
                    parser = RobotFileParser()
                    parser.parse(resp.text.splitlines())
                    try:
                        with self._lock:
                            self.sitemaps[host] = list(parser.site_maps() or [])
                    except Exception:
                        self.sitemaps[host] = []
                    crawl_delay = parser.crawl_delay(self.config.user_agent)
                    if crawl_delay:
                        with self._lock:
                            self.delay[host] = float(crawl_delay)
                elif 400 <= resp.status_code < 500:
                    # No robots.txt is an explicit allow-all for that host.
                    parser = RobotFileParser()
                    parser.parse([])
                else:
                    error = f"robots.txt returned HTTP {resp.status_code}"
            except Exception as exc:  # noqa: BLE001 - a fetch failure must not be treated as permission
                error = f"robots.txt unavailable: {type(exc).__name__}: {exc}"[:300]
        with self._lock:
            self.cache[host] = parser
            if error:
                self.errors[host] = error
        return parser

    def allowed(self, url: str) -> bool:
        parser = self.parser(url)
        if parser is None:
            # If robots checking is disabled, crawling is allowed; if enabled but
            # robots.txt could not be read, skip the URL rather than assume consent.
            return not self.config.respect_robots
        try:
            return parser.can_fetch(self.config.user_agent, url)
        except Exception:
            return not self.config.respect_robots


@dataclass
class FetchResult:
    requested_url: str
    final_url: str = ""
    status_code: int | None = None
    headers: dict = field(default_factory=dict)
    redirect_chain: list[str] = field(default_factory=list)
    body: str = ""
    response_time_ms: int | None = None
    content_size: int | None = None
    error: str = ""
    robots_allowed: bool = True
    extracted: dict = field(default_factory=dict)
    links: list[dict] = field(default_factory=list)


def extract_page(html: str, final_url: str) -> tuple[dict, list[dict]]:
    soup = BeautifulSoup(html or "", "lxml")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))

    def meta(name: str) -> str:
        node = soup.find("meta", attrs={"name": re.compile(f"^{re.escape(name)}$", re.I)})
        if node:
            return (node.get("content") or "").strip()
        node = soup.find("meta", attrs={"property": re.compile(f"^{re.escape(name)}$", re.I)})
        return (node.get("content") or "").strip() if node else ""

    title_node = soup.find("title")
    canonical_node = soup.find("link", rel=lambda r: r and "canonical" in (r if isinstance(r, list) else [r]))
    schema_types: list[str] = []
    for node in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(node.string or node.get_text() or "")
            items = payload if isinstance(payload, list) else [payload]
            for item in items:
                if isinstance(item, dict):
                    t = item.get("@type")
                    if isinstance(t, list):
                        schema_types.extend(str(x) for x in t)
                    elif t:
                        schema_types.append(str(t))
        except (json.JSONDecodeError, TypeError):
            schema_types.append("invalid-json-ld")

    hreflang: dict[str, str] = {}
    for node in soup.find_all("link", rel=lambda r: r and "alternate" in (r if isinstance(r, list) else [r])):
        lang = node.get("hreflang")
        href = node.get("href")
        if lang and href:
            hreflang[lang.lower()] = urljoin(final_url, href)

    og = {}
    for node in soup.find_all("meta", attrs={"property": re.compile("^og:", re.I)}):
        og[(node.get("property") or "").lower()] = (node.get("content") or "").strip()
    twitter = {}
    for node in soup.find_all("meta", attrs={"name": re.compile("^twitter:", re.I)}):
        twitter[(node.get("name") or "").lower()] = (node.get("content") or "").strip()

    h1_texts = [h.get_text(" ", strip=True) for h in soup.find_all("h1")][:20]
    h2_texts = [h.get_text(" ", strip=True) for h in soup.find_all("h2")][:50]
    images = soup.find_all("img")
    pagination = {
        "next": bool(soup.find("link", rel=lambda r: r and "next" in (r if isinstance(r, list) else [r])) or soup.find("a", rel="next")),
        "prev": bool(soup.find("link", rel=lambda r: r and "prev" in (r if isinstance(r, list) else [r])) or soup.find("a", rel="prev")),
    }

    links: list[dict] = []
    for node in soup.find_all("a", href=True):
        href = (node.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "data:")):
            continue
        links.append({
            "url": urljoin(final_url, href),
            "anchor": " ".join(node.get_text(" ", strip=True).split())[:300],
        })

    extracted = {
        "title": title_node.get_text(" ", strip=True) if title_node else "",
        "meta_description": meta("description"),
        "h1": h1_texts,
        "h2": h2_texts,
        "canonical": canonical_url(canonical_node.get("href") if canonical_node else None, final_url),
        "meta_robots": meta("robots"),
        "word_count": len(text.split()),
        "image_count": len(images),
        "images_missing_alt": sum(1 for img in images if not (img.get("alt") or "").strip()),
        "schema_types": schema_types,
        "faq_schema": "FAQPage" in schema_types,
        "organization_schema": "Organization" in schema_types,
        "h2_questions": [h for h in h2_texts if h.strip().endswith("?")],
        "first_paragraph": next(
            (p.get_text(" ", strip=True) for p in soup.find_all("p") if len(p.get_text(" ", strip=True).split()) >= 12),
            "",
        )[:600],
        "og": og,
        "twitter": twitter,
        "hreflang": hreflang,
        "pagination": pagination,
        "content_type": "text/html",
        "body_excerpt": text[:12000],
    }
    return extracted, links


class CrawlEngine:
    def __init__(
        self,
        db: Session,
        project_id: int,
        crawl_id: int,
        job_id: int | None,
        config: CrawlConfig,
        on_progress: Callable[[int, int, str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ):
        self.db = db
        self.project_id = project_id
        self.crawl_id = crawl_id
        self.job_id = job_id
        self.config = config
        self.on_progress = on_progress or (lambda *_: None)
        self.cancelled = cancelled or (lambda: False)
        self.robots: RobotsCache | None = None
        self.last_request: dict[str, float] = {}
        self._request_lock = threading.Lock()
        self.stats = {
            "discovered": 0, "crawled": 0, "failed": 0, "excluded": 0,
            "by_status": {}, "redirects": 0, "indexable": 0, "non_indexable": 0,
            "slow_pages": 0, "duplicate_titles": 0, "duplicate_descriptions": 0,
            "depth_distribution": {}, "errors": [], "robots": {}, "sitemap": {},
        }
        self.titles: dict[str, str] = {}
        self.descriptions: dict[str, str] = {}

    def _allowed_pattern(self, url: str) -> bool:
        if self.config.include_patterns and not any(re.search(p, url, re.I) for p in self.config.include_patterns):
            return False
        if self.config.exclude_patterns and any(re.search(p, url, re.I) for p in self.config.exclude_patterns):
            return False
        return True

    def _canonical_for_crawl(self, url: str) -> str:
        if self.config.query_handling == "drop_all":
            parts = urlsplit(url)
            return urljoin(url, parts.path)
        return normalize_url(url, self.config.rules())

    def _throttle(self, url: str) -> None:
        host = hostname_of(url)
        delay = max(self.config.crawl_delay, (self.robots.delay.get(host, 0) if self.robots else 0))
        if delay <= 0:
            return
        wait = self.last_request.get(host, 0) + delay - time.monotonic()
        if wait > 0:
            time.sleep(min(wait, 30))

    def _fetch(self, url: str) -> FetchResult:
        result = FetchResult(requested_url=url)
        headers = {"User-Agent": self.config.user_agent}
        headers.update(self.config.auth_headers or {})
        chain: list[str] = []
        current = url
        started = time.monotonic()
        try:
            with httpx.Client(follow_redirects=False, timeout=self.config.timeout, headers=headers) as client:
                if self.robots is None:
                    self.robots = RobotsCache(client, self.config)
                for hop in range(10):
                    validate_target_url(current, allow_private=self.config.allow_private)
                    # Check permission BEFORE issuing the request, including each redirect hop.
                    if self.robots and self.config.respect_robots and not self.robots.allowed(current):
                        result.error = "Disallowed by robots.txt"
                        result.robots_allowed = False
                        result.status_code = 0
                        result.final_url = current
                        result.redirect_chain = list(chain)
                        return result
                    with self._request_lock:
                        self._throttle(current)
                        self.last_request[hostname_of(current)] = time.monotonic()
                    response = None
                    for attempt in range(self.config.retries + 1):
                        try:
                            response = client.get(current)
                            break
                        except httpx.HTTPError as exc:
                            if attempt == self.config.retries:
                                result.error = f"{type(exc).__name__}: {exc}"[:1000]
                            else:
                                time.sleep(0.5 * (attempt + 1))
                    if response is None:
                        result.status_code = 0
                        result.final_url = current
                        result.redirect_chain = chain
                        return result
                    result.headers = {k.lower(): v for k, v in response.headers.items()}
                    result.status_code = response.status_code
                    result.final_url = str(response.url)
                    result.content_size = len(response.content)
                    if 300 <= response.status_code < 400 and response.headers.get("location") and hop < 9:
                        chain.append(current)
                        current = urljoin(current, response.headers["location"])
                        continue
                    body = response.text if "html" in response.headers.get("content-type", "").lower() or not response.headers.get("content-type") else ""
                    if body:
                        result.extracted, result.links = extract_page(body, result.final_url)
                        result.body = result.extracted.pop("body_excerpt", "")
                    break
            if len(chain) > 0:
                chain.append(result.final_url)
                result.redirect_chain = chain
        except ValueError as exc:
            result.error = str(exc)
            result.status_code = 0
            result.final_url = current
            result.redirect_chain = chain
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"[:1000]
            result.status_code = result.status_code or 0
        result.response_time_ms = int((time.monotonic() - started) * 1000)
        return result

    def _store(self, result: FetchResult, depth: int) -> None:
        now = iso(utcnow())
        self.db.add(CrawlObservation(
            crawl_id=self.crawl_id, project_id=self.project_id,
            requested_url=result.requested_url, final_url=result.final_url,
            status_code=result.status_code, headers=result.headers,
            redirect_chain=result.redirect_chain, body_excerpt=result.body[:12000],
            response_time_ms=result.response_time_ms, content_size=result.content_size,
            extracted=result.extracted, error=result.error, observed_at=now,
        ))
        ext = result.extracted
        robots_txt = (ext.get("meta_robots", "") + " " + result.headers.get("x-robots-tag", "")).lower()
        noindex = "noindex" in robots_txt
        indexable = None if result.status_code in (0, None) else (
            bool(200 <= result.status_code < 300) and not noindex
        )
        norm = self._canonical_for_crawl(result.final_url or result.requested_url)
        h = url_hash(result.requested_url, self.config.rules())
        rec = self.db.query(UrlRecord).filter(
            UrlRecord.project_id == self.project_id, UrlRecord.url_hash == h
        ).first()
        if rec is None:
            rec = UrlRecord(
                project_id=self.project_id, url_hash=h, sources=[f"crawl:{self.crawl_id}"],
                url=result.requested_url, normalized_url=norm,
                hostname=hostname_of(result.requested_url),
                path=urlsplit(result.requested_url).path,
                data_kind="live_crawl" if self.config.mode == "live" else "simulated",
                first_seen=now,
            )
            self.db.add(rec)
        rec.crawled = True
        rec.crawled_at = now
        rec.last_seen = now
        rec.http_status = result.status_code
        rec.content_type = result.headers.get("content-type", "")[:120]
        rec.response_time_ms = result.response_time_ms
        rec.content_size = result.content_size
        rec.title = ext.get("title", "")
        rec.meta_description = ext.get("meta_description", "")
        rec.h1 = ext.get("h1", [])
        rec.h2 = ext.get("h2", [])
        rec.canonical = ext.get("canonical", "")
        rec.meta_robots = ext.get("meta_robots", "")
        rec.x_robots_tag = result.headers.get("x-robots-tag", "")
        rec.robots_allowed = result.robots_allowed
        rec.indexable = indexable
        rec.word_count = int(ext.get("word_count", 0))
        rec.image_count = int(ext.get("image_count", 0))
        rec.images_missing_alt = int(ext.get("images_missing_alt", 0))
        rec.schema_types = ext.get("schema_types", [])
        rec.og = ext.get("og", {})
        rec.hreflang = ext.get("hreflang", {})
        rec.pagination = ext.get("pagination", {})
        rec.redirect_chain = result.redirect_chain
        rec.redirected_to = result.final_url if result.redirect_chain else ""
        rec.crawl_depth = depth
        rec.javascript_rendered = bool(self.config.javascript_rendering and ext)
        rec.page_type = classify_page_type(result.final_url, rec.title)
        if self.config.javascript_rendering and not ext:
            rec.notes = "JS rendering requested; no HTML extracted (Playwright renderer not active)"
        if rec.title:
            self.titles[rec.title.lower()] = self.titles.get(rec.title.lower(), 0) + 1
        if rec.meta_description:
            self.descriptions[rec.meta_description.lower()] = self.descriptions.get(rec.meta_description.lower(), 0) + 1
        status = str(result.status_code)
        self.stats["by_status"][status] = self.stats["by_status"].get(status, 0) + 1
        if result.redirect_chain:
            self.stats["redirects"] += 1
        if indexable:
            self.stats["indexable"] += 1
        elif indexable is False:
            self.stats["non_indexable"] += 1
        if (result.response_time_ms or 0) > 2000:
            self.stats["slow_pages"] += 1
        self.stats["depth_distribution"][str(depth)] = self.stats["depth_distribution"].get(str(depth), 0) + 1
        if result.status_code in (0, None) or result.error:
            self.stats["failed"] += 1
            if len(self.stats["errors"]) < 100:
                self.stats["errors"].append({"url": result.requested_url, "error": result.error or "No response"})
        if result.status_code and 200 <= result.status_code < 300:
            self.stats["crawled"] += 1

        # Link edges
        for link in result.links:
            target = link["url"]
            is_internal = is_same_host(target, result.final_url or result.requested_url)
            if is_internal and not self.config.follow_internal:
                continue
            if not is_internal:
                # An external link is public evidence even when we deliberately do
                # not crawl it. Preserve it for competitor discovery, but never
                # queue it unless follow_external is explicitly enabled.
                try:
                    validate_target_url(target, allow_private=self.config.allow_private)
                except ValueError:
                    continue
            self.db.add(LinkEdge(
                project_id=self.project_id, crawl_id=self.crawl_id,
                source_url=result.final_url or result.requested_url,
                target_url=target, anchor=link["anchor"],
                link_type="internal" if is_internal else "external",
                is_broken=False, observed_at=now,
            ))

    def _add_evidence_observation(self, url: str, status: int | None, text: str, content_type: str, error: str = "") -> None:
        """Persist robots/sitemap documents as raw evidence, not interpreted fields."""
        self.db.add(CrawlObservation(
            crawl_id=self.crawl_id, project_id=self.project_id,
            requested_url=url, final_url=url, status_code=status,
            headers={"content-type": content_type}, redirect_chain=[],
            body_excerpt=(text or "")[:12000], response_time_ms=None,
            content_size=len((text or "").encode("utf-8")),
            extracted={"document_type": "robots.txt" if url.endswith("/robots.txt") else "sitemap"},
            error=error[:1000], observed_at=iso(utcnow()),
        ))

    def _discover_sitemaps(self, start_url: str) -> dict:
        """Read robots.txt and sitemap index files, then seed URLs from them.

        Sitemap documents are stored as raw observations and also upserted into
        the URL inventory with `in_sitemap` provenance so orphan analysis can
        distinguish sitemap-only URLs from discovered internal links.
        """
        base = urlsplit(start_url)
        robots_url = f"{base.scheme}://{base.netloc}/robots.txt"
        info: dict = {
            "robots_url": robots_url, "robots_status": None,
            "declared_sitemaps": [], "sitemap_files": [], "sitemap_urls": 0,
            "robots_ai_rules": {}, "document": "", "errors": [],
        }
        headers = {"User-Agent": self.config.user_agent}
        headers.update(self.config.auth_headers or {})
        parser: RobotFileParser | None = None
        try:
            validate_target_url(robots_url, allow_private=self.config.allow_private)
            with httpx.Client(timeout=8, follow_redirects=True, headers=headers) as client:
                robots_resp = client.get(robots_url)
                info["robots_status"] = robots_resp.status_code
                robots_text = robots_resp.text if robots_resp.status_code == 200 else ""
                info["document"] = robots_text[:12000]
                self._add_evidence_observation(
                    robots_url, robots_resp.status_code, robots_text,
                    robots_resp.headers.get("content-type", "text/plain"),
                    "" if robots_resp.status_code == 200 else f"HTTP {robots_resp.status_code}",
                )
                if robots_text:
                    parser = RobotFileParser()
                    parser.parse(robots_text.splitlines())
                    try:
                        info["declared_sitemaps"] = [u for u in (parser.site_maps() or [])][:30]
                    except Exception:
                        info["declared_sitemaps"] = []
                info["robots_ai_rules"] = parse_robots_rules(robots_text)

                from app.services.imports import parse_sitemap, store_sitemap_entries, upsert_urls

                candidates = list(info["declared_sitemaps"]) + [
                    f"{base.scheme}://{base.netloc}/sitemap.xml",
                    f"{base.scheme}://{base.netloc}/sitemap_index.xml",
                ]
                seen_files: set[str] = set()
                all_entries: list[dict] = []
                for candidate in candidates:
                    if len(seen_files) >= 25 or len(all_entries) >= self.config.max_urls:
                        break
                    try:
                        validate_target_url(candidate, allow_private=self.config.allow_private)
                        if parser and self.config.respect_robots and not parser.can_fetch(self.config.user_agent, candidate):
                            continue
                        if candidate in seen_files:
                            continue
                        seen_files.add(candidate)
                        resp = client.get(candidate)
                        if resp.status_code != 200:
                            continue
                        text = resp.text
                        self._add_evidence_observation(
                            candidate, resp.status_code, text[:20000],
                            resp.headers.get("content-type", "application/xml"),
                        )
                        entries, kind = parse_sitemap(resp.content)
                        info["sitemap_files"].append({"url": candidate, "kind": kind, "entries": len(entries)})
                        if kind == "sitemap_index":
                            for child in entries[:25]:
                                loc = (child.get("loc") or "").strip()
                                if not loc or loc in seen_files or len(seen_files) >= 25:
                                    continue
                                try:
                                    validate_target_url(loc, allow_private=self.config.allow_private)
                                    if parser and self.config.respect_robots and not parser.can_fetch(self.config.user_agent, loc):
                                        continue
                                    seen_files.add(loc)
                                    child_resp = client.get(loc)
                                    if child_resp.status_code != 200:
                                        continue
                                    self._add_evidence_observation(
                                        loc, child_resp.status_code, child_resp.text[:20000],
                                        child_resp.headers.get("content-type", "application/xml"),
                                    )
                                    child_entries, child_kind = parse_sitemap(child_resp.content)
                                    info["sitemap_files"].append({
                                        "url": loc, "kind": child_kind, "entries": len(child_entries),
                                    })
                                    if child_kind == "sitemap":
                                        all_entries.extend(child_entries)
                                except Exception as exc:  # noqa: BLE001 - one broken sitemap must not stop the crawl
                                    info["errors"].append(f"{loc}: {type(exc).__name__}: {exc}"[:300])
                        elif kind == "sitemap":
                            all_entries.extend(entries)
                    except Exception as exc:  # noqa: BLE001
                        info["errors"].append(f"{candidate}: {type(exc).__name__}: {exc}"[:300])

                deduped: list[dict] = []
                seen_urls: set[str] = set()
                for entry in all_entries[: self.config.max_urls]:
                    loc = (entry.get("loc") or "").strip()
                    if not loc or loc in seen_urls:
                        continue
                    seen_urls.add(loc)
                    if not is_same_host(loc, start_url):
                        continue
                    deduped.append(entry)
                if deduped:
                    store_sitemap_entries(
                        self.db, self.project_id, deduped,
                        "sitemap-discovery",
                    )
                    accepted, _, _ = upsert_urls(
                        self.db, self.project_id, [e["loc"] for e in deduped],
                        source="sitemap", data_kind="public_sitemap",
                        rules=self.config.rules(), extra={"in_sitemap": True},
                    )
                    info["sitemap_urls"] = accepted
                    hashes = [url_hash(e["loc"], self.config.rules()) for e in deduped]
                    for i in range(0, len(hashes), 500):
                        for rec in self.db.query(UrlRecord).filter(
                            UrlRecord.project_id == self.project_id,
                            UrlRecord.url_hash.in_(hashes[i:i + 500]),
                        ):
                            rec.in_sitemap = True
                    self.db.flush()
                    # Release the write lock before the caller reports progress on
                    # SQLite; on Postgres this also makes sitemap evidence durable
                    # even if the crawl is later cancelled.
                    self.db.commit()
        except Exception as exc:  # noqa: BLE001 - sitemap discovery is best-effort evidence
            info["errors"].append(f"sitemap discovery: {type(exc).__name__}: {exc}"[:300])
        return info

    def run(self) -> dict:
        seeds: list[tuple[str, int]] = []
        if self.config.start_url:
            seeds.append((self.config.start_url, 0))
        for url in self.config.seed_urls:
            seeds.append((url, 0))
        if self.config.sitemap_discovery and self.config.start_url:
            sitemap_info = self._discover_sitemaps(self.config.start_url)
            self.stats["sitemap"] = sitemap_info
            if self.robots is not None:
                host = hostname_of(self.config.start_url)
                self.stats["robots"] = {
                    "url": sitemap_info.get("robots_url", ""),
                    "status": sitemap_info.get("robots_status"),
                    "document": (self.robots.documents.get(host, "") or sitemap_info.get("document", ""))[:12000],
                    "ai_rules": sitemap_info.get("robots_ai_rules", {}),
                }
            elif sitemap_info.get("robots_ai_rules") or sitemap_info.get("document"):
                self.stats["robots"] = {
                    "url": sitemap_info.get("robots_url", ""),
                    "status": sitemap_info.get("robots_status"),
                    "document": sitemap_info.get("document", "")[:12000],
                    "ai_rules": sitemap_info.get("robots_ai_rules", {}),
                }
            for entry in self.db.query(SitemapEntry).filter(
                SitemapEntry.project_id == self.project_id,
                SitemapEntry.source.like("sitemap%"),
            ).order_by(SitemapEntry.id.desc()).limit(self.config.max_urls):
                seeds.append((entry.loc, 1))
        queue: list[tuple[str, int]] = []
        seen: set[str] = set()
        for url, depth in seeds:
            try:
                validate_target_url(url, allow_private=self.config.allow_private)
                key = self._canonical_for_crawl(url)
                if key in seen:
                    continue
                seen.add(key)
                queue.append((url, depth))
            except ValueError as exc:
                self.stats["excluded"] += 1
                self.stats["errors"].append({"url": url, "error": str(exc)})
        self.stats["discovered"] = len(queue)
        self.on_progress(0, min(len(queue), self.config.max_urls), "Starting crawl")

        visited = 0
        while queue and visited < self.config.max_urls:
            if self.cancelled():
                self.stats["errors"].append({"url": "", "error": "Cancelled by user"})
                break
            batch: list[tuple[str, int]] = []
            while queue and len(batch) < self.config.concurrency and visited + len(batch) < self.config.max_urls:
                batch.append(queue.pop(0))
            with concurrent.futures.ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
                futures = {executor.submit(self._fetch, url): (url, depth) for url, depth in batch}
                for future in concurrent.futures.as_completed(futures):
                    url, depth = futures[future]
                    result = future.result()
                    if result.error == "Disallowed by robots.txt":
                        self.stats["excluded"] += 1
                        detail = (
                            (self.robots.errors.get(hostname_of(url)) if self.robots else None)
                            or "Disallowed by robots.txt"
                        )
                        self.stats["errors"].append({"url": url, "error": detail})
                    elif result.error and ("Private" in result.error or "credentials" in result.error):
                        self.stats["excluded"] += 1
                    else:
                        self._store(result, depth)
                        if depth < self.config.max_depth and result.status_code and 200 <= result.status_code < 400:
                            for link in result.links:
                                target = link["url"]
                                is_internal = is_same_host(target, result.final_url or url)
                                if not is_internal and not self.config.follow_external:
                                    continue
                                if not self._allowed_pattern(target):
                                    self.stats["excluded"] += 1
                                    continue
                                try:
                                    validate_target_url(target, allow_private=self.config.allow_private)
                                except ValueError:
                                    self.stats["excluded"] += 1
                                    continue
                                key = self._canonical_for_crawl(target)
                                if key not in seen:
                                    seen.add(key)
                                    queue.append((target, depth + 1))
                                    self.stats["discovered"] += 1
                    visited += 1
                    # Commit before reporting progress: the progress row is written
                    # through a different session, and SQLite allows one writer.
                    self.db.commit()
                    self.on_progress(visited, min(self.config.max_urls, self.stats["discovered"]), f"Fetched {visited} URLs")
            self.db.flush()
        self.stats["duplicate_titles"] = max(0, sum(c - 1 for c in self.titles.values() if c > 1))
        self.stats["duplicate_descriptions"] = max(0, sum(c - 1 for c in self.descriptions.values() if c > 1))
        self.db.commit()
        return self.stats
