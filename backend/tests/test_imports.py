from __future__ import annotations

from sqlalchemy import func, select

from app.models.inventory import SitemapEntry, UrlRecord
from app.models.projects import DataSource
from app.services.imports import parse_sitemap, parse_table, upsert_urls


SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://demo.example.com/one/?utm_source=test</loc><lastmod>2026-11-01</lastmod></url>
  <url><loc>https://demo.example.com/two/</loc></url>
</urlset>
"""

CSV = b"""URL,Title,Clicks,Revenue
https://demo.example.com/one/,One page,12,340.50
https://demo.example.com/three/,Three page,4,10
not-a-url,Bad row,1,1
"""


def test_parse_table_detects_columns_and_values():
    columns, rows = parse_table(CSV, "sample.csv")
    assert columns == ["URL", "Title", "Clicks", "Revenue"]
    assert rows[0]["URL"] == "https://demo.example.com/one/"
    assert rows[1]["Revenue"] == "10"
    assert len(rows) == 3


def test_parse_table_supports_json_and_xlsx():
    json_content = b'[{"url":"https://demo.example.com/json/","clicks":9},{"url":"https://demo.example.com/json-2/","clicks":2}]'
    columns, rows = parse_table(json_content, "keywords.json")
    assert columns == ["url", "clicks"]
    assert rows[0]["clicks"] == "9"

    from io import BytesIO
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["URL", "Title"])
    sheet.append(["https://demo.example.com/xlsx/", "Workbook page"])
    stream = BytesIO()
    workbook.save(stream)
    columns, rows = parse_table(stream.getvalue(), "inventory.xlsx")
    assert columns == ["URL", "Title"]
    assert rows[0]["Title"] == "Workbook page"


def test_parse_sitemap_reads_namespaced_locations():
    entries, kind = parse_sitemap(SITEMAP)
    assert kind == "sitemap"
    assert len(entries) == 2
    assert entries[0]["loc"] == "https://demo.example.com/one/?utm_source=test"
    assert entries[0]["lastmod"] == "2026-11-01"


def test_upsert_urls_is_batch_safe_deduplicated_and_labelled(db, demo_project):
    urls = [
        "HTTPS://DEMO.EXAMPLE.COM/One/?utm_source=newsletter",
        "https://demo.example.com/one/",
        "https://demo.example.com/two/",
        "https://demo.example.com/three/",
        "https://demo.example.com/",
        "http://localhost/private",
        "",
    ]
    accepted, rejected, errors = upsert_urls(
        db, demo_project["project_id"], urls, "csv_urls", "imported",
        rules={"lowercase_path": True}, batch_size=2,
        extra={"title": "Imported page", "clicks": 7, "revenue": 12.5},
    )
    db.commit()
    assert accepted == 4
    assert rejected == 2
    assert any("private" in error or "internal" in error for error in errors)
    count = db.scalar(select(func.count()).select_from(UrlRecord).where(
        UrlRecord.project_id == demo_project["project_id"],
        UrlRecord.url.like("https://demo.example.com/%"),
    ))
    assert count == demo_project["urls"] + 3
    imported = db.scalar(select(UrlRecord).where(
        UrlRecord.project_id == demo_project["project_id"],
        UrlRecord.url == "https://demo.example.com/three/",
    ))
    assert imported.data_kind == "imported"
    assert imported.sources == ["csv_urls"]
    assert imported.clicks == 7
    assert imported.revenue == 12.5
    existing = db.scalar(select(UrlRecord).where(
        UrlRecord.project_id == demo_project["project_id"],
        UrlRecord.url == "https://demo.example.com/",
    ))
    assert existing.data_kind == "synthetic"
    assert set(existing.sources) == {"synthetic_sitemap", "csv_urls"}


def test_import_url_list_api_persists_source_metadata(client, auth_headers, demo_project):
    response = client.post(
        "/api/v1/imports/url-list",
        headers=auth_headers,
        json={
            "project_id": demo_project["project_id"],
            "urls": ["https://demo.example.com/imported-a/", "https://demo.example.com/imported-b/"],
            "source": "api_test",
            "name": "API import test",
            "data_kind": "imported",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["accepted"] == 2
    assert body["rejected"] == 0
    source = db_source(client, auth_headers, demo_project["project_id"])
    assert source["source_type"] == "api_test"
    assert source["data_kind"] == "imported"
    assert source["row_count"] == 2


def db_source(client, headers, project_id: int) -> dict:
    response = client.get(f"/api/v1/imports/sources?project_id={project_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"][0]


def test_sitemap_entries_are_stored_separately_from_inventory(db, demo_project):
    from app.services.imports import store_sitemap_entries

    entries, _ = parse_sitemap(SITEMAP)
    count = store_sitemap_entries(db, demo_project["project_id"], entries, "test-sitemap.xml")
    db.commit()
    assert count == 2
    assert db.scalar(select(func.count()).select_from(SitemapEntry).where(
        SitemapEntry.project_id == demo_project["project_id"]
    )) == demo_project["sitemap_entries"] + 2
    assert db.scalar(select(func.count()).select_from(DataSource).where(
        DataSource.project_id == demo_project["project_id"]
    )) == 0
