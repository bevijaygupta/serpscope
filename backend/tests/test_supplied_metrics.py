"""User-supplied vendor data is stored verbatim and reported honestly."""
from __future__ import annotations

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.operations import Report
from app.services.import_jobs import run_import
from app.services.public_audit import build_public_audit
from app.services.supplied_metrics import supplied_signals


def test_imported_gsc_export_changes_signal_status_without_inventing_other_data(
    db, demo_project, client, auth_headers, tmp_path, monkeypatch
):
    project_id = demo_project["project_id"]
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    csv_file = tmp_path / "gsc-sample.csv"
    csv_file.write_text(
        "Top queries,Clicks,Impressions,CTR,Position,Date\n"
        "seo audit course,12,400,3%,8.4,2026-11-01\n"
        "technical seo checklist,7,210,3.3%,11.2,2026-11-01\n",
        encoding="utf-8",
    )
    stored_audit = build_public_audit(db, project_id)
    db.add(Report(
        project_id=project_id,
        title="Public audit before import",
        report_type="public_audit",
        content=stored_audit,
        missing_data=[],
        generated_by="public-audit",
    ))
    db.commit()
    assert "No Search Console queries" in " ".join(stored_audit["missing_data"])

    result = run_import(
        SessionLocal, 0,
        {"file_path": str(csv_file), "source_type": "gsc", "name": "gsc-sample.csv",
         "data_kind": "verification_sample"},
        project_id, demo_project["organization_id"],
    )
    assert result["supplied_metric_rows"] == 2

    db.expire_all()
    status = supplied_signals(db, project_id)
    assert status["gsc"]["supplied"] is True
    assert status["gsc"]["rows"] == 2
    assert status["rank"]["supplied"] is False

    audit = build_public_audit(db, project_id)
    assert audit["supplied_data"]["gsc"]["supplied"] is True
    assert audit["supplied_data"]["gsc"]["rows"] == 2
    assert "No Search Console queries" not in " ".join(audit["missing_data"])
    assert any("rank tracking" in statement for statement in audit["missing_data"])
    assert any(source["source"] == "user-supplied: gsc" for source in audit["source_registry"])

    response = client.get(
        "/api/v1/integrations/supplied-signals",
        params={"project_id": project_id}, headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["status_explanations"]) >= {"not_supplied", "supplied", "synthetic"}
    item = next(row for row in payload["items"] if row["signal"] == "gsc")
    assert item["supplied"] is True
    assert item["rows"] == 2
    assert set(item["sample"][0]) == {"dimension", "period", "metrics"}

    records_response = client.get(
        "/api/v1/integrations/supplied-records",
        params={"project_id": project_id, "signal": "gsc"}, headers=auth_headers,
    )
    assert records_response.status_code == 200, records_response.text
    records = records_response.json()["items"]
    assert len(records) == 2
    assert all(set(row) >= {"dimension", "period", "metrics", "data_kind"} for row in records)
    assert {row["metrics"]["Top queries"] for row in records} == {
        "seo audit course", "technical seo checklist",
    }
    assert all(row["metrics"]["Clicks"] in {"12", "7"} for row in records)

    stored_response = client.get(
        f"/api/v1/audits/projects/{project_id}/public-audit",
        headers=auth_headers,
    )
    assert stored_response.status_code == 200, stored_response.text
    stored_payload = stored_response.json()
    assert stored_payload["supplied_data"]["gsc"]["supplied"] is True
    assert "No Search Console queries" not in " ".join(stored_payload["missing_data"])
    assert any(source["type"] == "user_supplied_export" for source in stored_payload["source_registry"])
    assert "user_supplied:gsc" in stored_payload["meta"]["data_kinds"]
    assert any("verbatim rows from gsc" in line for section in stored_payload["sections"] for line in section["lines"])


def test_audit_without_supplied_data_keeps_every_vendor_gap_explicit(db, demo_project, client, auth_headers):
    project_id = demo_project["project_id"]
    audit = build_public_audit(db, project_id)
    joined = " ".join(audit["missing_data"])
    assert "No Search Console queries" in joined
    assert "No GA4 sessions" in joined
    assert "No rank tracking positions" in joined
    assert "No Lighthouse, CrUX" in joined
    assert "No GBP, NAP" in joined
    assert "No SERP-feature or paid-ads" in joined

    # The Search Overview reads these exact honest states; it never fills the gap itself.
    response = client.get(
        "/api/v1/integrations/supplied-signals",
        params={"project_id": project_id}, headers=auth_headers,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert set(payload["status_explanations"]) >= {"not_supplied", "supplied", "synthetic"}
    gsc = next(row for row in payload["items"] if row["signal"] == "gsc")
    assert gsc["supplied"] is False
    assert gsc["rows"] == 0
    assert gsc["sample"] == []
    assert audit["supplied_data"]["gsc"]["supplied"] is False
    assert audit["supplied_data"]["gsc"]["rows"] == 0
    assert audit["supplied_data"]["gsc"]["sample"] == []
