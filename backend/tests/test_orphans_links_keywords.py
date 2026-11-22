from __future__ import annotations

from sqlalchemy import func, select

from app.models.analysis import LinkSuggestion, OrphanRecord
from app.models.inventory import UrlRecord
from app.models.keywords import KeywordCluster, KeywordMapping
from app.services.keywords import classify_intent, cluster_keywords, map_clusters_to_urls
from app.services.links import analyse_graph
from app.services.orphans import detect_orphans, refresh_link_counts


def test_orphan_detection_classifies_and_scores(demo_project, db):
    result = detect_orphans(db, demo_project["project_id"])
    assert result["orphan_urls"] > 0
    assert result["total_urls_considered"] >= demo_project["urls"]
    assert sum(result["by_classification"].values()) == result["orphan_urls"]
    rows = db.scalars(select(OrphanRecord).where(OrphanRecord.project_id == demo_project["project_id"])).all()
    assert rows
    assert all(row.likely_cause and row.recommended_action for row in rows)
    assert all(0 <= row.priority_score <= 100 for row in rows)
    assert {row.confidence for row in rows} <= {"high", "medium", "unverified"}
    # Error URLs are not mislabelled as confirmed orphans.
    assert not any("404" in row.url and row.classification == "Confirmed crawl orphan" for row in rows)


def test_link_graph_creates_reviewable_suggestions(demo_project, db):
    result = analyse_graph(db, demo_project["project_id"], max_suggestions=50)
    assert result["urls_analysed"] == demo_project["urls"]
    assert result["suggestions_created"] > 0
    rows = db.scalars(select(LinkSuggestion).where(LinkSuggestion.project_id == demo_project["project_id"])).all()
    assert len(rows) == result["suggestions_created"]
    assert all(row.status == "proposed" for row in rows)
    assert all(row.reason and row.anchor_text for row in rows)
    assert all(row.source == "graph-rule" for row in rows)


def test_keyword_clustering_mapping_and_cannibalisation(demo_project, db):
    intent, reason = classify_intent("vapt services singapore")
    assert intent in {"commercial investigation", "informational", "transactional", "local", "navigational", "mixed"}
    assert reason
    clustered = cluster_keywords(db, demo_project["project_id"])
    assert clustered["clusters"] > 0
    assert db.scalar(select(func.count()).select_from(KeywordCluster).where(
        KeywordCluster.project_id == demo_project["project_id"])) == clustered["clusters"]
    mapped = map_clusters_to_urls(db, demo_project["project_id"])
    assert mapped["mapped_urls"] > 0
    rows = db.scalars(select(KeywordMapping).where(KeywordMapping.project_id == demo_project["project_id"])).all()
    assert len(rows) == mapped["mapped_urls"]
    assert all(row.reasoning and row.status == "suggested" for row in rows)
    assert isinstance(mapped["cannibalisation_conflicts"], int)


def test_refresh_link_counts_recomputes_from_edges(demo_project, db):
    before = db.scalar(select(func.sum(UrlRecord.internal_inlinks)).where(
        UrlRecord.project_id == demo_project["project_id"])) or 0
    result = refresh_link_counts(db, demo_project["project_id"])
    after = db.scalar(select(func.sum(UrlRecord.internal_inlinks)).where(
        UrlRecord.project_id == demo_project["project_id"])) or 0
    assert result["records_updated"] == demo_project["urls"]
    assert result["internal_inlinks"] == after
    assert before >= 0
