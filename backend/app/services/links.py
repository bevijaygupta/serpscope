"""Internal-link graph analysis and reviewable link suggestions."""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.url_utils import normalize_url
from app.models.analysis import LinkSuggestion
from app.models.inventory import LinkEdge, UrlRecord
from app.services.keywords import keyword_tokens


def analyse_graph(db: Session, project_id: int, max_suggestions: int = 5000) -> dict[str, Any]:
    records = db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id).order_by(UrlRecord.id).limit(100000)
    ).all()
    edges = db.scalars(select(LinkEdge).where(LinkEdge.project_id == project_id)).all()
    inlinks: dict[str, int] = defaultdict(int)
    anchors: dict[str, Counter] = defaultdict(Counter)
    broken: list[dict] = []
    for edge in edges:
        target = normalize_url(edge.target_url)
        if edge.link_type == "internal":
            inlinks[target] += 1
            if edge.anchor:
                anchors[target][edge.anchor.lower()] += 1
        if edge.is_broken:
            broken.append({"source": edge.source_url, "target": edge.target_url, "anchor": edge.anchor})
    by_url = {normalize_url(r.url): r for r in records}
    depth_distribution = Counter(r.crawl_depth for r in records)
    important_weak = [
        {
            "url": r.url, "inlinks": r.internal_inlinks, "clicks": r.clicks,
            "revenue": r.revenue, "importance": r.importance, "page_type": r.page_type,
            "reason": "High business or page importance with few internal links",
        }
        for r in records
        if r.internal_inlinks <= 2 and (r.clicks > 50 or r.revenue > 500 or r.importance >= 0.7 or r.page_type in {"service", "product"})
    ][:1000]
    excessive = [
        {"url": r.url, "outlinks": r.internal_outlinks}
        for r in records if r.internal_outlinks > 150
    ][:1000]
    orphan_candidates = [r for r in records if r.internal_inlinks == 0]

    db.query(LinkSuggestion).filter(LinkSuggestion.project_id == project_id).delete()
    created = 0
    # Suggest links from topically related, well-linked pages to orphan/weak targets.
    sources = [r for r in records if r.internal_inlinks >= 3 and r.crawled][:4000]
    targets = (orphan_candidates + [x["url"] for x in important_weak])[:3000]
    target_records = []
    seen = set()
    for t in targets:
        candidate_url = t.url if isinstance(t, UrlRecord) else t
        key = normalize_url(candidate_url)
        rec = by_url.get(key)
        if rec and key not in seen:
            target_records.append(rec)
            seen.add(key)
    for target in target_records[:1000]:
        target_tokens = keyword_tokens(f"{target.title} {' '.join(target.h1 or [])} {target.url}")
        ranked = []
        for source in sources:
            source_tokens = keyword_tokens(f"{source.title} {' '.join(source.h1 or [])} {source.url}")
            overlap = source_tokens & target_tokens
            if overlap:
                ranked.append((len(overlap) / max(1, len(target_tokens)), source, overlap))
        ranked.sort(key=lambda x: x[0], reverse=True)
        for relevance, source, overlap in ranked[:3]:
            if created >= max_suggestions:
                break
            anchor = sorted(overlap)[0] if overlap else (target.h1[0] if target.h1 else target.title[:60])
            db.add(LinkSuggestion(
                project_id=project_id, source_url=source.url, target_url=target.url,
                anchor_text=anchor[:120], relevance=round(min(1.0, relevance), 3),
                target_importance=round(min(1.0, (target.importance + min(1.0, target.clicks / 500)) / 2), 3),
                current_status="not_linked" if target.internal_inlinks == 0 else "weakly_linked",
                reason=f"Topical token overlap {relevance:.2f}; target inlinks={target.internal_inlinks}",
                source="graph-rule", status="proposed",
            ))
            created += 1
    db.commit()
    return {
        "urls_analysed": len(records), "edges_analysed": len(edges),
        "orphans": len(orphan_candidates), "important_weak_pages": len(important_weak),
        "excessive_link_pages": len(excessive), "broken_links": len(broken),
        "depth_distribution": dict(depth_distribution),
        "anchor_examples": {k: v.most_common(5) for k, v in list(anchors.items())[:10]},
        "suggestions_created": created,
        "broken_sample": broken[:20],
        "important_weak_sample": important_weak[:20],
    }
