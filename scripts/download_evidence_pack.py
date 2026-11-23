"""Download the complete hosted SERPScope public-audit evidence pack.

The script writes only public/observable evidence plus the authenticated audit
views for the demo workspace. It never invents or modifies audit data.

Usage:
  .venv/Scripts/python.exe scripts/download_evidence_pack.py
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

API = os.getenv("SERPSCOPE_API", "https://serpscope-api.onrender.com").rstrip("/")
PROJECT_ID = int(os.getenv("SERPSCOPE_PROJECT_ID", "2"))
JOB_ID = int(os.getenv("SERPSCOPE_JOB_ID", "17"))
TOKEN_PATH = Path(os.getenv(
    "SERPSCOPE_TOKEN_FILE",
    r"C:\Users\Official Use Only\AppData\Local\Temp\opencode\serpscope_token.txt",
))
ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.getenv(
    "SERPSCOPE_EVIDENCE_DIR",
    str(ROOT / "evidence" / "techmagnate_public_audit_hosted_2026-11-23"),
))
MANIFEST: list[dict[str, Any]] = []
ERRORS: list[dict[str, Any]] = []


def token() -> str:
    value = os.getenv("SERPSCOPE_TOKEN") or (TOKEN_PATH.read_text(encoding="utf-8").strip() if TOKEN_PATH.exists() else "")
    if not value:
        raise RuntimeError("No SERPScope bearer token found")
    return value


def save(name: str, content: bytes, endpoint: str, *, expect: int = 200) -> Path:
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    MANIFEST.append({
        "file": name,
        "endpoint": endpoint,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "expect": expect,
    })
    return path


def request(path: str, *, params: dict[str, Any] | None = None, auth: bool = True, expect: int = 200) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token()}"} if auth else {}
    response = httpx.get(API + path, params=params, headers=headers, timeout=180.0)
    if response.status_code != expect:
        ERRORS.append({"endpoint": path, "params": params, "status": response.status_code, "body": response.text[:1000]})
    return response


def save_json(name: str, payload: Any, endpoint: str, params: dict[str, Any] | None = None) -> Path:
    content = json.dumps(payload, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    endpoint_full = endpoint + (("?" + str(httpx.QueryParams(params))) if params else "")
    return save(name, content, endpoint_full)


def save_endpoint(name: str, path: str, *, params: dict[str, Any] | None = None, auth: bool = True) -> Any:
    response = request(path, params=params, auth=auth)
    if response.status_code == 200:
        payload = response.json()
        save_json(name, payload, path, params)
        return payload
    return None


def save_export(prefix: str, path: str, params: dict[str, Any], fmt: str, *, auth: bool = True) -> None:
    all_params = dict(params)
    all_params["format"] = fmt
    response = request(path, params=all_params, auth=auth)
    if response.status_code != 200:
        return
    disposition = response.headers.get("content-disposition", "")
    suggested = re.search(r'filename="?([^";]+)"?', disposition)
    filename = suggested.group(1) if suggested else f"{prefix}.{fmt}"
    save(f"exports/{prefix}_{fmt}{Path(filename).suffix if not filename.endswith(fmt) else ''}", response.content,
         path + "?" + str(httpx.QueryParams(all_params)))


def save_paged(name: str, path: str, *, params: dict[str, Any] | None = None, page_size: int = 500) -> None:
    base = dict(params or {})
    offset = 0
    items: list[Any] = []
    total = 0
    while True:
        paged = dict(base)
        paged.update({"offset": offset, "limit": page_size})
        response = request(path, params=paged)
        if response.status_code != 200:
            break
        payload = response.json()
        batch = payload.get("items") if isinstance(payload, dict) else payload
        items.extend(batch or [])
        total = int(payload.get("total", len(items))) if isinstance(payload, dict) else len(items)
        if not batch or len(items) >= total:
            break
        offset += page_size
    save_json(name, {"endpoint": path, "params": base, "total": total, "items": items}, path, base)


def markdown_value(value: Any) -> str:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return "" if value is None else str(value)


def build_readable(audit: dict, case_study: dict, job: dict, crawl: dict | None) -> None:
    lines = [
        "# SERPScope · complete hosted public-audit evidence pack",
        "",
        f"Target: **{audit['meta']['domain']}**  ",
        f"Project: {audit['meta']['project_name']} (id={audit['meta']['project_id']})  ",
        f"Job: {JOB_ID} · status: {job.get('status')}  ",
        f"Audit generated: {audit['meta']['generated_at']}  ",
        f"Pack downloaded: {datetime.now(timezone.utc).isoformat()}  ",
        "",
        "This file contains every audit segment returned by the live API. Raw rows and every",
        "export format are in the sibling files listed in `MANIFEST.json`. No GSC, GA4, rank",
        "or AI-visibility outcome data was supplied or invented.",
        "",
    ]

    def section(title: str, payload: Any) -> None:
        lines.extend(["", f"## {title}", "", markdown_value(payload), ""])

    section("1. Job", job)
    section("2. Crawl run", crawl)
    section("3. Audit meta", audit["meta"])
    section("4. Coverage", audit["coverage"])
    section("5. Robots evidence", audit["robots"])
    section("6. Counts", audit["counts"])
    section("7. Source registry", audit["source_registry"])
    section("8. Missing-data statements", audit["missing_data"])
    section("9. Deliverables", audit["deliverables"])
    lines.extend(["", "## 10. Findings (all)", ""])
    for item in audit["findings"]:
        lines.extend([f"### {item['id']} · {item['severity']} · {item['title']}", ""])
        for key in ("category", "affected_count", "observation", "recommended_action", "evidence", "source", "confidence", "limitation"):
            lines.append(f"- **{key}:** {markdown_value(item.get(key))}")
        lines.append("")
    lines.extend(["", "## 11. Six-month roadmap (all months)", ""])
    for item in audit["roadmap"]:
        lines.extend([f"### Month {item['month']} · {item['theme']}", ""])
        for key in ("objective", "actions", "deliverables", "owner", "success_checks", "without_access", "with_access"):
            lines.append(f"- **{key}:** {markdown_value(item.get(key))}")
        lines.append("")
    section("12. Report sections", audit["sections"])
    section("13. Public case study (read-only endpoint)", case_study)
    section("14. Download errors", ERRORS)
    (OUT / "COMPLETE_AUDIT.md").write_text("\n".join(lines), encoding="utf-8")

    raw = [
        "# Raw crawl observations",
        "",
        "Every request-level observation exported from the hosted crawl.",
        "The machine-readable versions are `exports/crawl_observations_*.{csv,json,xlsx}`.",
        "",
    ]
    for response_path in sorted(OUT.glob("exports/crawl_observations_*.json")):
        payload = json.loads(response_path.read_text(encoding="utf-8"))
        rows = payload if isinstance(payload, list) else payload.get("items", [])
        raw.extend(["| requested_url | final_url | status | ms | bytes | observed_at |", "|---|---|---:|---:|---:|---|"])
        for row in rows:
            raw.append("| {} | {} | {} | {} | {} | {} |".format(
                row.get("requested_url", ""), row.get("final_url", ""), row.get("status_code", ""),
                row.get("response_time_ms", ""), row.get("content_size", ""), row.get("observed_at", ""),
            ))
    (OUT / "RAW_OBSERVATIONS.md").write_text("\n".join(raw), encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    job = save_endpoint("job.json", f"/api/v1/jobs/{JOB_ID}")
    if not job or job.get("status") != "succeeded":
        raise SystemExit(f"Job {JOB_ID} is {job.get('status') if job else 'unavailable'}; rerun after completion")

    audit = save_endpoint("01_complete_audit.json", f"/api/v1/audits/projects/{PROJECT_ID}/public-audit")
    if not audit:
        raise SystemExit("Could not download the complete audit")
    case_study = save_endpoint("02_public_case_study.json", f"/api/v1/public/case-studies/{PROJECT_ID}", auth=False)
    result = job.get("result") or {}
    crawl_id = int(result.get("crawl_id") or (audit.get("meta") or {}).get("crawl_id") or 0)

    crawl = save_endpoint("03_crawl_run.json", f"/api/v1/crawler/runs/{crawl_id}") if crawl_id else None
    save_endpoint("04_job_list.json", "/api/v1/jobs", params={"limit": 50})
    save_endpoint("05_public_audit_reports.json", f"/api/v1/audits/projects/{PROJECT_ID}/public-audit/reports")
    save_endpoint("06_analytics_reports.json", f"/api/v1/analytics/reports", params={"project_id": PROJECT_ID, "limit": 100})
    save_endpoint("07_inventory_summary.json", f"/api/v1/inventory/summary", params={"project_id": PROJECT_ID})
    save_endpoint("08_meta_export_columns.json", "/api/v1/meta/export-columns")
    if crawl_id:
        save_endpoint(f"09_crawl_observations_page.json", f"/api/v1/crawler/runs/{crawl_id}/observations", params={"offset": 0, "limit": 1000})

    save_paged("10_url_inventory.json", "/api/v1/inventory/urls", params={"project_id": PROJECT_ID})
    save_paged("11_technical_issues.json", "/api/v1/technical/issues", params={"project_id": PROJECT_ID})
    save_paged("12_orphan_records.json", "/api/v1/orphans", params={"project_id": PROJECT_ID})
    save_paged("13_content_analyses.json", "/api/v1/content/analyses", params={"project_id": PROJECT_ID})
    save_paged("14_link_suggestions.json", "/api/v1/internal-links/suggestions", params={"project_id": PROJECT_ID})
    save_paged("15_ai_readiness.json", "/api/v1/ai-search/readiness", params={"project_id": PROJECT_ID})
    save_paged("16_ai_visibility_observations.json", "/api/v1/ai-search/observations", params={"project_id": PROJECT_ID})

    audit_export = f"/api/v1/audits/projects/{PROJECT_ID}/public-audit/export"
    for section in ("all", "findings", "roadmap"):
        for fmt in ("csv", "json", "xlsx"):
            save_export(f"public_audit_{section}", audit_export, {"section": section}, fmt)
    for fmt in ("pdf", "pptx"):
        save_export("public_audit_all", audit_export, {"section": "all"}, fmt)

    if crawl_id:
        export = f"/api/v1/crawler/runs/{crawl_id}/export"
        for fmt in ("csv", "json", "xlsx"):
            save_export("crawl_observations", export, {}, fmt)

    module_exports = [
        ("url_inventory", "/api/v1/inventory/export", {"project_id": PROJECT_ID}, ("csv", "json", "xlsx")),
        ("technical_issues", "/api/v1/technical/export", {"project_id": PROJECT_ID}, ("csv", "json", "xlsx")),
        ("orphan_records", "/api/v1/orphans/export", {"project_id": PROJECT_ID}, ("csv", "json", "xlsx")),
        ("internal_link_suggestions", "/api/v1/internal-links/export", {"project_id": PROJECT_ID}, ("csv", "json", "xlsx")),
    ]
    for name, path, params, formats in module_exports:
        for fmt in formats:
            save_export(name, path, params, fmt)
    for kind in ("analyses", "briefs"):
        for fmt in ("csv", "json", "xlsx"):
            save_export(f"content_{kind}", "/api/v1/content/export", {"project_id": PROJECT_ID, "kind": kind}, fmt)
    for kind in ("readiness", "observations"):
        for fmt in ("csv", "json", "xlsx"):
            save_export(f"ai_{kind}", "/api/v1/ai-search/export", {"project_id": PROJECT_ID, "kind": kind}, fmt)

    for report in (job.get("result") or {}).get("report_id"),:
        if report:
            save_endpoint(f"17_persisted_report_{report}.json", f"/api/v1/analytics/reports/{report}", params={"project_id": PROJECT_ID})

    build_readable(audit, case_study or {}, job, crawl)
    save_json("MANIFEST.json", {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api": API,
        "project_id": PROJECT_ID,
        "job_id": JOB_ID,
        "files": MANIFEST,
        "errors": ERRORS,
    }, "local-pack-manifest")
    (OUT / "DOWNLOAD_LOG.md").write_text(
        "# Download log\n\n" + "\n".join(
            f"- `{e['file']}` ← `{e['endpoint']}` ({e['bytes']} bytes)"
            for e in MANIFEST
        ) + "\n\n## Errors\n\n" + (json.dumps(ERRORS, indent=2) if ERRORS else "None"),
        encoding="utf-8",
    )
    print(f"Evidence pack: {OUT}")
    print(f"Files: {len(MANIFEST)} · errors: {len(ERRORS)}")
    print(f"Audit: {audit['coverage']['fetched_urls']} URLs fetched · {len(audit['findings'])} findings · {len(audit['roadmap'])} roadmap months")


if __name__ == "__main__":
    main()
