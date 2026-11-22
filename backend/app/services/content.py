"""Page-level content analysis and evidence-based content brief generation."""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.url_utils import path_of
from app.models.analysis import ContentAnalysis, ContentBrief
from app.models.inventory import UrlRecord
from app.models.keywords import KeywordMapping
from app.services.keywords import keyword_tokens


def analyse_content(db: Session, project_id: int, max_urls: int = 50000) -> dict[str, Any]:
    records = db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id, UrlRecord.crawled.is_(True))
        .order_by(UrlRecord.id).limit(max_urls)
    ).all()
    mappings = {m.url: m for m in db.scalars(
        select(KeywordMapping).where(KeywordMapping.project_id == project_id)
    )}
    db.query(ContentAnalysis).filter(ContentAnalysis.project_id == project_id).delete()
    scores = []
    for rec in records:
        target = mappings.get(rec.url)
        primary = target.primary_keyword if target else ""
        primary_tokens = keyword_tokens(primary)
        page_tokens = keyword_tokens(f"{rec.title} {' '.join(rec.h1 or [])} {path_of(rec.url)}")
        alignment = "aligned" if primary_tokens and (primary_tokens & page_tokens) else (
            "unknown" if not primary else "misaligned"
        )
        title_len = len(rec.title or "")
        findings = []
        if title_len == 0:
            findings.append("Missing title")
        elif title_len < 30:
            findings.append("Title is short")
        elif title_len > 65:
            findings.append("Title may be truncated")
        if not rec.meta_description:
            findings.append("Missing meta description")
        if not rec.h1:
            findings.append("Missing H1")
        if rec.word_count < 100:
            findings.append("Limited content depth")
        if rec.images_missing_alt > 0:
            findings.append(f"{rec.images_missing_alt} images missing alt text")
        if rec.page_type in {"product", "service", "article"} and not rec.schema_types:
            findings.append("No structured data detected")
        topic_gaps = sorted(primary_tokens - page_tokens)[:10]
        entity_gaps = sorted(t for t in primary_tokens if t not in page_tokens)[:10]
        score = max(0, 100 - len(findings) * 8 - (20 if alignment == "misaligned" else 0))
        db.add(ContentAnalysis(
            project_id=project_id, url=rec.url, title=rec.title,
            title_length=title_len, meta_length=len(rec.meta_description or ""),
            h1_count=len(rec.h1 or []), h2_count=len(rec.h2 or []),
            word_count=rec.word_count, intent_alignment=alignment,
            topic_gaps=topic_gaps, entity_gaps=entity_gaps,
            image_alt_issues=rec.images_missing_alt,
            schema_recommendations=(["Product", "BreadcrumbList"] if rec.page_type == "product"
                                    else ["Service", "FAQPage", "Organization"] if rec.page_type == "service" else []),
            internal_link_suggestions=[],
            freshness_signal="unknown", decay_signal="unknown",
            score=score, findings=findings, data_kind="derived",
        ))
        scores.append(score)
    db.commit()
    return {
        "analysed": len(scores),
        "average_score": round(sum(scores) / len(scores), 2) if scores else 0,
        "data_kind": "derived_from_crawl_observations",
    }


def generate_briefs(db: Session, project_id: int, limit: int = 500) -> dict[str, Any]:
    mappings = db.scalars(
        select(KeywordMapping).where(KeywordMapping.project_id == project_id)
        .order_by(KeywordMapping.id).limit(limit)
    ).all()
    db.query(ContentBrief).filter(ContentBrief.project_id == project_id).delete()
    created = 0
    for mapping in mappings:
        secondary = mapping.secondary_keywords or []
        questions = [
            f"What is {mapping.primary_keyword}?",
            f"How do you choose {mapping.primary_keyword}?",
            f"What should you check before using {mapping.primary_keyword}?",
        ]
        headings = ["Overview", f"Benefits of {mapping.primary_keyword}", "How it works", "Common questions"]
        headings += [str(s).title() for s in secondary[:4]]
        entities = sorted(keyword_tokens(mapping.primary_keyword) | {t for s in secondary for t in keyword_tokens(str(s))})[:20]
        schema = ["FAQPage", "BreadcrumbList"]
        if mapping.page_type == "product":
            schema.insert(0, "Product")
        if mapping.page_type == "service":
            schema.insert(0, "Service")
        db.add(ContentBrief(
            project_id=project_id, url=mapping.url,
            primary_keyword=mapping.primary_keyword,
            secondary_keywords=secondary[:10], intent=mapping.intent,
            audience="Decision-makers researching " + mapping.primary_keyword,
            page_purpose=f"Serve {mapping.intent} intent for {mapping.primary_keyword}",
            suggested_title=f"{mapping.primary_keyword.title()} | Guide & Options",
            suggested_h1=mapping.primary_keyword.title(),
            suggested_headings=headings, questions=questions, entities=entities,
            internal_links=mapping.suggested_internal_links or [],
            conversion_objective=("Request a quote or consultation" if mapping.intent in {"transactional", "commercial investigation", "local"} else "Subscribe or continue reading"),
            recommended_schema=schema,
            sources=[f"keyword mapping #{mapping.id}", f"cluster: {mapping.cluster_name}"],
            approval_status="draft",
        ))
        created += 1
    db.commit()
    return {"briefs_created": created, "data_kind": "rule-based suggestions; not copied competitor content"}
