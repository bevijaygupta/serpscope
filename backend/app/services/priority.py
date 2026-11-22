"""Transparent, configurable priority scoring.

Every score returns its components, weights, formula and a human-readable
explanation. No score is emitted without evidence.
"""
from __future__ import annotations

import math
from typing import Any

DEFAULT_WEIGHTS = {
    "business_impact": 0.25,
    "organic_performance": 0.18,
    "revenue_impact": 0.20,
    "technical_severity": 0.15,
    "confidence": 0.10,
    "affected_urls": 0.12,
}

THRESHOLDS = {"P0": 80, "P1": 60, "P2": 35, "P3": 0}


def clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def log_scale(value: float, scale: float = 1000.0) -> float:
    """0 -> 0, scale -> ~100, larger values cap at 100."""
    if value <= 0:
        return 0.0
    return clamp(100 * math.log10(1 + value) / math.log10(1 + scale))


def priority_band(score: float, confidence: str = "verified") -> str:
    if confidence in {"unverified", "insufficient", "estimated"} and score < 70:
        return "Review"
    for band in ("P0", "P1", "P2", "P3"):
        if score >= THRESHOLDS[band]:
            return band
    return "P3"


def calculate_priority(
    components: dict[str, float],
    confidence: str = "verified",
    weights: dict[str, float] | None = None,
    context: str = "",
) -> dict[str, Any]:
    """Calculate a weighted priority score with full explanation.

    `components` values are 0-100. Missing components default to zero and are
    reported so that gaps in evidence remain visible.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_weight = sum(w.values()) or 1.0
    used = {k: clamp(float(components.get(k, 0) or 0)) for k in w}
    contributions = {k: used[k] * (w[k] / total_weight) for k in w}
    score = round(sum(contributions.values()), 2)
    formula = " + ".join(f"{k}({used[k]:.1f}) x {w[k] / total_weight:.2f}" for k in w)
    band = priority_band(score, confidence)
    parts = [
        f"{k}={used[k]:.1f} x {w[k] / total_weight:.2f} -> {contributions[k]:.1f}"
        for k in w
        if used[k] > 0
    ]
    explanation = (
        f"Score {score:.1f}/100 = {formula}. "
        + ("Contributions: " + "; ".join(parts) + ". " if parts else "No positive evidence components. ")
        + f"Confidence: {confidence}. Band: {band}."
    )
    if context:
        explanation += f" Context: {context}."
    return {
        "score": score,
        "priority": band,
        "components": used,
        "weights": {k: round(v / total_weight, 4) for k, v in w.items()},
        "contributions": {k: round(v, 2) for k, v in contributions.items()},
        "formula": formula,
        "confidence": confidence,
        "explanation": explanation,
    }


def issue_components(
    affected_count: int = 0,
    clicks: float = 0,
    impressions: float = 0,
    revenue: float = 0,
    conversions: float = 0,
    severity: str = "medium",
    confidence: str = "verified",
    business_impact: str = "unknown",
) -> dict[str, float]:
    severity_map = {"critical": 100, "high": 80, "medium": 50, "low": 20, "info": 5}
    impact_map = {"critical": 100, "high": 80, "medium": 50, "low": 20, "unknown": 10}
    confidence_map = {"verified": 100, "imported": 75, "estimated": 50, "unverified": 25}
    return {
        "business_impact": impact_map.get(business_impact, 10),
        "organic_performance": clamp(max(log_scale(clicks, 2000), log_scale(impressions, 50000) * 0.6)),
        "revenue_impact": clamp(max(log_scale(revenue, 100000), log_scale(conversions, 500) * 0.8)),
        "technical_severity": severity_map.get(severity, 50),
        "confidence": confidence_map.get(confidence, 25),
        "affected_urls": log_scale(affected_count, 10000),
    }


def orphan_components(
    clicks: float = 0,
    impressions: float = 0,
    sessions: float = 0,
    conversions: float = 0,
    revenue: float = 0,
    referring_domains: int = 0,
    importance: float = 0,
    indexable: bool | None = None,
    inlinks: int = 0,
    page_type: str = "unknown",
) -> dict[str, float]:
    type_boost = {"service": 85, "product": 85, "homepage": 90, "category": 70, "article": 45}.get(page_type, 30)
    return {
        "business_impact": clamp(max(type_boost, importance * 100)),
        "organic_performance": clamp(max(log_scale(clicks, 1000), log_scale(impressions, 20000) * 0.6, log_scale(sessions, 2000) * 0.5)),
        "revenue_impact": clamp(max(log_scale(revenue, 50000), log_scale(conversions, 200) * 0.8)),
        "technical_severity": clamp(100 - min(inlinks, 20) * 5) if inlinks == 0 else 20,
        "confidence": 70 if indexable is True else (40 if indexable is None else 20),
        "affected_urls": clamp(log_scale(referring_domains, 500) * 0.8 + (20 if inlinks == 0 else 0)),
    }
