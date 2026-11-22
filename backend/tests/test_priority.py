from __future__ import annotations

from app.services.priority import (
    calculate_priority,
    clamp,
    issue_components,
    log_scale,
    orphan_components,
    priority_band,
)


def test_clamp_and_log_scale_are_bounded():
    assert clamp(-5) == 0
    assert clamp(150) == 100
    assert log_scale(0) == 0
    assert 0 < log_scale(10) < log_scale(1000) <= 100
    assert log_scale(10_000_000) == 100


def test_priority_score_is_explainable():
    components = issue_components(affected_count=120, clicks=400, revenue=9000, severity="high",
                                  confidence="verified", business_impact="critical")
    result = calculate_priority(components, "verified", context="planted high-value 404")
    assert 0 <= result["score"] <= 100
    assert result["priority"] in {"P0", "P1", "P2", "P3", "Review"}
    assert "Score" in result["explanation"]
    assert "business_impact" in result["formula"]
    assert set(result["components"]) == set(result["weights"])
    assert abs(sum(result["weights"].values()) - 1.0) < 0.001


def test_low_confidence_scores_are_marked_for_review():
    assert priority_band(60, "unverified") == "Review"
    assert priority_band(80, "verified") == "P0"
    result = calculate_priority(issue_components(confidence="unverified", severity="low"), "unverified")
    assert result["confidence"] == "unverified"


def test_orphan_components_reflect_evidence():
    rich = orphan_components(clicks=500, revenue=10_000, importance=0.9, indexable=True,
                             inlinks=0, page_type="service")
    poor = orphan_components(clicks=0, revenue=0, importance=0.1, indexable=None,
                             inlinks=0, page_type="unknown")
    assert rich["business_impact"] > poor["business_impact"]
    assert rich["organic_performance"] > poor["organic_performance"]
    assert rich["confidence"] > poor["confidence"]
