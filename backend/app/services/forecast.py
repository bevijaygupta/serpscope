"""Transparent scenario forecasting. Estimates are explicitly not guarantees."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models.operations import Forecast


def _ctr_curve(position: float, baseline_ctr: float, baseline_position: float) -> float:
    """Simple relative CTR model: CTR scales with 1/position^2 relative to baseline."""
    if position <= 0 or baseline_position <= 0:
        return baseline_ctr
    factor = (baseline_position / position) ** 2
    return min(0.6, max(0.001, baseline_ctr * factor))


def build_forecast(db: Session, project_id: int, name: str, inputs: dict, created_by: int | None = None) -> dict[str, Any]:
    baseline_clicks = float(inputs.get("current_clicks") or 0)
    impressions = float(inputs.get("impressions") or 0)
    ctr = float(inputs.get("ctr") or (baseline_clicks / impressions if impressions else 0.02))
    position = float(inputs.get("average_position") or 20)
    conv_rate = float(inputs.get("conversion_rate") or 0)
    value = float(inputs.get("average_value") or 0)
    opportunity_clicks = float(inputs.get("opportunity_clicks") or 0)
    scenarios_cfg = inputs.get("scenarios") or {
        "conservative": {"position_factor": 0.85, "ctr_factor": 0.9, "capture": 0.25},
        "expected": {"position_factor": 0.65, "ctr_factor": 1.0, "capture": 0.5},
        "optimistic": {"position_factor": 0.45, "ctr_factor": 1.1, "capture": 0.8},
    }
    scenarios = {}
    for label, cfg in scenarios_cfg.items():
        target_position = max(1.0, position * float(cfg.get("position_factor", 1)))
        target_ctr = _ctr_curve(target_position, ctr, position) * float(cfg.get("ctr_factor", 1))
        additional_impressions = opportunity_clicks / max(ctr, 0.001) * float(cfg.get("capture", 0.5))
        total_impressions = impressions + additional_impressions
        projected_clicks = total_impressions * target_ctr
        conversions = projected_clicks * conv_rate
        scenarios[label] = {
            "assumptions": cfg,
            "target_position": round(target_position, 2),
            "target_ctr": round(target_ctr, 4),
            "projected_impressions": round(total_impressions, 1),
            "projected_clicks": round(projected_clicks, 1),
            "incremental_clicks": round(projected_clicks - baseline_clicks, 1),
            "projected_conversions": round(conversions, 2),
            "projected_value": round(conversions * value, 2),
        }
    formulas = {
        "target_ctr": "min(0.6, baseline_ctr * (baseline_position / target_position)^2 * ctr_factor)",
        "projected_impressions": "current_impressions + (opportunity_clicks / baseline_ctr * capture)",
        "projected_clicks": "projected_impressions * target_ctr",
        "projected_conversions": "projected_clicks * conversion_rate",
        "projected_value": "projected_conversions * average_value",
    }
    sensitivity = []
    for variable, deltas in {
        "ctr": [-0.01, 0.01], "position": [-2, 2], "conversion_rate": [-0.01, 0.01], "demand": [-0.2, 0.2]
    }.items():
        for delta in deltas:
            modified = {**inputs}
            if variable == "ctr":
                modified["ctr"] = max(0.001, ctr + delta)
            elif variable == "position":
                modified["average_position"] = max(1, position + delta)
            elif variable == "conversion_rate":
                modified["conversion_rate"] = max(0, conv_rate + delta)
            else:
                modified["opportunity_clicks"] = max(0, opportunity_clicks * (1 + delta))
            sim = build_scenarios_only(modified, scenarios_cfg)
            sensitivity.append({
                "variable": variable, "delta": delta,
                "expected_clicks": sim["expected"]["projected_clicks"],
                "expected_value": sim["expected"]["projected_value"],
            })
    record = Forecast(
        project_id=project_id, name=name, inputs=inputs,
        scenarios=scenarios, formulas=formulas, created_by=created_by,
    )
    db.add(record)
    db.commit()
    return {
        "forecast_id": record.id, "scenarios": scenarios, "formulas": formulas,
        "sensitivity": sensitivity,
        "disclaimer": "Scenario estimate based on user-supplied assumptions. Not a ranking, traffic or revenue guarantee.",
    }


def build_scenarios_only(inputs: dict, scenarios_cfg: dict | None = None) -> dict[str, dict]:
    baseline_clicks = float(inputs.get("current_clicks") or 0)
    impressions = float(inputs.get("impressions") or 0)
    ctr = float(inputs.get("ctr") or (baseline_clicks / impressions if impressions else 0.02))
    position = float(inputs.get("average_position") or 20)
    conv_rate = float(inputs.get("conversion_rate") or 0)
    value = float(inputs.get("average_value") or 0)
    opportunity_clicks = float(inputs.get("opportunity_clicks") or 0)
    cfg = scenarios_cfg or {
        "conservative": {"position_factor": 0.85, "ctr_factor": 0.9, "capture": 0.25},
        "expected": {"position_factor": 0.65, "ctr_factor": 1.0, "capture": 0.5},
        "optimistic": {"position_factor": 0.45, "ctr_factor": 1.1, "capture": 0.8},
    }
    out = {}
    for label, s in cfg.items():
        target_position = max(1.0, position * float(s.get("position_factor", 1)))
        target_ctr = _ctr_curve(target_position, ctr, position) * float(s.get("ctr_factor", 1))
        total_impressions = impressions + opportunity_clicks / max(ctr, 0.001) * float(s.get("capture", 0.5))
        clicks = total_impressions * target_ctr
        conversions = clicks * conv_rate
        out[label] = {"projected_clicks": round(clicks, 1), "projected_value": round(conversions * value, 2)}
    return out
