"""Keyword research, clustering and keyword-to-URL mapping models."""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Keyword(Base, IdMixin, TimestampMixin):
    __tablename__ = "keywords"
    project_id: Mapped[int] = mapped_column(index=True)
    keyword: Mapped[str] = mapped_column(Text, index=True)
    normalized: Mapped[str] = mapped_column(Text, index=True)
    intent: Mapped[str] = mapped_column(String(40), default="unclassified", index=True)
    intent_source: Mapped[str] = mapped_column(String(30), default="rule")
    intent_override: Mapped[str] = mapped_column(String(40), default="")
    topic: Mapped[str] = mapped_column(String(150), default="", index=True)
    parent_topic: Mapped[str] = mapped_column(String(150), default="", index=True)
    country: Mapped[str] = mapped_column(String(10), default="", index=True)
    language: Mapped[str] = mapped_column(String(20), default="")
    volume: Mapped[int | None] = mapped_column(Integer)
    difficulty: Mapped[float | None] = mapped_column()
    cpc: Mapped[float | None] = mapped_column()
    competition: Mapped[str] = mapped_column(String(30), default="")
    serp_features: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(100), default="imported", index=True)
    collected_at: Mapped[str | None] = mapped_column(String(40))
    confidence: Mapped[str] = mapped_column(String(30), default="imported")
    cluster_id: Mapped[int | None] = mapped_column(
        ForeignKey("keyword_clusters.id", ondelete="SET NULL"), index=True
    )
    cluster_method: Mapped[str] = mapped_column(String(40), default="")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)


class KeywordCluster(Base, IdMixin, TimestampMixin):
    __tablename__ = "keyword_clusters"
    project_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(String(250), index=True)
    parent_topic: Mapped[str] = mapped_column(String(150), default="")
    intent: Mapped[str] = mapped_column(String(40), default="")
    method: Mapped[str] = mapped_column(String(40), default="")
    reasoning: Mapped[str] = mapped_column(Text, default="")
    primary_keyword: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(30), default="auto")
    keywords: Mapped[list] = mapped_column(JSON, default=list)


class KeywordMapping(Base, IdMixin, TimestampMixin):
    __tablename__ = "keyword_mappings"
    project_id: Mapped[int] = mapped_column(index=True)
    url: Mapped[str] = mapped_column(Text, index=True)
    url_id: Mapped[int | None] = mapped_column(index=True)
    primary_keyword: Mapped[str] = mapped_column(Text, default="", index=True)
    secondary_keywords: Mapped[list] = mapped_column(JSON, default=list)
    supporting_keywords: Mapped[list] = mapped_column(JSON, default=list)
    intent: Mapped[str] = mapped_column(String(40), default="")
    cluster_name: Mapped[str] = mapped_column(String(250), default="")
    page_type: Mapped[str] = mapped_column(String(60), default="")
    funnel_stage: Mapped[str] = mapped_column(String(40), default="")
    target_location: Mapped[str] = mapped_column(String(100), default="")
    confidence: Mapped[float] = mapped_column(default=0.0)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    recommended_changes: Mapped[list] = mapped_column(JSON, default=list)
    suggested_internal_links: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="suggested", index=True)
    cannibalisation_risk: Mapped[str] = mapped_column(String(30), default="none")
    source: Mapped[str] = mapped_column(String(40), default="rule-based")


Index("ix_kw_project_norm", Keyword.project_id, Keyword.normalized)
Index("ix_mapping_project_primary", KeywordMapping.project_id, KeywordMapping.primary_keyword)
