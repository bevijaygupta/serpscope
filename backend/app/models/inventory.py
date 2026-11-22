"""Shared URL inventory, link graph and raw crawl observations."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class UrlRecord(Base, IdMixin, TimestampMixin):
    """One canonicalised URL in a project's shared inventory.

    Interpreted SEO fields live here. Raw observations are stored separately in
    CrawlObservation so that evidence is never confused with interpretation.
    """

    __tablename__ = "url_records"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), index=True)
    normalized_url: Mapped[str] = mapped_column(Text, index=True)
    hostname: Mapped[str] = mapped_column(String(255), index=True)
    path: Mapped[str] = mapped_column(Text, default="")

    # provenance
    sources: Mapped[list] = mapped_column(JSON, default=list)
    data_kind: Mapped[str] = mapped_column(String(30), default="imported", index=True)
    first_seen: Mapped[str | None] = mapped_column(String(40))
    last_seen: Mapped[str | None] = mapped_column(String(40))

    # crawl observation summary
    crawled: Mapped[bool] = mapped_column(default=False, index=True)
    crawled_at: Mapped[str | None] = mapped_column(String(40))
    http_status: Mapped[int | None] = mapped_column(Integer, index=True)
    content_type: Mapped[str] = mapped_column(String(120), default="")
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    content_size: Mapped[int | None] = mapped_column(Integer)

    # on-page fields
    title: Mapped[str] = mapped_column(Text, default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    h1: Mapped[list] = mapped_column(JSON, default=list)
    h2: Mapped[list] = mapped_column(JSON, default=list)
    canonical: Mapped[str] = mapped_column(Text, default="")
    meta_robots: Mapped[str] = mapped_column(String(255), default="")
    x_robots_tag: Mapped[str] = mapped_column(String(255), default="")
    robots_allowed: Mapped[bool | None] = mapped_column()
    indexable: Mapped[bool | None] = mapped_column(index=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    internal_inlinks: Mapped[int] = mapped_column(Integer, default=0)
    internal_outlinks: Mapped[int] = mapped_column(Integer, default=0)
    external_links: Mapped[int] = mapped_column(Integer, default=0)
    image_count: Mapped[int] = mapped_column(Integer, default=0)
    images_missing_alt: Mapped[int] = mapped_column(Integer, default=0)
    schema_types: Mapped[list] = mapped_column(JSON, default=list)
    og: Mapped[dict] = mapped_column(JSON, default=dict)
    hreflang: Mapped[dict] = mapped_column(JSON, default=dict)
    pagination: Mapped[dict] = mapped_column(JSON, default=dict)
    redirect_chain: Mapped[list] = mapped_column(JSON, default=list)
    redirected_to: Mapped[str] = mapped_column(Text, default="")
    crawl_depth: Mapped[int] = mapped_column(Integer, default=0, index=True)
    javascript_rendered: Mapped[bool | None] = mapped_column()

    # classification / business context
    page_type: Mapped[str] = mapped_column(String(60), default="unknown", index=True)
    template: Mapped[str] = mapped_column(String(120), default="", index=True)
    importance: Mapped[float] = mapped_column(default=0.0)
    in_sitemap: Mapped[bool] = mapped_column(default=False, index=True)
    is_orphan: Mapped[bool] = mapped_column(default=False, index=True)
    has_traffic: Mapped[bool] = mapped_column(default=False, index=True)
    clicks: Mapped[float] = mapped_column(default=0.0)
    impressions: Mapped[float] = mapped_column(default=0.0)
    sessions: Mapped[float] = mapped_column(default=0.0)
    conversions: Mapped[float] = mapped_column(default=0.0)
    revenue: Mapped[float] = mapped_column(default=0.0)
    referring_domains: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


Index("ix_url_project_status", UrlRecord.project_id, UrlRecord.http_status)
Index("ix_url_project_type", UrlRecord.project_id, UrlRecord.page_type)
Index("ix_url_project_hash", UrlRecord.project_id, UrlRecord.url_hash, unique=True)
Index("ix_url_project_norm", UrlRecord.project_id, UrlRecord.normalized_url)


class LinkEdge(Base, IdMixin, TimestampMixin):
    __tablename__ = "link_edges"
    project_id: Mapped[int] = mapped_column(index=True)
    source_url: Mapped[str] = mapped_column(Text, index=True)
    target_url: Mapped[str] = mapped_column(Text, index=True)
    anchor: Mapped[str] = mapped_column(Text, default="")
    link_type: Mapped[str] = mapped_column(String(30), default="internal", index=True)
    is_broken: Mapped[bool] = mapped_column(default=False, index=True)
    observed_at: Mapped[str | None] = mapped_column(String(40))
    crawl_id: Mapped[int | None] = mapped_column(index=True)


Index("ix_edge_project_target", LinkEdge.project_id, LinkEdge.target_url)
Index("ix_edge_project_source", LinkEdge.project_id, LinkEdge.source_url)


class SitemapEntry(Base, IdMixin, TimestampMixin):
    __tablename__ = "sitemap_entries"
    project_id: Mapped[int] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(255), default="")
    loc: Mapped[str] = mapped_column(Text, index=True)
    lastmod: Mapped[str] = mapped_column(String(40), default="")
    changefreq: Mapped[str] = mapped_column(String(30), default="")
    priority: Mapped[str] = mapped_column(String(20), default="")
    observed_at: Mapped[str | None] = mapped_column(String(40))


class Crawl(Base, IdMixin, TimestampMixin):
    __tablename__ = "crawls"
    project_id: Mapped[int] = mapped_column(index=True)
    job_id: Mapped[int | None] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200), default="Crawl")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    discovered: Mapped[int] = mapped_column(Integer, default=0)
    crawled: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    excluded: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[str | None] = mapped_column(String(40))
    finished_at: Mapped[str | None] = mapped_column(String(40))
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    data_kind: Mapped[str] = mapped_column(String(30), default="live")


class CrawlObservation(Base, IdMixin, TimestampMixin):
    """Raw, uninterpreted evidence for one fetched URL."""

    __tablename__ = "crawl_observations"
    crawl_id: Mapped[int] = mapped_column(ForeignKey("crawls.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    requested_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text, default="")
    status_code: Mapped[int | None] = mapped_column(Integer, index=True)
    headers: Mapped[dict] = mapped_column(JSON, default=dict)
    redirect_chain: Mapped[list] = mapped_column(JSON, default=list)
    body_excerpt: Mapped[str] = mapped_column(Text, default="")
    response_time_ms: Mapped[int | None] = mapped_column(Integer)
    content_size: Mapped[int | None] = mapped_column(Integer)
    extracted: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    observed_at: Mapped[str | None] = mapped_column(String(40))


Index("ix_obs_crawl_status", CrawlObservation.crawl_id, CrawlObservation.status_code)
