"""Keyword normalisation, intent classification, clustering and URL mapping."""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Iterable

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.timeutil import iso, utcnow
from app.core.url_utils import classify_page_type, normalize_url, path_of
from app.models.inventory import UrlRecord
from app.models.keywords import Keyword, KeywordCluster, KeywordMapping

STOPWORDS = {
    "a", "an", "and", "are", "for", "how", "in", "is", "of", "on", "or", "the", "to", "what",
    "which", "why", "with", "best", "near", "me", "my", "your", "you", "do", "does", "can",
}
INTENT_PATTERNS = [
    ("local", r"\b(near me|nearby|in [a-z ]+|location|opening hours|address|directions)\b"),
    ("transactional", r"\b(buy|price|pricing|quote|book|order|hire|purchase|discount|deal|sign up|free trial)\b"),
    ("commercial investigation", r"\b(best|top|vs|versus|review|comparison|compare|alternative|alternatives|software|tool|services?)\b"),
    ("navigational", r"\b(login|log in|dashboard|website|official|support|contact|careers)\b"),
    ("informational", r"\b(what|how|why|guide|tutorial|ideas|tips|examples|definition|meaning|learn|checklist)\b"),
]


def normalize_keyword(value: str) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"[^\w\s-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def keyword_tokens(value: str) -> set[str]:
    return {t for t in normalize_keyword(value).split() if len(t) > 2 and t not in STOPWORDS}


def classify_intent(keyword: str, brand_terms: Iterable[str] = ()) -> tuple[str, str]:
    kw = normalize_keyword(keyword)
    brands = [normalize_keyword(b) for b in brand_terms if b]
    if brands and any(b and b in kw for b in brands):
        if re.search(r"\b(login|official|website|careers)\b", kw):
            return "navigational", "brand term plus navigational modifier"
        return "branded", "contains configured brand term"
    matched = []
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, kw):
            matched.append(intent)
    if len(matched) > 1:
        return "mixed", "multiple intent modifiers: " + ", ".join(matched)
    if matched:
        return matched[0], f"matched {matched[0]} modifier pattern"
    return "informational", "default: no commercial or local modifier detected"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _char_ngrams(value: str, n: int = 3) -> Counter:
    text = normalize_keyword(value).replace(" ", "")
    return Counter(text[i:i + n] for i in range(max(0, len(text) - n + 1)))


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b.get(k, 0) for k in a)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)


def cluster_keywords(db: Session, project_id: int, method: str = "normalized", config: dict | None = None) -> dict[str, Any]:
    """Cluster imported keywords. Returns cluster counts and method details."""
    cfg = {"threshold": 0.45, "brand_terms": [], "max_keywords": 100000}
    cfg.update(config or {})
    keywords = db.scalars(
        select(Keyword).where(Keyword.project_id == project_id).order_by(Keyword.id).limit(cfg["max_keywords"])
    ).all()
    if not keywords:
        return {"clusters": 0, "keywords": 0, "method": method, "note": "No keywords imported"}
    intent_classes = [(k, classify_intent(k.keyword, cfg["brand_terms"])[0]) for k in keywords]
    uf = UnionFind(len(keywords))
    ngrams = [_char_ngrams(k.keyword) for k in keywords] if method == "semantic" else []
    tokens = [keyword_tokens(k.keyword) for k in keywords] if method in {"token", "serp_overlap"} else []
    reasons: dict[int, list[str]] = defaultdict(list)

    if method == "exact":
        groups: dict[str, list[int]] = defaultdict(list)
        for i, k in enumerate(keywords):
            groups[k.keyword.strip().lower()].append(i)
        for idxs in groups.values():
            for i in idxs[1:]:
                uf.union(idxs[0], i)
            reasons[idxs[0]].append("exact string match")
    elif method == "normalized":
        groups = defaultdict(list)
        for i, k in enumerate(keywords):
            groups[normalize_keyword(k.keyword)].append(i)
        for idxs in groups.values():
            for i in idxs[1:]:
                uf.union(idxs[0], i)
            reasons[idxs[0]].append("normalised phrase match")
    elif method == "intent":
        groups = defaultdict(list)
        for i, (_, intent) in enumerate(intent_classes):
            groups[intent].append(i)
        for idxs in groups.values():
            for i in idxs[1:]:
                uf.union(idxs[0], i)
            reasons[idxs[0]].append("same classified intent")
    elif method == "token":
        threshold = float(cfg["threshold"])
        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                score = _jaccard(tokens[i], tokens[j])
                if score >= threshold:
                    uf.union(i, j)
                    reasons[min(i, j)].append(f"token overlap {score:.2f}")
    elif method == "semantic":
        threshold = float(cfg.get("semantic_threshold", 0.55))
        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                score = _cosine(ngrams[i], ngrams[j])
                if score >= threshold:
                    uf.union(i, j)
                    reasons[min(i, j)].append(f"character similarity {score:.2f}")
    elif method == "serp_overlap":
        serp_sets = []
        for k in keywords:
            evidence = k.evidence or {}
            urls = evidence.get("serp_urls") or evidence.get("serp_results") or []
            serp_sets.append({normalize_url(u) for u in urls})
        for i in range(len(keywords)):
            for j in range(i + 1, len(keywords)):
                if not serp_sets[i] or not serp_sets[j]:
                    continue
                overlap = len(serp_sets[i] & serp_sets[j]) / len(serp_sets[i] | serp_sets[j])
                if overlap >= float(cfg.get("serp_threshold", 0.3)):
                    uf.union(i, j)
                    reasons[min(i, j)].append(f"SERP overlap {overlap:.2f}")
    else:
        raise ValueError(f"Unsupported clustering method: {method}")

    clusters: dict[int, list[int]] = defaultdict(list)
    for i, k in enumerate(keywords):
        clusters[uf.find(i)].append(i)

    db.query(KeywordCluster).filter(KeywordCluster.project_id == project_id).delete()
    db.flush()
    result = []
    for root, idxs in sorted(clusters.items()):
        members = [keywords[i] for i in idxs]
        members.sort(key=lambda k: (-(k.volume or 0), k.keyword))
        primary = members[0].keyword
        token_counts = Counter(t for k in members for t in keyword_tokens(k.keyword))
        label = " ".join(t for t, _ in token_counts.most_common(3)) or primary
        intents = Counter(intent_classes[i][1] for i in idxs)
        intent = intents.most_common(1)[0][0]
        total_volume = sum(k.volume or 0 for k in members)
        reasoning = (
            f"Method={method}; {len(members)} keywords; total supplied volume={total_volume}; "
            f"dominant intent={intent}; evidence: {'; '.join(dict.fromkeys(reasons.get(root, [])))[:500]}"
        )
        cluster = KeywordCluster(
            project_id=project_id, name=f"{label.title()} ({len(members)})",
            parent_topic=members[0].parent_topic or label.title(),
            intent=intent, method=method, reasoning=reasoning,
            primary_keyword=primary,
            keywords=[{"keyword": k.keyword, "volume": k.volume, "intent": k.intent} for k in members],
        )
        db.add(cluster)
        db.flush()
        for k in members:
            k.cluster_id = cluster.id
            k.cluster_method = method
        result.append({"cluster_id": cluster.id, "name": cluster.name, "keywords": len(members), "primary": primary})
    db.commit()
    return {
        "method": method, "keywords": len(keywords), "clusters": len(result),
        "thresholds": {k: v for k, v in cfg.items() if "threshold" in k},
        "clusters_sample": result[:20],
        "note": "Semantic method uses character-similarity rules; no external embedding provider is called unless configured separately.",
    }


def map_clusters_to_urls(db: Session, project_id: int, config: dict | None = None) -> dict[str, Any]:
    """Assign one primary cluster/keyword per URL using transparent scoring."""
    cfg = {"max_urls": 100000, "brand_terms": []}
    cfg.update(config or {})
    clusters = db.scalars(
        select(KeywordCluster).where(KeywordCluster.project_id == project_id)
    ).all()
    if not clusters:
        return {"mapped": 0, "error": "No clusters available; run clustering first"}
    urls = db.scalars(
        select(UrlRecord).where(UrlRecord.project_id == project_id).order_by(UrlRecord.id)
        .limit(cfg["max_urls"])
    ).all()
    cluster_features = []
    for c in clusters:
        all_tokens = set()
        for k in c.keywords or []:
            all_tokens |= keyword_tokens(str(k.get("keyword", "")))
        cluster_features.append((c, all_tokens))

    db.query(KeywordMapping).filter(KeywordMapping.project_id == project_id).delete()
    used_primary: set[str] = set()
    mapped = 0
    unmapped_urls = []
    for rec in urls:
        page_text = f"{rec.title or ''} {' '.join(rec.h1 or [])} {path_of(rec.url).replace('-', ' ').replace('_', ' ')}"
        page_tokens = keyword_tokens(page_text)
        page_intent, _ = classify_intent(page_text or rec.url, cfg["brand_terms"])
        best = None
        for cluster, tokens in cluster_features:
            overlap = _jaccard(page_tokens, tokens) if page_tokens else 0.0
            coverage = len(page_tokens & tokens) / max(1, len(tokens)) if tokens else 0.0
            intent_match = 1.0 if cluster.intent == page_intent else (0.4 if "mixed" in (cluster.intent, page_intent) else 0.0)
            volume = sum(int(k.get("volume") or 0) for k in (cluster.keywords or []))
            volume_score = min(1.0, math.log10(1 + volume) / 4)
            uniqueness = 0.0 if cluster.primary_keyword.lower() in used_primary else 0.25
            score = overlap * 0.35 + coverage * 0.25 + intent_match * 0.2 + volume_score * 0.1 + uniqueness
            if best is None or score > best[0]:
                best = (score, cluster, coverage, intent_match)
        if best is None or best[0] < 0.18:
            unmapped_urls.append(rec.url)
            continue
        score, cluster, coverage, intent_match = best
        primary = cluster.primary_keyword
        cannibalisation = "conflict" if primary.lower() in used_primary else (
            "watch" if coverage < 0.15 else "none"
        )
        used_primary.add(primary.lower())
        members = cluster.keywords or []
        secondary = [str(m.get("keyword")) for m in members[1:6]]
        supporting = [str(m.get("keyword")) for m in members[6:16]]
        changes = []
        if not rec.title:
            changes.append("Add a title including the primary keyword")
        if not rec.h1:
            changes.append("Add an H1 aligned to the primary intent")
        if intent_match < 1:
            changes.append(f"Align content with detected intent ({cluster.intent})")
        db.add(KeywordMapping(
            project_id=project_id, url=rec.url, url_id=rec.id,
            primary_keyword=primary, secondary_keywords=secondary,
            supporting_keywords=supporting, intent=cluster.intent,
            cluster_name=cluster.name, page_type=rec.page_type,
            funnel_stage={"informational": "awareness", "commercial investigation": "consideration",
                          "transactional": "conversion", "local": "conversion"}.get(cluster.intent, "consideration"),
            target_location=("Singapore" if rec.url.lower().endswith("/sg/") or ".sg" in rec.url else ""),
            confidence=round(min(0.99, score), 3),
            reasoning=(f"token overlap/coverage {coverage:.2f}, intent match {intent_match:.2f}, "
                       f"cluster method={cluster.method}, page type={rec.page_type}"),
            recommended_changes=changes, cannibalisation_risk=cannibalisation,
            source="rule-based", status="suggested",
        ))
        mapped += 1
    db.commit()

    # Cannibalisation report: duplicate primaries and overlapping clusters on identical page types
    conflicts = db.execute(text(
        "SELECT primary_keyword, COUNT(*) c, GROUP_CONCAT(url) urls FROM keyword_mappings "
        "WHERE project_id=:p GROUP BY lower(primary_keyword) HAVING c > 1 ORDER BY c DESC LIMIT 5000"
    ), {"p": project_id}).all()
    rows = [{
        "primary_keyword": r[0], "url_count": r[1], "urls": (r[2] or "").split(","),
        "risk": "high", "recommendation": "Consolidate pages or differentiate intent and primary keyword",
    } for r in conflicts]
    return {
        "mapped_urls": mapped, "unmapped_urls": len(unmapped_urls),
        "unmapped_sample": unmapped_urls[:20], "cannibalisation_conflicts": len(rows),
        "conflicts_sample": rows[:20], "method": "token_coverage+intent+volume+uniqueness",
    }


def ensure_intents(db: Session, project_id: int, brand_terms: list[str] | None = None) -> int:
    updated = 0
    for kw in db.scalars(select(Keyword).where(Keyword.project_id == project_id)):
        if kw.intent_override:
            kw.intent = kw.intent_override
            kw.intent_source = "manual"
        else:
            intent, reason = classify_intent(kw.keyword, brand_terms or [])
            kw.intent = intent
            kw.intent_source = "rule"
            kw.evidence = {**(kw.evidence or {}), "intent_reason": reason}
        updated += 1
    db.commit()
    return updated
