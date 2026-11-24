"""Domain-specific enterprise SEO models."""
from __future__ import annotations

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Competitor(Base, IdMixin, TimestampMixin):
    __tablename__ = "competitors"
    project_id: Mapped[int] = mapped_column(index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    notes: Mapped[str] = mapped_column(Text, default="")


class KeywordGap(Base, IdMixin, TimestampMixin):
    __tablename__ = "keyword_gaps"
    project_id: Mapped[int] = mapped_column(index=True)
    competitor_id: Mapped[int | None] = mapped_column(index=True)
    keyword: Mapped[str] = mapped_column(Text, index=True)
    intent: Mapped[str] = mapped_column(String(40), default="")
    competitor_url: Mapped[str] = mapped_column(Text, default="")
    our_url: Mapped[str] = mapped_column(Text, default="")
    gap_type: Mapped[str] = mapped_column(String(60), index=True)
    priority: Mapped[str] = mapped_column(String(10), default="P2")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    recommendation: Mapped[str] = mapped_column(Text, default="")


class InternationalPlan(Base, IdMixin, TimestampMixin):
    __tablename__ = "international_plans"
    project_id: Mapped[int] = mapped_column(index=True)
    market: Mapped[str] = mapped_column(String(100), index=True)
    language: Mapped[str] = mapped_column(String(40), default="")
    url_structure: Mapped[str] = mapped_column(String(60), default="subdirectory")
    search_intent: Mapped[str] = mapped_column(String(60), default="")
    service_pages: Mapped[list] = mapped_column(JSON, default=list)
    supporting_content: Mapped[list] = mapped_column(JSON, default=list)
    keyword_clusters: Mapped[list] = mapped_column(JSON, default=list)
    hreflang_recommendations: Mapped[list] = mapped_column(JSON, default=list)
    internal_link_architecture: Mapped[list] = mapped_column(JSON, default=list)
    roadmap: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class HreflangRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "hreflang_records"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    lang: Mapped[str] = mapped_column(String(20), default="")
    target: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="ok", index=True)
    evidence: Mapped[str] = mapped_column(Text, default="")


class Location(Base, IdMixin, TimestampMixin):
    __tablename__ = "locations"
    project_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200), index=True)
    brand: Mapped[str] = mapped_column(String(120), default="", index=True)
    address: Mapped[str] = mapped_column(Text, default="")
    city: Mapped[str] = mapped_column(String(120), index=True)
    state: Mapped[str] = mapped_column(String(120), default="", index=True)
    postal_code: Mapped[str] = mapped_column(String(40), default="")
    country: Mapped[str] = mapped_column(String(80), index=True)
    phone: Mapped[str] = mapped_column(String(60), default="")
    website: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    landing_page: Mapped[str] = mapped_column(Text, default="")
    local_keywords: Mapped[list] = mapped_column(JSON, default=list)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    audit: Mapped[dict] = mapped_column(JSON, default=dict)
    performance: Mapped[dict] = mapped_column(JSON, default=dict)
    duplicate_group: Mapped[str] = mapped_column(String(80), default="")
    data_kind: Mapped[str] = mapped_column(String(30), default="imported")


class Product(Base, IdMixin, TimestampMixin):
    __tablename__ = "products"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    product_id: Mapped[str] = mapped_column(String(120), default="", index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(200), default="", index=True)
    price: Mapped[str] = mapped_column(String(40), default="")
    availability: Mapped[str] = mapped_column(String(40), default="")
    identifier: Mapped[str] = mapped_column(String(120), default="")
    canonical: Mapped[str] = mapped_column(Text, default="")
    schema_types: Mapped[list] = mapped_column(JSON, default=list)
    diagnostics: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="P2")
    data_kind: Mapped[str] = mapped_column(String(30), default="imported")


class MigrationMapping(Base, IdMixin, TimestampMixin):
    __tablename__ = "migration_mappings"
    project_id: Mapped[int] = mapped_column(index=True)
    old_url: Mapped[str] = mapped_column(Text, index=True)
    new_url: Mapped[str] = mapped_column(Text, default="", index=True)
    redirect_status: Mapped[str] = mapped_column(String(50), default="not_checked", index=True)
    redirect_chain: Mapped[list] = mapped_column(JSON, default=list)
    http_status: Mapped[int | None] = mapped_column()
    old_canonical: Mapped[str] = mapped_column(Text, default="")
    new_canonical: Mapped[str] = mapped_column(Text, default="")
    old_indexable: Mapped[bool | None] = mapped_column()
    new_indexable: Mapped[bool | None] = mapped_column()
    in_old_sitemap: Mapped[bool] = mapped_column(default=False)
    in_new_sitemap: Mapped[bool] = mapped_column(default=False)
    clicks: Mapped[float] = mapped_column(default=0.0)
    revenue: Mapped[float] = mapped_column(default=0.0)
    risk: Mapped[str] = mapped_column(String(10), default="P2", index=True)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(Text, default="")


class MigrationProject(Base, IdMixin, TimestampMixin):
    __tablename__ = "migration_projects"
    project_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(200))
    migration_type: Mapped[str] = mapped_column(String(80), default="domain")
    old_domain: Mapped[str] = mapped_column(String(255), default="")
    new_domain: Mapped[str] = mapped_column(String(255), default="")
    phase: Mapped[str] = mapped_column(String(40), default="planning")
    checklist: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class AiVisibilityRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_visibility_records"
    project_id: Mapped[int] = mapped_column(index=True)
    question: Mapped[str] = mapped_column(Text, index=True)
    answer_engine: Mapped[str] = mapped_column(String(100), default="", index=True)
    observed_at: Mapped[str | None] = mapped_column(String(40))
    brand_mentioned: Mapped[bool | None] = mapped_column()
    competitor_mentioned: Mapped[list] = mapped_column(JSON, default=list)
    cited_url: Mapped[str] = mapped_column(Text, default="")
    answer_url: Mapped[str] = mapped_column(Text, default="")
    locale: Mapped[str] = mapped_column(String(20), default="")
    source: Mapped[str] = mapped_column(String(100), default="manual-observation")
    data_kind: Mapped[str] = mapped_column(String(30), default="observed")
    notes: Mapped[str] = mapped_column(Text, default="")


class AiReadinessItem(Base, IdMixin, TimestampMixin):
    __tablename__ = "ai_readiness_items"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    dimension: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(30), default="gap")
    evidence: Mapped[str] = mapped_column(Text, default="")
    recommendation: Mapped[str] = mapped_column(Text, default="")
    data_kind: Mapped[str] = mapped_column(String(30), default="derived")
