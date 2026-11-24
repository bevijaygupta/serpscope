"""User-supplied vendor data is stored verbatim and reported honestly."""
from __future__ import annotations

from app.db.session import SessionLocal
from app.services.import_jobs import run_import
from app.services.public_audit import build_public_audit
from app.services.supplied_metrics import supplied_signals


def test_imported_gsc_export_changes_signal_status_without_inventing_other_data(
    db, demo_project, client, auth_headers, tmp_path
):
    project_id = demo_project["project_id"]
    csv_file = tmp_path / "gsc-sample.csv"
    csv_file.write_text(
        "Top queries,Clicks,Impressions,CTR,Position,Date\n"
        "seo audit course,12,400,3%,8.4,2026-11-01\n"
        "technical seo checklist,7,210,3.3%,11.2,2026-11-01\n",
        encoding="utf-8",
    )
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
    item = next(row for row in response.json()["items"] if row["signal"] == "gsc")
    assert item["supplied"] is True
    assert item["rows"] == 2


def test_audit_without_supplied_data_keeps_every_vendor_gap_explicit(db, demo_project):
    audit = build_public_audit(db, demo_project["project_id"])
    joined = " ".join(audit["missing_data"])
    assert "No Search Console queries" in joined
    assert "No GA4 sessions" in joined
    assert "No rank tracking positions" in joined
    assert "No Lighthouse, CrUX" in joined
    assert "No GBP, NAP" in joined
    assert "No SERP-feature or paid-ads" in joined
