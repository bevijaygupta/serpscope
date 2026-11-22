"""Interpreted SEO analysis: issues, orphan pages, content and link recommendations."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Issue(Base, IdMixin, TimestampMixin):
    __tablename__ = "issues"
    project_id: Mapped[int] = mapped_column(index=True)
    code: Mapped[str] = mapped_column(String(80), index=True)
    name: Mapped[str] = mapped_column(String(250))
    category: Mapped[str] = mapped_column(String(80), default="technical", index=True)
    severity: Mapped[str] = mapped_column(String(20), default="P2", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="P2", index=True)
    priority_score: Mapped[float] = mapped_column(default=0.0)
    business_impact: Mapped[str] = mapped_column(String(40), default="unknown")
    affected_count: Mapped[int] = mapped_column(Integer, default=0)
    page_templates: Mapped[list] = mapped_column(JSON, default=list)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    priority_explanation: Mapped[str] = mapped_column(Text, default="")
    recommended_fix: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(150), default="")
    status: Mapped[str] = mapped_column(String(40), default="Detected", index=True)
    due_date: Mapped[str | None] = mapped_column(String(20))
    resolution_notes: Mapped[str] = mapped_column(Text, default="")
    validation_status: Mapped[str] = mapped_column(String(40), default="unvalidated")
    detected_at: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(60), default="rule-engine")
    is_demo: Mapped[bool] = mapped_column(default=False)


class IssueUrl(Base, IdMixin, TimestampMixin):
    __tablename__ = "issue_urls"
    issue_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class OrphanRecord(Base, IdMixin, TimestampMixin):
    __tablename__ = "orphan_records"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    normalized_url: Mapped[str] = mapped_column(Text, index=True)
    classification: Mapped[str] = mapped_column(String(60), index=True)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    internal_inlinks: Mapped[int] = mapped_column(Integer, default=0)
    crawled: Mapped[bool] = mapped_column(default=False)
    indexable: Mapped[bool | None] = mapped_column()
    clicks: Mapped[float] = mapped_column(default=0.0)
    impressions: Mapped[float] = mapped_column(default=0.0)
    sessions: Mapped[float] = mapped_column(default=0.0)
    conversions: Mapped[float] = mapped_column(default=0.0)
    revenue: Mapped[float] = mapped_column(default=0.0)
    referring_domains: Mapped[int] = mapped_column(Integer, default=0)
    importance: Mapped[float] = mapped_column(default=0.0)
    priority: Mapped[str] = mapped_column(String(10), default="P3", index=True)
    priority_score: Mapped[float] = mapped_column(default=0.0)
    score_components: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[str] = mapped_column(String(30), default="unverified")
    likely_cause: Mapped[str] = mapped_column(Text, default="")
    recommended_action: Mapped[str] = mapped_column(Text, default="")
    page_type: Mapped[str] = mapped_column(String(60), default="unknown")
    observed_at: Mapped[str | None] = mapped_column(String(40))


class ContentAnalysis(Base, IdMixin, TimestampMixin):
    __tablename__ = "content_analyses"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str] = mapped_column(Text, default="")
    title_length: Mapped[int] = mapped_column(Integer, default=0)
    meta_length: Mapped[int] = mapped_column(Integer, default=0)
    h1_count: Mapped[int] = mapped_column(Integer, default=0)
    h2_count: Mapped[int] = mapped_column(Integer, default=0)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    intent_alignment: Mapped[str] = mapped_column(String(40), default="unknown")
    topic_gaps: Mapped[list] = mapped_column(JSON, default=list)
    entity_gaps: Mapped[list] = mapped_column(JSON, default=list)
    image_alt_issues: Mapped[int] = mapped_column(Integer, default=0)
    schema_recommendations: Mapped[list] = mapped_column(JSON, default=list)
    internal_link_suggestions: Mapped[list] = mapped_column(JSON, default=list)
    freshness_signal: Mapped[str] = mapped_column(String(60), default="")
    decay_signal: Mapped[str] = mapped_column(String(60), default="")
    score: Mapped[float] = mapped_column(default=0.0)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    data_kind: Mapped[str] = mapped_column(String(30), default="derived")


class ContentBrief(Base, IdMixin, TimestampMixin):
    __tablename__ = "content_briefs"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    primary_keyword: Mapped[str] = mapped_column(Text, default="")
    secondary_keywords: Mapped[list] = mapped_column(JSON, default=list)
    intent: Mapped[str] = mapped_column(String(40), default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    page_purpose: Mapped[str] = mapped_column(Text, default="")
    suggested_title: Mapped[str] = mapped_column(Text, default="")
    suggested_h1: Mapped[str] = mapped_column(Text, default="")
    suggested_headings: Mapped[list] = mapped_column(JSON, default=list)
    questions: Mapped[list] = mapped_column(JSON, default=list)
    entities: Mapped[list] = mapped_column(JSON, default=list)
    internal_links: Mapped[list] = mapped_column(JSON, default=list)
    conversion_objective: Mapped[str] = mapped_column(Text, default="")
    recommended_schema: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    approval_status: Mapped[str] = mapped_column(String(30), default="draft")


class LinkSuggestion(Base, IdMixin, TimestampMixin):
    __tablename__ = "link_suggestions"
    project_id: Mapped[int] = mapped_column(index=True)
    source_url: Mapped[str] = mapped_column(Text, index=True)
    target_url: Mapped[str] = mapped_column(Text, index=True)
    anchor_text: Mapped[str] = mapped_column(Text, default="")
    relevance: Mapped[float] = mapped_column(default=0.0)
    target_importance: Mapped[float] = mapped_column(default=0.0)
    current_status: Mapped[str] = mapped_column(String(40), default="not_linked")
    reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="proposed")
    source: Mapped[str] = mapped_column(String(40), default="graph-rule")


Index("ix_issue_project_priority", Issue.project_id, Issue.priority)
Index("ix_orphan_project_priority", OrphanRecord.project_id, OrphanRecord.priority)
