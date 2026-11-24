from __future__ import annotations

from sqlalchemy import select

from app.models.enterprise import Competitor, KeywordGap
from app.models.inventory import Crawl, LinkEdge, UrlRecord
from app.models.keywords import Keyword, KeywordMapping
from app.models.projects import Job, Project
from app.services.competitor_discovery import derive_public_evidence
from app.services.crawler import CrawlConfig, CrawlEngine
from app.services.public_audit import build_public_audit
from app.services.public_audit_jobs import derived_result_counts


def test_derived_result_counts_do_not_double_prefix():
    counts = derived_result_counts({
        "competitors": 2,
        "derived_keywords": 30,
        "keyword_gaps": 3,
        "derived_mappings": 40,
        "error": "ignored",
    })
    assert counts == {
        "derived_competitors": 2,
        "derived_keywords": 30,
        "derived_keyword_gaps": 3,
        "derived_mappings": 40,
    }
    assert not any(key.startswith("derived_derived_") for key in counts)


class FakeResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict | None = None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}
        self.content = text.encode("utf-8")
        self.url = "https://demo.example.com/"


class LinkPageClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url: str, **kwargs):
        if url.endswith("/robots.txt"):
            return FakeResponse(200, "User-agent: *\nAllow: /\n")
        return FakeResponse(
            200,
            '<html><head><title>Enterprise SEO audit guide</title></head>'
            '<body><a href="https://competitor.example.com/guide">Enterprise SEO audit guide</a></body></html>',
            {"content-type": "text/html"},
        )


def test_external_links_are_recorded_when_not_followed(monkeypatch, db, demo_project):
    monkeypatch.setattr("app.services.crawler.httpx.Client", LinkPageClient)
    job = Job(name="Link evidence", job_type="test", status="running")
    db.add(job)
    db.flush()
    crawl = Crawl(project_id=demo_project["project_id"], job_id=job.id, name="Link evidence crawl")
    db.add(crawl)
    db.commit()
    config = CrawlConfig.from_dict({
        "start_url": "https://demo.example.com/",
        "max_urls": 1,
        "max_depth": 1,
        "concurrency": 1,
        "crawl_delay": 0,
        "respect_robots": True,
        "sitemap_discovery": False,
        "follow_external": False,
    })

    stats = CrawlEngine(db, demo_project["project_id"], crawl.id, job.id, config).run()

    assert stats["crawled"] == 1
    edge = db.scalar(select(LinkEdge).where(
        LinkEdge.project_id == demo_project["project_id"],
        LinkEdge.crawl_id == crawl.id,
        LinkEdge.link_type == "external",
        LinkEdge.target_url.like("https://competitor.example.com%"),
    ))
    assert edge is not None
    assert "audit" in edge.anchor.lower()
    assert all("competitor.example.com" not in str(item) for item in stats["errors"])


def test_public_evidence_derivation_populates_keywords_competitors_and_gaps(db, demo_project):
    project = Project(
        organization_id=demo_project["organization_id"],
        name="Public evidence project",
        domain="https://demo.example.com/",
    )
    db.add(project)
    db.flush()
    crawl = Crawl(project_id=project.id, name="Public evidence crawl", status="completed")
    db.add(crawl)
    db.flush()
    record = UrlRecord(
        project_id=project.id,
        url="https://demo.example.com/services/audit/",
        url_hash="public-evidence-1",
        normalized_url="https://demo.example.com/services/audit/",
        hostname="demo.example.com",
        path="/services/audit/",
        crawled=True,
        title="Enterprise SEO audit guide",
        h1=["Enterprise SEO audit guide"],
        page_type="service",
    )
    db.add(record)
    db.flush()
    db.add(LinkEdge(
        project_id=project.id,
        crawl_id=crawl.id,
        source_url=record.url,
        target_url="https://competitor.example.com/guide",
        anchor="Enterprise SEO audit guide",
        link_type="external",
        observed_at="2026-11-24T00:00:00+00:00",
    ))
    db.commit()

    counts = derive_public_evidence(db, project.id, crawl.id)

    assert counts["competitors"] == 1
    assert counts["keyword_gaps"] >= 1
    assert counts["derived_keywords"] >= 1
    assert counts["derived_mappings"] == 1

    competitor = db.scalar(select(Competitor).where(Competitor.project_id == project.id))
    assert competitor.domain == "competitor.example.com"
    assert "public crawl" in competitor.notes

    keyword = db.scalar(select(Keyword).where(
        Keyword.project_id == project.id,
        Keyword.source.in_(["public_page_evidence", "competitor_public_anchor"]),
    ))
    assert keyword is not None
    assert keyword.evidence["outbound_anchor_evidence"]
    assert keyword.evidence["outbound_anchor_evidence"][0]["competitor_domain"] == "competitor.example.com"
    assert keyword.volume is None

    gap = db.scalar(select(KeywordGap).where(KeywordGap.project_id == project.id))
    assert gap.gap_type == "competitor_topic_evidence"
    assert gap.evidence["crawl_id"] == crawl.id

    mapping = db.scalar(select(KeywordMapping).where(
        KeywordMapping.project_id == project.id,
        KeywordMapping.source == "public_page_evidence",
    ))
    assert mapping is not None
    assert mapping.primary_keyword

    audit = build_public_audit(db, project.id, crawl.id)
    assert audit["derived_evidence"]["competitors"] == 1
    assert audit["derived_evidence"]["keyword_gaps"] >= 1
    assert audit["derived_evidence"]["keywords"] >= 1
    assert audit["derived_evidence"]["keyword_mappings"] == 1
    assert "observed outbound links" in " ".join(
        entry["source"] for entry in audit["source_registry"]
    )
    assert any("link-observed candidates" in item for item in audit["missing_data"])
